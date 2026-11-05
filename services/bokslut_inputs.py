"""Uppgifter till bokslutet som inte står i bokföringen (migration 046).

Varje nyckel har en typ som kontrolleras innan något skrivs. En ändring är en
ny rad; `None` tar bort uppgiften. Både agenten och en inloggad människa får
skriva: uppgifterna är underlag till årsredovisningen och deklarationen, inte
räkenskapsinformation, och varje ändring står kvar med vem som gjorde den.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable, Dict, List, Mapping

from domain.validation import ValidationError

_DATUM = re.compile(r"\d{4}-\d{2}-\d{2}")
_KONTO = re.compile(r"\d{4}")


def _text(v: Any) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError("ska vara en text")
    return v.strip()


def _datum(v: Any) -> str:
    v = _text(v)
    if not _DATUM.fullmatch(v):
        raise ValueError("ska vara ett datum ÅÅÅÅ-MM-DD")
    date.fromisoformat(v)
    return v


def _heltal(minimum: int | None = 0) -> Callable[[Any], int]:
    def check(v: Any) -> int:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
            raise ValueError("ska vara ett heltal")
        if minimum is not None and v < minimum:
            raise ValueError(f"får inte vara mindre än {minimum}")
        return int(v)

    return check


def _procent(v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError("ska vara en procentsats")
    if not -5 <= v <= 20:
        raise ValueError("ska vara en procentsats mellan -5 och 20")
    return float(v)


def _konton(v: Any) -> List[str]:
    if not isinstance(v, list) or not all(
        isinstance(x, str) and _KONTO.fullmatch(x) for x in v
    ):
        raise ValueError("ska vara en lista med fyrsiffriga kontonummer")
    return sorted(set(v))


def _underskrifter(v: Any) -> List[Dict[str, str]]:
    if not isinstance(v, list) or not v:
        raise ValueError("ska vara en lista med namn och roll")
    out = []
    for p in v:
        if not isinstance(p, dict):
            raise ValueError("varje underskrift ska ha namn och roll")
        out.append({"namn": _text(p.get("namn")), "roll": _text(p.get("roll"))})
    return out


def _upplysningar(v: Any) -> Dict[str, bool]:
    if not isinstance(v, dict) or not set(v) <= {"uppdragstagare", "revision"}:
        raise ValueError("ska ange uppdragstagare och revision som ja/nej")
    return {k: bool(v.get(k, False)) for k in ("uppdragstagare", "revision")}


def _objekt(v: Any) -> Dict[str, Any]:
    if not isinstance(v, dict):
        raise ValueError("ska vara ett objekt")
    return v


KEYS: Dict[str, tuple[str, Callable[[Any], Any]]] = {
    "ar.verksamhet": ("Verksamhetens art och inriktning", _text),
    "ar.vasentliga_handelser": ("Väsentliga händelser under året", _text),
    "ar.medeltal_anstallda": ("Medelantal anställda", _heltal()),
    "ar.medeltal_anstallda_fg": ("Medelantal anställda föregående år", _heltal()),
    "ar.utdelning": ("Föreslagen utdelning (kr)", _heltal()),
    "ar.ort": ("Ort för underskrift", _text),
    "ar.datum": ("Datum för underskrift", _datum),
    "ar.underskrifter": ("Underskrifter", _underskrifter),
    "ar.stamma_datum": ("Datum för årsstämman", _datum),
    "ar.intygare": ("Den som skriver under fastställelseintyget", _text),
    "ar.stamma_beslut": ("Stämmans beslut om vinstdisposition", _text),
    "ar.stallda_sakerheter": ("Ställda säkerheter", _text),
    "ar.eventualforpliktelser": ("Eventualförpliktelser", _text),
    "ar.flerarsoversikt": ("Flerårsöversikt för år som saknas i Bok", _objekt),
    "ar.jamforelse_rr": ("Resultaträkningens jämförelsetal", _objekt),
    "ink2s.slr": ("Statslåneräntan i november året före (%)", _procent),
    "ink2s.ej_avdragsgilla_konton": ("Ej avdragsgilla konton (4.3c)", _konton),
    "ink2s.skattefria_konton": ("Skattefria konton (4.5c)", _konton),
    "ink2s.upplysningar": ("Upplysningar om årsredovisningen", _upplysningar),
    "ink2s.belopp.7653": ("4.3c angivet belopp", _heltal(None)),
    "ink2s.belopp.7754": ("4.5c angivet belopp", _heltal(None)),
    "ink2s.belopp.7654": ("4.6a angivet belopp", _heltal(None)),
    "ink2s.belopp.7667": ("4.6d angivet belopp", _heltal(None)),
}


class BokslutInputsService:
    def current(self, fiscal_year_id: str) -> Dict[str, Any]:
        from repositories.bokslut_inputs_repo import BokslutInputsRepository

        return BokslutInputsRepository.current(fiscal_year_id)

    def history(self, fiscal_year_id: str) -> List[Dict[str, Any]]:
        from repositories.bokslut_inputs_repo import BokslutInputsRepository

        return BokslutInputsRepository.history(fiscal_year_id)

    def set_values(
        self, fiscal_year_id: str, values: Mapping[str, Any], actor: str
    ) -> Dict[str, Any]:
        from db.database import db
        from repositories.audit_repo import AuditRepository
        from repositories.bokslut_inputs_repo import BokslutInputsRepository
        from repositories.period_repo import PeriodRepository

        if not PeriodRepository.get_fiscal_year(fiscal_year_id):
            raise ValidationError("fiscal_year_not_found", "Fiscal year not found")
        if not values:
            raise ValidationError("bokslut_inputs_empty", "Inga uppgifter angavs")

        clean: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        for key, value in values.items():
            if key not in KEYS:
                errors[key] = "okänd uppgift"
                continue
            if value is None:
                clean[key] = None
                continue
            try:
                clean[key] = KEYS[key][1](value)
            except ValueError as exc:
                errors[key] = f"{KEYS[key][0]} {exc}"
        if errors:
            raise ValidationError(
                "bokslut_inputs_invalid",
                "Uppgifterna kunde inte sparas",
                details="; ".join(f"{k}: {v}" for k, v in errors.items()),
                payload={"errors": errors},
            )

        current = BokslutInputsRepository.current(fiscal_year_id)
        changed = {k: v for k, v in clean.items() if current.get(k) != v}
        for key, value in changed.items():
            BokslutInputsRepository.append(fiscal_year_id, key, value, actor)
        if changed:
            AuditRepository.log(
                entity_type="bokslut_inputs",
                entity_id=fiscal_year_id,
                action="updated",
                actor=actor,
                payload={"values": changed},
                _commit=False,
            )
        db.commit()
        return BokslutInputsRepository.current(fiscal_year_id)


def schema() -> List[Dict[str, str]]:
    return [{"key": k, "label": label} for k, (label, _) in KEYS.items()]
