"""Årsredovisning för mindre aktiebolag enligt K2 (BFNAR 2016:10).

Resultaträkningen är kostnadsslagsindelad och balansräkningen följer
uppställningsformen i ÅRL bilaga 2/K2 kapitel 4–6; raderna härleds ur
BAS-kontoplanens intervall. Allt som inte går att läsa ur bokföringen
(verksamhetsbeskrivning, medeltal anställda, utdelning, underskrifter) hämtas
ur `bokslut_inputs` (services/bokslut_inputs.py). Saknas en uppgift som
årsredovisningen kräver står den i `missing`, och PDF:en markerar raden.

Belopp räknas i öre per rad och avrundas till hela kronor per rad. Summorna
är summor av de avrundade raderna, så att varje uppställning går ihop på
papperet; en differens mellan balansräkningens två sidor som uppstår av
avrundningen redovisas som en varning.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

Ranges = Sequence[Tuple[int, int]]

# Andelen av obeskattade reserver som räknas som eget kapital i soliditeten
# (1 - bolagsskatten 20,6 %).
EK_ANDEL_OBESKATTADE = Decimal("0.794")


def _ar_etikett(start: date, end: date) -> str:
    """`2025` för ett kalenderår, `2024/25` för ett brutet."""
    if start.year == end.year:
        return str(end.year)
    return f"{start.year}/{str(end.year)[2:]}"


@dataclass(frozen=True)
class Rad:
    key: str
    label: str
    ranges: Ranges
    note: Optional[str] = None


# ── Resultaträkning ───────────────────────────────────────────────────────
# Värdet är påverkan på resultatet: intäkter positiva, kostnader negativa.
RR_INTAKTER = (
    Rad("nettoomsattning", "Nettoomsättning", ((3000, 3799),)),
    Rad("aktiverat_arbete", "Aktiverat arbete för egen räkning", ((3800, 3899),)),
    Rad("ovriga_rorelseintakter", "Övriga rörelseintäkter", ((3900, 3999),)),
)
RR_KOSTNADER = (
    Rad("ravaror", "Råvaror och förnödenheter", ((4000, 4899),)),
    Rad("lagerforandring", "Förändring av lager", ((4900, 4999),)),
    Rad("ovriga_externa", "Övriga externa kostnader", ((5000, 6999),)),
    Rad("personal", "Personalkostnader", ((7000, 7699),), note="personal"),
    Rad(
        "avskrivningar",
        "Av- och nedskrivningar av materiella och immateriella anläggningstillgångar",
        ((7700, 7899),),
    ),
    Rad("ovriga_rorelsekostnader", "Övriga rörelsekostnader", ((7900, 7999),)),
)
RR_FINANSIELLA = (
    Rad("koncern", "Resultat från andelar i koncernföretag", ((8000, 8099),)),
    Rad("intresse", "Resultat från andelar i intresseföretag", ((8100, 8199),)),
    Rad(
        "ovriga_fin_anl",
        "Resultat från övriga finansiella anläggningstillgångar",
        ((8200, 8299),),
    ),
    Rad(
        "ranteintakter",
        "Övriga ränteintäkter och liknande resultatposter",
        ((8300, 8399),),
    ),
    Rad(
        "rantekostnader", "Räntekostnader och liknande resultatposter", ((8400, 8499),)
    ),
)
RR_DISPOSITIONER = (
    Rad(
        "periodiseringsfond",
        "Förändring av periodiseringsfonder",
        ((8810, 8819),),
        note="obeskattade",
    ),
    Rad("overavskrivningar", "Förändring av överavskrivningar", ((8850, 8859),)),
    Rad(
        "ovriga_dispositioner",
        "Övriga bokslutsdispositioner",
        ((8800, 8809), (8820, 8849), (8860, 8899)),
    ),
)
RR_SKATT = (Rad("skatt", "Skatt på årets resultat", ((8900, 8989),)),)

# ── Balansräkning ─────────────────────────────────────────────────────────
# Tillgångar debet positivt, eget kapital och skulder kredit positivt.
BR_ANLAGGNING = (
    (
        "Immateriella anläggningstillgångar",
        (Rad("immateriella", "Immateriella anläggningstillgångar", ((1000, 1099),)),),
    ),
    (
        "Materiella anläggningstillgångar",
        (
            Rad("byggnader", "Byggnader och mark", ((1100, 1199),)),
            Rad("inventarier", "Maskiner och inventarier", ((1200, 1299),)),
        ),
    ),
    (
        "Finansiella anläggningstillgångar",
        (
            Rad("andelar_koncern", "Andelar i koncernföretag", ((1310, 1319),)),
            Rad(
                "langfristiga_vp",
                "Andra långfristiga värdepappersinnehav",
                ((1350, 1359),),
            ),
            Rad(
                "langfristiga_fordringar",
                "Andra långfristiga fordringar",
                ((1300, 1309), (1320, 1349), (1360, 1399)),
            ),
        ),
    ),
)
BR_OMSATTNING = (
    ("Varulager m.m.", (Rad("varulager", "Varulager", ((1400, 1499),)),)),
    (
        "Kortfristiga fordringar",
        (
            Rad("kundfordringar", "Kundfordringar", ((1500, 1599),)),
            Rad("ovriga_fordringar", "Övriga fordringar", ((1600, 1699),)),
            Rad(
                "forutbetalda",
                "Förutbetalda kostnader och upplupna intäkter",
                ((1700, 1799),),
            ),
        ),
    ),
    (
        "Kortfristiga placeringar",
        (
            Rad(
                "kortfristiga_placeringar",
                "Övriga kortfristiga placeringar",
                ((1800, 1899),),
            ),
        ),
    ),
    ("Kassa och bank", (Rad("kassa_bank", "Kassa och bank", ((1900, 1999),)),)),
)
BR_BUNDET = (
    Rad("aktiekapital", "Aktiekapital", ((2080, 2084),)),
    Rad("uppskrivningsfond", "Uppskrivningsfond", ((2085, 2085),)),
    Rad("reservfond", "Reservfond", ((2086, 2089),)),
)
BR_FRITT = (Rad("balanserat", "Balanserat resultat", ((2090, 2098),)),)
BR_OBESKATTADE = (
    Rad("periodiseringsfonder", "Periodiseringsfonder", ((2110, 2149),)),
    Rad("overavskrivningar_br", "Ackumulerade överavskrivningar", ((2150, 2159),)),
    Rad(
        "ovriga_obeskattade",
        "Övriga obeskattade reserver",
        ((2100, 2109), (2160, 2199)),
    ),
)
BR_AVSATTNINGAR = (Rad("avsattningar", "Avsättningar", ((2200, 2299),)),)
BR_LANGFRISTIGA = (
    Rad("langfristiga_skulder", "Långfristiga skulder", ((2300, 2399),)),
)
BR_KORTFRISTIGA = (
    Rad("leverantorsskulder", "Leverantörsskulder", ((2440, 2449),)),
    Rad("skatteskulder", "Skatteskulder", ((2500, 2599),)),
    Rad(
        "ovriga_skulder",
        "Övriga skulder",
        ((2400, 2439), (2450, 2499), (2600, 2899)),
    ),
    Rad(
        "upplupna",
        "Upplupna kostnader och förutbetalda intäkter",
        ((2900, 2999),),
    ),
)

REDOVISNINGSPRINCIPER = (
    "Årsredovisningen har upprättats i enlighet med årsredovisningslagen och "
    "Bokföringsnämndens allmänna råd (BFNAR 2016:10) om årsredovisning i "
    "mindre företag (K2).",
    "Tillgångar och skulder har värderats till anskaffningsvärde respektive "
    "nominellt värde om inget annat anges. Fordringar har tagits upp till det "
    "belopp som efter individuell bedömning beräknas bli betalt.",
    "Inkomster och utgifter har periodiserats enligt god redovisningssed.",
)


def kr(ore: int) -> int:
    return int((Decimal(ore) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _in(code: str, ranges: Ranges) -> bool:
    if not code.isdigit():
        return False
    n = int(code)
    return any(lo <= n <= hi for lo, hi in ranges)


def _sum(balances: Dict[str, int], ranges: Ranges) -> int:
    return sum(v for c, v in balances.items() if _in(c, ranges))


@dataclass
class Arsdata:
    """Saldon för ett år: balanskonton vid utgång, resultatkonton för året."""

    start: date
    end: date
    closing: Dict[str, int]  # öre, debet positivt, balanskonton
    result: Optional[Dict[str, int]]  # öre, debet positivt, resultatkonton

    @property
    def unclosed_result(self) -> int:
        """Resultat som ännu inte förts till 2099 (kredit positivt)."""
        if not self.result:
            return 0
        return -sum(v for c, v in self.result.items() if _in(c, ((3000, 8999),)))


class ArsredovisningService:
    def build(self, fiscal_year_id: str) -> Dict[str, Any]:
        from repositories.bokslut_inputs_repo import BokslutInputsRepository
        from repositories.period_repo import PeriodRepository
        from services.pdf_export import CompanyInfo

        fy = PeriodRepository.get_fiscal_year(fiscal_year_id)
        if not fy:
            raise ValueError(f"Fiscal year {fiscal_year_id} not found")
        years = sorted(PeriodRepository.list_fiscal_years(), key=lambda y: y.start_date)
        prev = next(
            (y for y in years if y.end_date == fy.start_date - timedelta(days=1)), None
        )
        # De två räkenskapsåren före föregående år, för flerårsöversikten
        # (K2: räkenskapsåret och de tre föregående).
        earlier: List[Any] = []
        link = prev
        while link is not None and len(earlier) < 2:
            start = link.start_date
            link = next(
                (y for y in years if y.end_date == start - timedelta(days=1)), None
            )
            if link is not None:
                earlier.append(link)

        inputs = BokslutInputsRepository.current(fiscal_year_id)
        carried = BokslutInputsRepository.current(prev.id) if prev else {}
        company = CompanyInfo.load()

        cur = self._year(fy.id, fy.start_date, fy.end_date)
        prior = (
            self._year(prev.id, prev.start_date, prev.end_date)
            if prev
            else Arsdata(
                start=date(
                    fy.start_date.year - 1, fy.start_date.month, fy.start_date.day
                ),
                end=fy.start_date - timedelta(days=1),
                closing=self._opening(fy.id),
                result=None,
            )
        )

        warnings: List[str] = []
        missing: List[Dict[str, str]] = []

        rr = self._resultatrakning(cur, prior)
        br = self._balansrakning(cur, prior)
        if br["summa_tillgangar"][0] != br["summa_ek_skulder"][0]:
            warnings.append(
                "Balansräkningens två sidor skiljer sig åt med "
                f"{br['summa_tillgangar'][0] - br['summa_ek_skulder'][0]} kr "
                "efter avrundning till hela kronor."
            )
        if rr["arets_resultat"][0] != br["arets_resultat"][0]:
            warnings.append(
                "Årets resultat i resultaträkningen "
                f"({rr['arets_resultat'][0]} kr) skiljer sig från balansräkningen "
                f"({br['arets_resultat'][0]} kr) efter avrundning."
            )
        for label in br["omklassificerade"]:
            warnings.append(
                f"{label} har debetsaldo och redovisas under Övriga fordringar."
            )
        for side in ("skulder_negativa",):
            for label in br.get(side, []):
                warnings.append(
                    f"{label} har debetsaldo och borde redovisas som fordran."
                )
        if prior.result is None:
            warnings.append(
                "Föregående räkenskapsår finns inte i Bok, så resultaträkningens "
                "jämförelsetal saknas. De kan anges som uppgift."
            )
            jmf = inputs.get("ar.jamforelse_rr") or {}
            for section in rr["sektioner"]:
                for row in section["rader"]:
                    if row["key"] in jmf:
                        row["belopp"][1] = int(jmf[row["key"]])

        def text(key: str, label: str, required: bool = True) -> Optional[Any]:
            if key in inputs:
                return inputs[key]
            if key in carried:
                return carried[key]
            if required:
                missing.append({"key": key, "label": label})
            return None

        verksamhet = text("ar.verksamhet", "Verksamhetens art och inriktning")
        handelser = text(
            "ar.vasentliga_handelser", "Väsentliga händelser", required=False
        )
        anstallda = inputs.get("ar.medeltal_anstallda")
        if anstallda is None:
            missing.append(
                {"key": "ar.medeltal_anstallda", "label": "Medelantal anställda"}
            )
        anstallda_prior = inputs.get(
            "ar.medeltal_anstallda_fg", carried.get("ar.medeltal_anstallda")
        )
        underskrifter = text("ar.underskrifter", "Underskrifter (namn och roll)") or []
        ort = (
            inputs.get("ar.ort")
            or carried.get("ar.ort")
            or company.seat
            or company.postort
        )
        if not ort:
            missing.append({"key": "ar.ort", "label": "Ort för underskrift"})
        datum = inputs.get("ar.datum")
        if not datum:
            missing.append({"key": "ar.datum", "label": "Datum för underskrift"})

        # Förslag till vinstdisposition
        fritt = br["fritt_eget_kapital"][0]
        utdelning = inputs.get("ar.utdelning")
        if utdelning is None:
            missing.append({"key": "ar.utdelning", "label": "Föreslagen utdelning"})
            utdelning = 0
        if utdelning > fritt:
            warnings.append(
                f"Föreslagen utdelning ({utdelning} kr) är större än fritt eget "
                f"kapital ({fritt} kr)."
            )
        balanserat_ub = br["rader_index"]["balanserat"][0]
        vinstdisposition = {
            "balanserat_resultat": balanserat_ub,
            "arets_resultat": br["arets_resultat"][0],
            "summa": fritt,
            "utdelning": utdelning,
            "i_ny_rakning": fritt - utdelning,
        }

        earliest = earlier[-1] if earlier else prev
        flerar = self._flerarsoversikt(
            [(cur, br, rr, 0), (prior, br, rr, 1)],
            earlier,
            inputs.get("ar.flerarsoversikt") or {},
            earliest_opening=self._opening(earliest.id) if earliest else None,
        )

        ek_forandring = self._eget_kapital_forandring(cur, prior)

        fonder = []
        for code in sorted(
            {c for c in {**cur.closing, **prior.closing} if _in(c, ((2110, 2149),))}
        ):
            a, b = -cur.closing.get(code, 0), -prior.closing.get(code, 0)
            if a or b:
                fonder.append(
                    {
                        "account": code,
                        "name": self._names().get(code, code),
                        "belopp": [kr(a), kr(b)],
                    }
                )

        personal = {
            "medeltal_anstallda": [anstallda, anstallda_prior],
            "loner": [
                kr(_sum(cur.result or {}, ((7000, 7399),))),
                kr(_sum(prior.result, ((7000, 7399),))) if prior.result else None,
            ],
            "sociala": [
                kr(_sum(cur.result or {}, ((7400, 7599),))),
                kr(_sum(prior.result, ((7400, 7599),))) if prior.result else None,
            ],
        }

        return {
            "fiscal_year_id": fy.id,
            "company": {
                "name": company.name,
                "org_number": company.org_number,
                "seat": company.seat,
            },
            "period": {
                "start": fy.start_date.isoformat(),
                "end": fy.end_date.isoformat(),
            },
            "prior_period": {
                "start": prior.start.isoformat(),
                "end": prior.end.isoformat(),
            },
            "forvaltningsberattelse": {
                "verksamhet": verksamhet,
                "vasentliga_handelser": handelser,
                "flerarsoversikt": flerar,
                "eget_kapital": ek_forandring,
                "vinstdisposition": vinstdisposition,
            },
            "resultatrakning": {k: v for k, v in rr.items() if k != "rader_index"},
            "balansrakning": {
                k: v
                for k, v in br.items()
                if k not in ("rader_index", "skulder_negativa", "omklassificerade")
            },
            "noter": {
                "redovisningsprinciper": list(REDOVISNINGSPRINCIPER),
                "personal": personal,
                "periodiseringsfonder": fonder,
                "stallda_sakerheter": inputs.get("ar.stallda_sakerheter", "Inga"),
                "eventualforpliktelser": inputs.get("ar.eventualforpliktelser", "Inga"),
            },
            "underskrifter": {"ort": ort, "datum": datum, "personer": underskrifter},
            "faststallelseintyg": {
                "stamma_datum": inputs.get("ar.stamma_datum"),
                "intygare": inputs.get("ar.intygare")
                or (underskrifter[0]["namn"] if underskrifter else None),
                "beslut": inputs.get(
                    "ar.stamma_beslut",
                    "Årsstämman beslutade att godkänna styrelsens förslag till vinstdisposition.",
                ),
            },
            "missing": missing,
            "warnings": warnings,
        }

    # ── Data ───────────────────────────────────────────────────────────────

    def _names(self) -> Dict[str, str]:
        if not hasattr(self, "_name_cache"):
            from repositories.account_repo import AccountRepository

            self._name_cache = {
                a.code: a.name or ""
                for a in AccountRepository.list_all(active_only=False)
            }
        return self._name_cache

    def _opening(self, fiscal_year_id: str) -> Dict[str, int]:
        from services.opening_balance import OpeningBalanceService, is_balance_account

        return {
            c: v
            for c, v in OpeningBalanceService().balances(fiscal_year_id).items()
            if is_balance_account(c)
        }

    def _year(self, fiscal_year_id: str, start: date, end: date) -> Arsdata:
        from repositories.opening_balance_repo import OpeningBalanceRepository
        from services.opening_balance import is_balance_account

        opening = self._opening(fiscal_year_id)
        movements = OpeningBalanceRepository.movements(fiscal_year_id)
        closing = dict(opening)
        result: Dict[str, int] = {}
        for code, net in movements.items():
            if is_balance_account(code):
                closing[code] = closing.get(code, 0) + net
            else:
                result[code] = net
        return Arsdata(start=start, end=end, closing=closing, result=result)

    # ── Uppställningar ─────────────────────────────────────────────────────

    def _rows(
        self, rader: Sequence[Rad], years: Sequence[Optional[Dict[str, int]]], sign: int
    ) -> List[Dict[str, Any]]:
        out = []
        for rad in rader:
            belopp = [
                None if y is None else kr(sign * _sum(y, rad.ranges)) for y in years
            ]
            if all(not b for b in belopp):
                continue
            out.append(
                {"key": rad.key, "label": rad.label, "not": rad.note, "belopp": belopp}
            )
        return out

    @staticmethod
    def _total(rows: List[Dict[str, Any]], i: int) -> Optional[int]:
        values = [r["belopp"][i] for r in rows]
        if any(v is None for v in values) and rows:
            return None
        return sum(v for v in values if v is not None)

    def _resultatrakning(self, cur: Arsdata, prior: Arsdata) -> Dict[str, Any]:
        ys = [cur.result or {}, prior.result]
        intakter = self._rows(RR_INTAKTER, ys, -1)
        kostnader = self._rows(RR_KOSTNADER, ys, -1)
        finansiella = self._rows(RR_FINANSIELLA, ys, -1)
        dispositioner = self._rows(RR_DISPOSITIONER, ys, -1)
        skatt = self._rows(RR_SKATT, ys, -1)

        def add(*parts: Optional[int]) -> Optional[int]:
            return None if any(p is None for p in parts) else sum(parts)  # type: ignore[arg-type]

        tot = {}
        for i in (0, 1):
            ti = self._total(intakter, i) or 0 if ys[i] is not None else None
            tk = self._total(kostnader, i) or 0 if ys[i] is not None else None
            tf = self._total(finansiella, i) or 0 if ys[i] is not None else None
            td = self._total(dispositioner, i) or 0 if ys[i] is not None else None
            ts = self._total(skatt, i) or 0 if ys[i] is not None else None
            tot[i] = {
                "intakter": ti,
                "kostnader": tk,
                "rorelseresultat": add(ti, tk),
                "efter_finansiella": add(ti, tk, tf),
                "fore_skatt": add(ti, tk, tf, td),
                "arets_resultat": add(ti, tk, tf, td, ts),
            }
        pair = lambda k: [tot[0][k], tot[1][k]]  # noqa: E731
        return {
            "sektioner": [
                {
                    "titel": "Rörelsens intäkter m.m.",
                    "rader": intakter,
                    "summa": pair("intakter"),
                },
                {
                    "titel": "Rörelsens kostnader",
                    "rader": kostnader,
                    "summa": pair("kostnader"),
                },
                {
                    "titel": "Rörelseresultat",
                    "rader": [],
                    "summa": pair("rorelseresultat"),
                },
                {"titel": "Finansiella poster", "rader": finansiella, "summa": None},
                {
                    "titel": "Resultat efter finansiella poster",
                    "rader": [],
                    "summa": pair("efter_finansiella"),
                },
                {
                    "titel": "Bokslutsdispositioner",
                    "rader": dispositioner,
                    "summa": None,
                },
                {
                    "titel": "Resultat före skatt",
                    "rader": [],
                    "summa": pair("fore_skatt"),
                },
                {"titel": "Skatter", "rader": skatt, "summa": None},
            ],
            "nettoomsattning": [
                (
                    next(
                        (
                            r["belopp"][i]
                            for r in intakter
                            if r["key"] == "nettoomsattning"
                        ),
                        0,
                    )
                    if ys[i] is not None
                    else None
                )
                for i in (0, 1)
            ],
            "efter_finansiella": pair("efter_finansiella"),
            "arets_resultat": pair("arets_resultat"),
        }

    def _balansrakning(self, cur: Arsdata, prior: Arsdata) -> Dict[str, Any]:
        ys = [dict(cur.closing), dict(prior.closing)]
        index: Dict[str, List[Optional[int]]] = {}
        # En skatte- eller momsskuld med debetsaldo är en fordran (K2 2.x:
        # tillgångar och skulder kvittas inte). Raden flyttas till Övriga
        # fordringar genom ett par motposter i den här beräkningens saldon.
        omklassade: List[str] = []
        for y in ys:
            for ranges, offset, label in (
                (((2500, 2599),), "2599", "Skatteskulder"),
                (((2600, 2699),), "2699", "Momsskuld"),
            ):
                net = _sum(y, ranges)
                if net > 0:
                    y[offset] = y.get(offset, 0) - net
                    y["1600"] = y.get("1600", 0) + net
                    if label not in omklassade:
                        omklassade.append(label)

        def grupper(defs, sign):
            out = []
            for titel, rader in defs:
                rows = self._rows(rader, ys, sign)
                for r in rows:
                    index[r["key"]] = r["belopp"]
                if rows:
                    out.append(
                        {
                            "titel": titel,
                            "rader": rows,
                            "summa": [self._total(rows, 0), self._total(rows, 1)],
                        }
                    )
            return out

        anl = grupper(BR_ANLAGGNING, 1)
        oms = grupper(BR_OMSATTNING, 1)
        s_anl = [sum(g["summa"][i] for g in anl) for i in (0, 1)]
        s_oms = [sum(g["summa"][i] for g in oms) for i in (0, 1)]
        tillgangar = [s_anl[i] + s_oms[i] for i in (0, 1)]

        bundet = self._rows(BR_BUNDET, ys, -1)
        fritt = self._rows(BR_FRITT, ys, -1)
        arets = [
            kr(-cur.closing.get("2099", 0) + cur.unclosed_result),
            kr(-prior.closing.get("2099", 0) + prior.unclosed_result),
        ]
        if not any(r["key"] == "balanserat" for r in fritt):
            fritt.insert(
                0,
                {
                    "key": "balanserat",
                    "label": "Balanserat resultat",
                    "not": None,
                    "belopp": [0, 0],
                },
            )
        fritt.append(
            {
                "key": "arets_resultat",
                "label": "Årets resultat",
                "not": None,
                "belopp": arets,
            }
        )
        for r in bundet + fritt:
            index[r["key"]] = r["belopp"]
        s_bundet = [self._total(bundet, i) or 0 for i in (0, 1)]
        s_fritt = [self._total(fritt, i) or 0 for i in (0, 1)]
        ek = [s_bundet[i] + s_fritt[i] for i in (0, 1)]

        obeskattade = self._rows(BR_OBESKATTADE, ys, -1)
        for r in obeskattade:
            if r["key"] == "periodiseringsfonder":
                r["not"] = "obeskattade"
        avs = self._rows(BR_AVSATTNINGAR, ys, -1)
        lang = self._rows(BR_LANGFRISTIGA, ys, -1)
        kort = self._rows(BR_KORTFRISTIGA, ys, -1)
        negativa = [r["label"] for r in kort if (r["belopp"][0] or 0) < 0]
        s = lambda rows: [self._total(rows, i) or 0 for i in (0, 1)]  # noqa: E731
        s_obesk, s_avs, s_lang, s_kort = s(obeskattade), s(avs), s(lang), s(kort)
        ek_skulder = [
            ek[i] + s_obesk[i] + s_avs[i] + s_lang[i] + s_kort[i] for i in (0, 1)
        ]

        skuldsektioner = [
            {"titel": "Obeskattade reserver", "rader": obeskattade, "summa": s_obesk},
            {"titel": "Avsättningar", "rader": avs, "summa": s_avs},
            {"titel": "Långfristiga skulder", "rader": lang, "summa": s_lang},
            {"titel": "Kortfristiga skulder", "rader": kort, "summa": s_kort},
        ]
        return {
            "tillgangar": [
                {"titel": "Anläggningstillgångar", "grupper": anl, "summa": s_anl},
                {"titel": "Omsättningstillgångar", "grupper": oms, "summa": s_oms},
            ],
            "summa_tillgangar": tillgangar,
            "eget_kapital": {
                "bundet": {"rader": bundet, "summa": s_bundet},
                "fritt": {"rader": fritt, "summa": s_fritt},
                "summa": ek,
            },
            "skulder": [x for x in skuldsektioner if x["rader"]],
            "summa_ek_skulder": ek_skulder,
            "fritt_eget_kapital": s_fritt,
            "obeskattade_reserver": s_obesk,
            "arets_resultat": arets,
            "rader_index": index,
            "skulder_negativa": negativa,
            "omklassificerade": omklassade,
        }

    #: K2: flerårsöversikten visar räkenskapsåret och de tre föregående.
    FLERAR_ANTAL = 4

    def _flerarsoversikt(
        self, years, earlier, manual: Dict[str, Any], earliest_opening=None
    ) -> List[Dict[str, Any]]:
        """Räkenskapsåret och de tre föregående. `years` är (data, br, rr, i)
        för de två år balans- och resultaträkningen redan har räknat,
        `earlier` de räkenskapsår i Bok som kommer före dem (nyast först).
        Året före det äldsta räkenskapsåret får sin balansräkning ur dess
        ingående balans. År som inte finns i Bok fylls ur `manual`."""
        out = [self._flerar_rad(data, br, rr, i) for data, br, rr, i in years]
        last = years[-1][0]
        for fy in earlier:
            if len(out) >= self.FLERAR_ANTAL:
                break
            last = self._year(fy.id, fy.start_date, fy.end_date)
            sub = self._balansrakning(last, last)
            subrr = self._resultatrakning(last, last)
            out.append(self._flerar_rad(last, sub, subrr, 0))
        if len(out) < self.FLERAR_ANTAL and earliest_opening is not None:
            # Året finns inte som räkenskapsår, men dess balansräkning är
            # det äldsta räkenskapsårets ingående balans.
            last = Arsdata(
                start=date(last.start.year - 1, last.start.month, last.start.day),
                end=last.start - timedelta(days=1),
                closing=earliest_opening,
                result=None,
            )
            sub = self._balansrakning(last, last)
            subrr = self._resultatrakning(last, last)
            out.append(self._flerar_rad(last, sub, subrr, 0))
        while len(out) < self.FLERAR_ANTAL:
            start = date(last.start.year - 1, last.start.month, last.start.day)
            end = last.start - timedelta(days=1)
            last = Arsdata(start=start, end=end, closing={}, result=None)
            out.append(
                {
                    "ar": _ar_etikett(start, end),
                    "nettoomsattning": None,
                    "resultat_efter_finansiella": None,
                    "balansomslutning": None,
                    "soliditet": None,
                }
            )
        for row in out:
            for k, v in (manual.get(row["ar"]) or {}).items():
                if row.get(k) is None:
                    row[k] = v
        return out

    @staticmethod
    def _flerar_rad(data, br, rr, i) -> Dict[str, Any]:
        omslutning = br["summa_tillgangar"][i]
        ek = br["eget_kapital"]["summa"][i]
        obesk = br["obeskattade_reserver"][i]
        soliditet = (
            round(
                float(
                    (Decimal(ek) + Decimal(obesk) * EK_ANDEL_OBESKATTADE)
                    / Decimal(omslutning)
                    * 100
                )
            )
            if omslutning
            else None
        )
        return {
            "ar": _ar_etikett(data.start, data.end),
            "nettoomsattning": rr["nettoomsattning"][i],
            "resultat_efter_finansiella": rr["efter_finansiella"][i],
            "balansomslutning": omslutning,
            "soliditet": soliditet,
        }

    def _eget_kapital_forandring(self, cur: Arsdata, prior: Arsdata) -> Dict[str, Any]:
        def g(bal, ranges):
            return kr(-_sum(bal, ranges))

        ak_ib = g(prior.closing, ((2080, 2089),))
        ak_ub = g(cur.closing, ((2080, 2089),))
        bal_ib = g(prior.closing, ((2090, 2098),))
        res_ib = kr(-prior.closing.get("2099", 0) + prior.unclosed_result)
        bal_ub = g(cur.closing, ((2090, 2098),))
        res_ub = kr(-cur.closing.get("2099", 0) + cur.unclosed_result)
        # Det som inte är föregående års resultat är utdelning (eller annan
        # förändring av det fria egna kapitalet).
        ovrigt = bal_ub - (bal_ib + res_ib)
        rader: List[Dict[str, Any]] = [
            {"label": "Belopp vid årets ingång", "belopp": [ak_ib, bal_ib, res_ib]},
            {"label": "Disposition enligt årsstämman", "belopp": [0, res_ib, -res_ib]},
        ]
        if ovrigt:
            rader.append(
                {
                    "label": "Utdelning" if ovrigt < 0 else "Övriga förändringar",
                    "belopp": [0, ovrigt, 0],
                }
            )
        if ak_ub != ak_ib:
            rader.append(
                {
                    "label": "Förändring av bundet eget kapital",
                    "belopp": [ak_ub - ak_ib, 0, 0],
                }
            )
        rader.append({"label": "Årets resultat", "belopp": [0, 0, res_ub]})
        rader.append(
            {"label": "Belopp vid årets utgång", "belopp": [ak_ub, bal_ub, res_ub]}
        )
        for r in rader:
            r["belopp"].append(sum(r["belopp"]))
        return {
            "kolumner": [
                "Bundet eget kapital",
                "Balanserat resultat",
                "Årets resultat",
                "Totalt",
            ],
            "rader": rader,
        }


def build_arsredovisning(fiscal_year_id: str) -> Dict[str, Any]:
    return ArsredovisningService().build(fiscal_year_id)


def _context(report: Dict[str, Any]) -> Dict[str, Any]:
    notnr: Dict[str, Any] = {"principer": 1, "personal": 2}
    nr = 3
    if report["noter"]["periodiseringsfonder"]:
        notnr["obeskattade"] = nr
        nr += 1
    notnr["sakerheter"] = nr
    roller = " ".join(
        p.get("roll", "") for p in report["underskrifter"]["personer"]
    ).lower()
    return {
        "r": report,
        "notnr": notnr,
        "tkr": lambda v: (
            None
            if v is None
            else int((Decimal(v) / 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        ),
        "any_vd": "verkställande" in roller or "vd" in roller.split(),
    }


def render_arsredovisning_pdf(fiscal_year_id: str) -> Tuple[bytes, Dict[str, Any]]:
    from services.pdf_export import PDFEngine

    report = build_arsredovisning(fiscal_year_id)
    return PDFEngine().render_pdf("arsredovisning.html", _context(report)), report


def render_arsredovisning_html(fiscal_year_id: str) -> str:
    from services.pdf_export import PDFEngine

    return PDFEngine().render_html(
        "arsredovisning.html", _context(build_arsredovisning(fiscal_year_id))
    )


def render_faststallelseintyg_pdf(fiscal_year_id: str) -> Tuple[bytes, Dict[str, Any]]:
    from services.pdf_export import PDFEngine

    report = build_arsredovisning(fiscal_year_id)
    return PDFEngine().render_pdf("faststallelseintyg.html", _context(report)), report
