"""Skattemässiga justeringar i INK2S (punkt 4.3–4.6) och bolagsskatten.

iOrdning lät människan fylla i 4.3c, 4.5c och 4.6a för hand. Här räknas de
fram ur bokföringen, och var och en kan ersättas med ett belopp som en
människa har angett (`bokslut_inputs`, migration 046). Det beräknade beloppet
visas alltid bredvid, så att en ersättning syns.

- 4.3c Andra bokförda kostnader som inte ska dras av: konton som är ej
  avdragsgilla (BAS-standard eller "ej avdragsgill" i kontonamnet).
- 4.5c Andra bokförda intäkter som inte ska tas upp: skattefria konton (BAS
  8314, eller "ej skattepliktig"/"skattefri" i kontonamnet).
- 4.6a Schablonintäkt: periodiseringsfonderna vid beskattningsårets ingång
  gånger statslåneräntan vid utgången av november året innan, lägst 0,5 %.
- 4.6d Uppräkning vid återföring: 6 % av återförda fonder avsatta
  beskattningsår som började före 2019, 4 % för 2019–2020, inget därefter.

Belopp räknas i öre och avrundas till hela kronor först när de visas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional

# Statslåneräntan vid utgången av november, i procent. Året är det år räntan
# gäller för: beskattningsår som börjar år Y använder räntan från november
# Y-1. Ett år som saknas måste anges som uppgift (`ink2s.slr`).
STATSLANERANTA_NOVEMBER: Dict[int, Decimal] = {
    2022: Decimal("1.94"),
    2023: Decimal("2.62"),
    2024: Decimal("1.96"),
    2025: Decimal("2.55"),
}
SLR_GOLV = Decimal("0.5")

BOLAGSSKATT = Decimal("0.206")

# BAS: konton för kostnader som inte är avdragsgilla.
EJ_AVDRAGSGILLA_BAS = frozenset(
    {"6072", "6342", "6982", "6992", "6993", "7622", "7632", "8423"}
)
# BAS: skattefria intäkter.
SKATTEFRIA_BAS = frozenset({"8314"})

_EJ_AVDRAGSGILL_NAMN = re.compile(r"ej\s+avdragsgill", re.IGNORECASE)
_SKATTEFRI_NAMN = re.compile(r"ej\s+skattepliktig|skattefri", re.IGNORECASE)
_AR_I_NAMN = re.compile(r"\b(20\d{2})\b")

PERIODISERINGSFOND_KONTON = range(2110, 2150)

# Fältkoder i INK2S (SRU). 7667 för 4.6d kommer ur en sekundärkälla och ska
# stämmas av mot Skatteverkets fälttabell; resten bekräftas av iOrdnings filer.
FALT_4_3C = "7653"
FALT_4_5C = "7754"
FALT_4_6A = "7654"
FALT_4_6D = "7667"
OVERSTYRBARA_FALT = (FALT_4_3C, FALT_4_5C, FALT_4_6A, FALT_4_6D)


def kronor(ore: int) -> int:
    """Öre till hela kronor, vanlig avrundning (0,50 uppåt)."""
    return int((Decimal(ore) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def ar_ur_kontonamn(namn: str) -> Optional[int]:
    """Avsättningsåret i "Periodiseringsfond 2019" (beskattningsåret)."""
    m = _AR_I_NAMN.search(namn or "")
    return int(m.group(1)) if m else None


def upprakningsprocent(avsattningsar: int) -> Decimal:
    if avsattningsar < 2019:
        return Decimal("6")
    if avsattningsar <= 2020:
        return Decimal("4")
    return Decimal("0")


def ar_ej_avdragsgill(code: str, name: str) -> bool:
    return code in EJ_AVDRAGSGILLA_BAS or bool(_EJ_AVDRAGSGILL_NAMN.search(name or ""))


def ar_skattefri(code: str, name: str) -> bool:
    return code in SKATTEFRIA_BAS or bool(_SKATTEFRI_NAMN.search(name or ""))


@dataclass
class Justering:
    """Ett fält i INK2S med beräkning, eventuell ersättning och underlag."""

    code: str
    row: str
    label: str
    calculated: int  # kronor
    override: Optional[int] = None
    basis: str = ""
    sources: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def value(self) -> int:
        return self.calculated if self.override is None else self.override

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "row": self.row,
            "label": self.label,
            "value": self.value,
            "calculated": self.calculated,
            "override": self.override,
            "basis": self.basis,
            "sources": self.sources,
        }


@dataclass
class Periodiseringsfond:
    account: str
    name: str
    avsattningsar: Optional[int]
    opening: int  # öre, positivt = fondens storlek
    closing: int
    reversed: int  # öre återfört under året
    allocated: int  # öre avsatt under året

    def as_dict(self) -> Dict[str, Any]:
        return {
            "account": self.account,
            "name": self.name,
            "avsattningsar": self.avsattningsar,
            "opening": kronor(self.opening),
            "closing": kronor(self.closing),
            "reversed": kronor(self.reversed),
            "allocated": kronor(self.allocated),
        }


@dataclass
class Skatteberakning:
    adjustments: Dict[str, Justering]
    fonder: List[Periodiseringsfond]
    slr_percent: Optional[Decimal]
    slr_source: str
    ej_avdragsgilla_konton: List[str]
    skattefria_konton: List[str]
    warnings: List[str] = field(default_factory=list)


class TaxAdjustmentService:
    """Räknar fram INK2S-justeringarna för ett räkenskapsår."""

    def calculate(self, fiscal_year_id: str) -> Skatteberakning:
        from repositories.bokslut_inputs_repo import BokslutInputsRepository
        from repositories.opening_balance_repo import OpeningBalanceRepository
        from repositories.period_repo import PeriodRepository
        from services.opening_balance import OpeningBalanceService

        fy = PeriodRepository.get_fiscal_year(fiscal_year_id)
        if not fy:
            raise ValueError(f"Fiscal year {fiscal_year_id} not found")

        inputs = BokslutInputsRepository.current(fiscal_year_id)
        opening = OpeningBalanceService().balances(fiscal_year_id)
        movements = OpeningBalanceRepository.movements(fiscal_year_id)
        debit_credit = OpeningBalanceRepository.movement_sides(fiscal_year_id)
        names = _account_names()
        warnings: List[str] = []

        # ── 4.3c och 4.5c ──────────────────────────────────────────────
        ej_avdragsgilla = inputs.get("ink2s.ej_avdragsgilla_konton")
        if ej_avdragsgilla is None:
            ej_avdragsgilla = sorted(
                c
                for c in names
                if ar_ej_avdragsgill(c, names[c]) and not _is_tax_account(c)
            )
        skattefria = inputs.get("ink2s.skattefria_konton")
        if skattefria is None:
            skattefria = sorted(c for c in names if ar_skattefri(c, names[c]))

        def summa(konton: List[str], tecken: int) -> tuple[int, List[Dict]]:
            total = 0
            sources = []
            for code in konton:
                bal = movements.get(code, 0) * tecken
                if bal:
                    total += bal
                    sources.append(
                        {
                            "account": code,
                            "name": names.get(code, ""),
                            "value": kronor(bal),
                        }
                    )
            return total, sources

        ej_ore, ej_src = summa(ej_avdragsgilla, 1)
        fri_ore, fri_src = summa(skattefria, -1)

        # ── Periodiseringsfonder ─────────────────────────────────────────
        fonder: List[Periodiseringsfond] = []
        for n in PERIODISERINGSFOND_KONTON:
            code = str(n)
            ib = -opening.get(code, 0)
            debit, credit = debit_credit.get(code, (0, 0))
            if ib == 0 and debit == 0 and credit == 0:
                continue
            fonder.append(
                Periodiseringsfond(
                    account=code,
                    name=names.get(code, ""),
                    avsattningsar=ar_ur_kontonamn(names.get(code, "")),
                    opening=ib,
                    closing=ib - debit + credit,
                    reversed=debit,
                    allocated=credit,
                )
            )

        # 4.6a: statslåneräntan vid utgången av november året före det
        # kalenderår då beskattningsåret går ut -- för ett brutet år som
        # slutar 2025 alltså november 2024, inte året före startåret.
        start_year = fy.start_date.year
        rate_year = fy.end_date.year - 1
        slr: Optional[Decimal]
        if "ink2s.slr" in inputs:
            slr = Decimal(str(inputs["ink2s.slr"]))
            slr_source = "angiven"
        elif rate_year in STATSLANERANTA_NOVEMBER:
            slr = STATSLANERANTA_NOVEMBER[rate_year]
            slr_source = f"statslåneräntan 30 november {rate_year}"
        else:
            slr = None
            slr_source = "saknas"
        fond_ib = sum(f.opening for f in fonder)
        if slr is None:
            schablon_ore = 0
            if fond_ib:
                warnings.append(
                    f"Statslåneräntan för november {rate_year} saknas. "
                    "Ange den för att få schablonintäkten i 4.6a."
                )
        else:
            rate = max(slr, SLR_GOLV) / 100
            schablon_ore = int(
                (Decimal(fond_ib) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )

        # 4.6d
        uppr_ore = 0
        uppr_src: List[Dict] = []
        for f in fonder:
            if not f.reversed:
                continue
            if f.avsattningsar is None:
                warnings.append(
                    f"Konto {f.account} ({f.name}) har återförts men avsättningsåret "
                    "framgår inte av kontonamnet. Kontrollera uppräkning i 4.6d."
                )
                continue
            pct = upprakningsprocent(f.avsattningsar)
            if not pct:
                continue
            belopp = int(
                (Decimal(f.reversed) * pct / 100).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
            uppr_ore += belopp
            uppr_src.append(
                {
                    "account": f.account,
                    "name": f"{f.name}: {pct} % av {kronor(f.reversed)}",
                    "value": kronor(belopp),
                }
            )

        # 6-årsregeln
        for f in fonder:
            if f.avsattningsar and f.closing and start_year >= f.avsattningsar + 6:
                warnings.append(
                    f"{f.name or f.account} ska återföras senast beskattningsåret "
                    f"{f.avsattningsar + 6} men har {kronor(f.closing)} kr kvar."
                )

        adjustments = {
            FALT_4_3C: Justering(
                FALT_4_3C,
                "4.3c",
                "Andra bokförda kostnader som inte ska dras av",
                kronor(ej_ore),
                basis="Ej avdragsgilla konton: "
                + (", ".join(ej_avdragsgilla) or "inga"),
                sources=ej_src,
            ),
            FALT_4_5C: Justering(
                FALT_4_5C,
                "4.5c",
                "Andra bokförda intäkter som inte ska tas upp",
                kronor(fri_ore),
                basis="Skattefria konton: " + (", ".join(skattefria) or "inga"),
                sources=fri_src,
            ),
            FALT_4_6A: Justering(
                FALT_4_6A,
                "4.6a",
                "Schablonintäkt på periodiseringsfonder vid beskattningsårets ingång",
                kronor(schablon_ore),
                basis=(
                    f"{kronor(fond_ib)} kr × {max(slr, SLR_GOLV)} % ({slr_source})"
                    if slr is not None
                    else "statslåneräntan saknas"
                ),
                sources=[
                    {"account": f.account, "name": f.name, "value": kronor(f.opening)}
                    for f in fonder
                    if f.opening
                ],
            ),
            FALT_4_6D: Justering(
                FALT_4_6D,
                "4.6d",
                "Uppräknat belopp vid återföring av periodiseringsfond",
                kronor(uppr_ore),
                basis="6 % för fonder avsatta före 2019, 4 % för 2019–2020",
                sources=uppr_src,
            ),
        }
        for code in OVERSTYRBARA_FALT:
            key = f"ink2s.belopp.{code}"
            if key in inputs and inputs[key] is not None:
                adjustments[code].override = int(inputs[key])

        return Skatteberakning(
            adjustments=adjustments,
            fonder=fonder,
            slr_percent=slr,
            slr_source=slr_source,
            ej_avdragsgilla_konton=list(ej_avdragsgilla),
            skattefria_konton=list(skattefria),
            warnings=warnings,
        )


def beraknad_bolagsskatt(overskott_kr: int) -> int:
    """20,6 % av överskottet avrundat nedåt till helt hundratal kronor."""
    if overskott_kr <= 0:
        return 0
    underlag = (overskott_kr // 100) * 100
    return int(
        (Decimal(underlag) * BOLAGSSKATT).quantize(Decimal("1"), rounding=ROUND_FLOOR)
    )


def _is_tax_account(code: str) -> bool:
    return code.isdigit() and 8900 <= int(code) <= 8989


def _account_names() -> Dict[str, str]:
    from repositories.account_repo import AccountRepository

    return {a.code: a.name or "" for a in AccountRepository.list_all(active_only=False)}
