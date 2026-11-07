"""Bokslutet för ett räkenskapsår: blanketter, årsredovisning och kontroller.

Samlar det som annars ligger i fyra tjänster -- INK2 (services/ink2_declaration
och services/sru_export), momsdeklarationen (services/vat_report),
årsredovisningen (services/arsredovisning) och skatteberäkningen
(services/tax_adjustments) -- till en översikt per år, med de kontroller som
ska vara gröna innan blanketterna laddas upp och årsredovisningen skrivs ut.

Inget här bokför. Kontrollerna pekar på det som saknas (momsavstämning,
bolagsskatt, resultat mot 2099); verifikationerna bokförs som vanligt.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any, Dict, List, Tuple

OK, INFO, VARNING, FEL = "ok", "info", "varning", "fel"


def _kontroll(id_: str, niva: str, titel: str, text: str = "") -> Dict[str, str]:
    return {"id": id_, "niva": niva, "titel": titel, "text": text}


def _filnamn(namn: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", namn).strip("_") or "bolag"


class BokslutService:
    def _fiscal_year(self, fiscal_year_id: str):
        from repositories.period_repo import PeriodRepository

        fy = PeriodRepository.get_fiscal_year(fiscal_year_id)
        if not fy:
            raise ValueError(f"Fiscal year {fiscal_year_id} not found")
        return fy

    # ── Översikt ───────────────────────────────────────────────────────────

    def overview(self, fiscal_year_id: str) -> Dict[str, Any]:
        from services.arsredovisning import build_arsredovisning
        from services.bokslut_inputs import BokslutInputsService, schema
        from services.ink2_declaration import INK2DeclarationService
        from services.sru_export import SRUExportService
        from services.tax_adjustments import beraknad_bolagsskatt, kronor
        from services.vat_report import VatReportService

        fy = self._fiscal_year(fiscal_year_id)

        sru = SRUExportService()
        declaration = sru.calculate_sru_fields(fiscal_year_id)
        tax = sru.tax_calculation
        ink2 = INK2DeclarationService().build(fiscal_year_id)

        vat_service = VatReportService()
        vat = vat_service.format_skv_summary(
            vat_service.preview_for_dates(fy.start_date, fy.end_date)
        )
        ar = build_arsredovisning(fiscal_year_id)

        overskott = declaration.get_field_value("7670")
        underskott = declaration.get_field_value("7770")
        bokford_skatt = kronor(self._movement(fiscal_year_id, ((8910, 8919),)))
        beraknad = beraknad_bolagsskatt(overskott)
        # 8811 debiteras vid avsättning: rörelsen (debet minus kredit) är
        # avsättningen som ett positivt belopp. Taket räknas på överskottet
        # före årets avsättning, som redan är avdragen i 7670.
        avsatt = kronor(self._movement(fiscal_year_id, ((8811, 8811),)))
        max_avsattning = max(0, (overskott + avsatt) * 25 // 100)

        skatt = {
            "overskott": overskott,
            "underskott": underskott,
            "underlag": (overskott // 100) * 100,
            "beraknad_skatt": beraknad,
            "bokford_skatt": bokford_skatt,
            "differens": bokford_skatt - beraknad,
            "slr_procent": None if tax.slr_percent is None else float(tax.slr_percent),
            "slr_kalla": tax.slr_source,
            "justeringar": [a.as_dict() for a in tax.adjustments.values()],
            "periodiseringsfonder": [f.as_dict() for f in tax.fonder],
            "max_avsattning_periodiseringsfond": max_avsattning,
            "bokford_avsattning": avsatt,
            "ej_avdragsgilla_konton": tax.ej_avdragsgilla_konton,
            "skattefria_konton": tax.skattefria_konton,
        }

        kontroller = self._kontroller(
            fiscal_year_id, fy, declaration, sru, vat, ar, skatt
        )

        return {
            "fiscal_year": {
                "id": fy.id,
                "start": fy.start_date.isoformat(),
                "end": fy.end_date.isoformat(),
                "locked": bool(getattr(fy, "locked", False)),
            },
            "company": ar["company"],
            "kontroller": kontroller,
            "ink2": ink2,
            "skatt": skatt,
            "moms": vat,
            "arsredovisning": ar,
            "uppgifter": BokslutInputsService().current(fiscal_year_id),
            "uppgifter_schema": schema(),
            "nedladdningar": self.downloads(fiscal_year_id),
        }

    def downloads(self, fiscal_year_id: str) -> List[Dict[str, str]]:
        base = f"/api/v1/bokslut/{fiscal_year_id}/filer"
        return [
            {
                "id": "info_sru",
                "grupp": "Skatteverket",
                "label": "INFO.SRU",
                "beskrivning": "Inkomstdeklaration 2, filöverföring (fil 1 av 2)",
                "url": f"{base}/INFO.SRU",
            },
            {
                "id": "blanketter_sru",
                "grupp": "Skatteverket",
                "label": "BLANKETTER.SRU",
                "beskrivning": "INK2R och INK2S, filöverföring (fil 2 av 2)",
                "url": f"{base}/BLANKETTER.SRU",
            },
            {
                "id": "sru_zip",
                "grupp": "Skatteverket",
                "label": "SRU-filer (zip)",
                "beskrivning": "Båda SRU-filerna i ett arkiv",
                "url": f"{base}/sru.zip",
            },
            {
                "id": "eskd",
                "grupp": "Skatteverket",
                "label": "Momsdeklaration (.eskd)",
                "beskrivning": "Filöverföring av momsdeklarationen",
                "url": f"{base}/moms.eskd",
            },
            {
                "id": "moms_pdf",
                "grupp": "Skatteverket",
                "label": "Momsdeklaration (PDF)",
                "beskrivning": "Rutorna med underlag per konto",
                "url": f"{base}/momsdeklaration.pdf",
            },
            {
                "id": "arsredovisning_pdf",
                "grupp": "Bolagsverket",
                "label": "Årsredovisning (PDF)",
                "beskrivning": "Att skriva ut, underteckna och skicka",
                "url": f"{base}/arsredovisning.pdf",
            },
            {
                "id": "faststallelseintyg_pdf",
                "grupp": "Bolagsverket",
                "label": "Fastställelseintyg (PDF)",
                "beskrivning": "Undertecknas efter årsstämman",
                "url": f"{base}/faststallelseintyg.pdf",
            },
        ]

    # ── Kontroller ─────────────────────────────────────────────────────────

    def _movement(self, fiscal_year_id: str, ranges) -> int:
        from repositories.opening_balance_repo import OpeningBalanceRepository

        total = 0
        for code, net in OpeningBalanceRepository.movements(fiscal_year_id).items():
            if code.isdigit() and any(lo <= int(code) <= hi for lo, hi in ranges):
                total += net
        return total

    def _closing(self, fiscal_year_id: str) -> Dict[str, int]:
        from repositories.opening_balance_repo import OpeningBalanceRepository
        from services.opening_balance import OpeningBalanceService, is_balance_account

        closing = {
            c: v
            for c, v in OpeningBalanceService().balances(fiscal_year_id).items()
            if is_balance_account(c)
        }
        for code, net in OpeningBalanceRepository.movements(fiscal_year_id).items():
            if is_balance_account(code):
                closing[code] = closing.get(code, 0) + net
        return closing

    def _kontroller(
        self, fiscal_year_id, fy, declaration, sru, vat, ar, skatt
    ) -> List[Dict[str, str]]:
        from services.tax_adjustments import kronor

        out: List[Dict[str, str]] = []
        closing = self._closing(fiscal_year_id)
        br = ar["balansrakning"]

        diff = br["summa_tillgangar"][0] - br["summa_ek_skulder"][0]
        out.append(
            _kontroll("balans", OK, "Balansräkningen går ihop")
            if diff == 0
            else _kontroll(
                "balans",
                VARNING,
                "Balansräkningen skiljer sig efter avrundning",
                f"Tillgångar minus eget kapital och skulder är {diff} kr.",
            )
        )

        unclosed = -self._movement(fiscal_year_id, ((3000, 8999),))
        out.append(
            _kontroll("resultat", OK, "Årets resultat är bokfört mot 2099")
            if unclosed == 0
            else _kontroll(
                "resultat",
                VARNING,
                "Årets resultat är inte bokfört",
                f"{kronor(unclosed)} kr ligger kvar på resultatkontona. Bokför "
                "årets resultat (8999 mot 2099) när skatten är bokförd.",
            )
        )

        moms_saldo = sum(
            v for c, v in closing.items() if c.isdigit() and 2610 <= int(c) <= 2649
        )
        ruta49 = vat["skv_4700"]["ruta_49_moms_att_betala"]
        if moms_saldo:
            out.append(
                _kontroll(
                    "momsavstamning",
                    VARNING,
                    "Momsavstämningen är inte bokförd",
                    f"Momskontona 2610–2649 har {kronor(-moms_saldo)} kr kvar. Bokför "
                    f"avstämningen mot 2650 ({ruta49} kr att betala enligt ruta 49).",
                )
            )
        else:
            skuld = kronor(-closing.get("2650", 0))
            out.append(
                _kontroll("momsavstamning", OK, "Momsavstämningen är bokförd")
                if abs(skuld - ruta49) <= 1
                else _kontroll(
                    "momsavstamning",
                    INFO,
                    "Momsskulden skiljer sig från ruta 49",
                    f"2650 har {skuld} kr, deklarationen {ruta49} kr. Skillnaden kan vara "
                    "en tidigare periods moms som inte är betald än.",
                )
            )
        for w in vat.get("warnings", []):
            out.append(_kontroll("moms_varning", VARNING, "Momsdeklarationen", w))

        diff_skatt = skatt["differens"]
        if skatt["bokford_skatt"] == 0 and skatt["beraknad_skatt"]:
            out.append(
                _kontroll(
                    "skatt",
                    VARNING,
                    "Bolagsskatten är inte bokförd",
                    f"Beräknad skatt är {skatt['beraknad_skatt']} kr (20,6 % av "
                    f"{skatt['underlag']} kr). Bokför den på 8910 mot 2512.",
                )
            )
        elif abs(diff_skatt) > 0:
            out.append(
                _kontroll(
                    "skatt",
                    INFO if abs(diff_skatt) < 100 else VARNING,
                    "Bokförd skatt skiljer sig från beräknad",
                    f"Bokfört {skatt['bokford_skatt']} kr, beräknat {skatt['beraknad_skatt']} kr "
                    f"(20,6 % av överskottet {skatt['overskott']} kr avrundat nedåt till "
                    "hundratal). Skillnaden regleras i slutskatten.",
                )
            )
        else:
            out.append(_kontroll("skatt", OK, "Bokförd skatt stämmer med beräkningen"))

        for w in sru.warnings:
            if w.startswith("Årsspecifik SRU-mappning"):
                continue
            out.append(_kontroll("ink2", VARNING, "Inkomstdeklarationen", w))

        for adj in skatt["justeringar"]:
            if adj["override"] is not None and adj["override"] != adj["calculated"]:
                out.append(
                    _kontroll(
                        f"ink2s_{adj['row']}",
                        INFO,
                        f"{adj['row']} är angivet för hand",
                        f"{adj['override']} kr i stället för beräknade {adj['calculated']} kr.",
                    )
                )
        if any(a["code"] == "7667" and a["value"] for a in skatt["justeringar"]):
            out.append(
                _kontroll(
                    "ink2s_4_6d",
                    INFO,
                    "Kontrollera 4.6d i Skatteverkets förhandsgranskning",
                    "Uppräkningen skrivs med fältkod 7667. Se att beloppet hamnar på "
                    "4.6d när filerna laddas upp.",
                )
            )

        out.append(
            _kontroll(
                "periodiseringsfond",
                INFO,
                "Avsättning till periodiseringsfond",
                f"Högst {skatt['max_avsattning_periodiseringsfond']} kr kan sättas av i år "
                f"(25 % av överskottet före avsättning). Bokfört: {skatt['bokford_avsattning']} kr.",
            )
        )

        for m in ar["missing"]:
            out.append(
                _kontroll(
                    f"ar_{m['key']}",
                    VARNING,
                    "Årsredovisningen saknar en uppgift",
                    m["label"],
                )
            )
        for w in ar["warnings"]:
            out.append(_kontroll("ar_varning", INFO, "Årsredovisningen", w))

        if not getattr(fy, "locked", False):
            out.append(
                _kontroll(
                    "last",
                    INFO,
                    "Räkenskapsåret är inte låst",
                    "Lås året när bokslutet är klart, så att inget nytt bokförs i det.",
                )
            )

        order = {FEL: 0, VARNING: 1, INFO: 2, OK: 3}
        return sorted(out, key=lambda k: order[k["niva"]])

    # ── Filer ──────────────────────────────────────────────────────────────

    def sru_files(self, fiscal_year_id: str) -> Tuple[bytes, bytes, str]:
        from services.sru_export import SRUExportService, encode_sru

        service = SRUExportService()
        declaration = service.calculate_sru_fields(fiscal_year_id)
        info = encode_sru(service.generate_info_sru(declaration))
        blanketter = encode_sru(service.generate_blanketter_sru(declaration))
        return (
            info,
            blanketter,
            f"{_filnamn(declaration.company_name)}_{declaration.fiscal_year_end[:4]}",
        )

    def file(self, fiscal_year_id: str, name: str) -> Tuple[bytes, str, str]:
        """(innehåll, mediatyp, filnamn) för en av nedladdningarna."""
        fy = self._fiscal_year(fiscal_year_id)
        year = fy.end_date.year

        if name in ("INFO.SRU", "BLANKETTER.SRU", "sru.zip"):
            info, blanketter, stem = self.sru_files(fiscal_year_id)
            if name == "INFO.SRU":
                return info, "text/plain; charset=ISO-8859-1", "INFO.SRU"
            if name == "BLANKETTER.SRU":
                return blanketter, "text/plain; charset=ISO-8859-1", "BLANKETTER.SRU"
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("INFO.SRU", info)
                z.writestr("BLANKETTER.SRU", blanketter)
            return buf.getvalue(), "application/zip", f"{stem}_INK2_SRU.zip"

        if name in ("moms.eskd", "momsdeklaration.pdf"):
            from services.vat_report import VatReportService

            vat = VatReportService()
            decl = vat.preview_for_dates(fy.start_date, fy.end_date)
            if name == "moms.eskd":
                return (
                    vat.export_eskd(decl),
                    "application/xml; charset=ISO-8859-1",
                    f"Moms-{decl.period_code}.eskd",
                )
            return (
                vat.export_pdf(decl),
                "application/pdf",
                f"momsdeklaration-{decl.period_code}.pdf",
            )

        if name == "arsredovisning.pdf":
            from services.arsredovisning import render_arsredovisning_pdf

            pdf, report = render_arsredovisning_pdf(fiscal_year_id)
            return (
                pdf,
                "application/pdf",
                f"Arsredovisning_{_filnamn(report['company']['name'])}_{year}.pdf",
            )

        if name == "faststallelseintyg.pdf":
            from services.arsredovisning import render_faststallelseintyg_pdf

            pdf, report = render_faststallelseintyg_pdf(fiscal_year_id)
            return (
                pdf,
                "application/pdf",
                f"Faststallelseintyg_{_filnamn(report['company']['name'])}_{year}.pdf",
            )

        raise KeyError(name)
