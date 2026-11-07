"""Bokslutet per räkenskapsår (services/bokslut.py och dess delar).

Ett litet påhittat aktiebolag med samma slags poster som referensåren
2024–2025 från iOrdning: kapitalförsäkring (skattefri), ränta på
skattekontot (skattefri intäkt och ej avdragsgill kostnad), en
förseningsavgift, återförda periodiseringsfonder och en bokförd
momsavstämning med öresutjämning.
"""

import pytest
from fastapi.testclient import TestClient

from config import settings

SIE = """#FLAGGA 0
#FORMAT PC8
#SIETYP 4
#FNAMN "Testbolaget AB"
#ORGNR 556677-8899
#RAR 0 20250101 20251231
#KONTO 1385 "Värde av kapitalförsäkring"
#KONTO 1630 Skattekonto
#KONTO 1920 Bankkonto
#KONTO 2081 Aktiekapital
#KONTO 2091 "Balanserad vinst eller förlust"
#KONTO 2099 "Årets resultat"
#KONTO 2128 "Periodiseringsfond 2018"
#KONTO 2129 "Periodiseringsfond 2019"
#KONTO 2122 "Periodiseringsfond 2022"
#KONTO 2512 "Beräknad inkomstskatt"
#KONTO 2610 "Utgående moms, oreducerad"
#KONTO 2640 "Ingående moms"
#KONTO 2650 Momsskuld
#KONTO 3010 Försäljning
#KONTO 3100 "Momsfria intäkter"
#KONTO 3740 Öresutjämning
#KONTO 5400 Förbrukningsinventarier
#KONTO 6992 "Övriga externa kostnader, ej avdragsgill"
#KONTO 8226 "Värdeförändring kapitalförsäkring, ej skattepliktig"
#KONTO 8314 "Ränteintäkt Skattemyndigheten"
#KONTO 8423 "Räntekostnad Skattemyndigheten"
#KONTO 8819 "Återföring från periodiseringsfond"
#KONTO 8910 Skatt
#KONTO 8999 "Årets resultat"
#IB 0 1385 100000
#IB 0 1920 500000
#IB 0 2081 -50000
#IB 0 2091 -150000
#IB 0 2128 -100000
#IB 0 2129 -100000
#IB 0 2122 -200000
#VER A 1 20250131 Faktura
{
#TRANS 3010 {} -100000.00
#TRANS 2610 {} -25000.00
#TRANS 1920 {} 125000.00
}
#VER A 2 20250201 Momsfri intakt
{
#TRANS 3100 {} -5000.00
#TRANS 1920 {} 5000.00
}
#VER A 3 20250301 Inventarier
{
#TRANS 5400 {} 8000.00
#TRANS 2640 {} 2000.00
#TRANS 1920 {} -10000.00
}
#VER A 4 20250401 Forseningsavgift
{
#TRANS 6992 {} 625.00
#TRANS 1630 {} -625.00
}
#VER A 5 20250501 Skattekonto
{
#TRANS 8314 {} -40.00
#TRANS 8423 {} 60.00
#TRANS 1630 {} -20.00
}
#VER A 6 20250601 Uttag kapitalforsakring
{
#TRANS 1385 {} -100000.00
#TRANS 1920 {} 130000.00
#TRANS 8226 {} -30000.00
}
#VER A 7 20251231 Aterforing periodiseringsfond
{
#TRANS 2128 {} 100000.00
#TRANS 2129 {} 100000.00
#TRANS 8819 {} -200000.00
}
#VER A 8 20251231 Momsavstamning
{
#TRANS 2610 {} 25000.00
#TRANS 2640 {} -2000.00
#TRANS 2650 {} -23000.00
}
"""


@pytest.fixture
def ar(test_db):
    from services.sie4_import import SIE4Importer

    importer = SIE4Importer("", "")
    assert importer.import_content(SIE), importer.errors
    return importer.fiscal_year_resolution["id"]


@pytest.fixture
def client(test_db):
    from api.main import app

    return TestClient(app, headers={"Authorization": f"Bearer {settings.api_key}"})


def _falt(fy):
    from services.sru_export import SRUExportService

    d = SRUExportService().calculate_sru_fields(fy)
    return {k: v.value for k, v in d.fields.items()}


class TestInk2s:
    def test_justeringarna_raknas_ur_bokforingen(self, ar):
        f = _falt(ar)
        # Resultat: 100 000 + 5 000 - 8 000 - 625 + 40 - 60 + 30 000 + 200 000
        assert f["7450"] == 326355
        # 4.3c: förseningsavgiften och räntekostnaden på skattekontot.
        assert f["7653"] == 625 + 60
        # 4.5c: kapitalförsäkringen och den skattefria räntan, inget mer.
        assert f["7754"] == 30000 + 40
        # 4.6a: fonderna vid årets ingång (400 000) × 1,96 % (nov 2024).
        assert f["7654"] == 7840
        # 4.6d: 6 % av fonden från 2018 och 4 % av den från 2019.
        assert f["7667"] == 6000 + 4000
        assert f["7670"] == 326355 + 685 - 30040 + 7840 + 10000

    def test_ett_angivet_belopp_ersatter_beraknat(self, ar):
        from services.bokslut_inputs import BokslutInputsService

        BokslutInputsService().set_values(
            ar,
            {"ink2s.belopp.7667": 0, "ink2s.skattefria_konton": ["8226"]},
            "test",
        )
        f = _falt(ar)
        assert "7667" not in f
        assert f["7754"] == 30000
        assert f["7670"] == 326355 + 685 - 30000 + 7840

    def test_sru_filen_ar_latin1_och_har_arets_blankett(self, ar):
        from services.bokslut import BokslutService

        info, blanketter, _ = BokslutService().sru_files(ar)
        assert not blanketter.startswith(b"\xef\xbb\xbf")
        text = blanketter.decode("iso-8859-1")
        assert "#BLANKETT INK2R-2025P4" in text
        assert "#UPPGIFT 7654 7840" in text
        assert "#UPPGIFT 8041 X" in text
        assert info.decode("iso-8859-1").startswith("#DATABESKRIVNING_START")


class TestMoms:
    def test_ruta_05_och_42(self, ar):
        from repositories.period_repo import PeriodRepository
        from services.vat_report import VatReportService

        fy = PeriodRepository.get_fiscal_year(ar)
        s = VatReportService()
        decl = s.preview_for_dates(fy.start_date, fy.end_date)
        rutor = s.format_skv_summary(decl)["skv_4700"]
        # Momsavstämningen räknas inte, 3100 utan moms går till ruta 42.
        assert rutor["ruta_05_momspliktig_forsaljning"] == 100000
        assert rutor["ruta_42_ovrig_forsaljning"] == 5000
        assert rutor["ruta_10_utgaende_moms_25"] == 25000
        assert rutor["ruta_48_ingaende_moms"] == 2000
        assert rutor["ruta_49_moms_att_betala"] == 23000
        eskd = s.export_eskd(decl).decode("iso-8859-1")
        assert "<ForsOvrigt>5000</ForsOvrigt>" in eskd

    def test_moms_och_momsfritt_pa_samma_verifikation(self, test_db):
        """En faktura med både momspliktig och momsfri försäljning: bara
        raden som momsen motsvarar går till ruta 05."""
        from repositories.period_repo import PeriodRepository
        from services.vat_report import VatReportService

        fy = _importera(
            SIE.replace(
                """#VER A 2 20250201 Momsfri intakt
{
#TRANS 3100 {} -5000.00
#TRANS 1920 {} 5000.00
}""",
                """#VER A 2 20250201 Faktura med momsfri rad
{
#TRANS 3010 {} -20000.00
#TRANS 3100 {} -5000.00
#TRANS 2610 {} -5000.00
#TRANS 1920 {} 30000.00
}""",
            )
        )
        fy = PeriodRepository.get_fiscal_year(fy)
        s = VatReportService()
        decl = s.preview_for_dates(fy.start_date, fy.end_date)
        rutor = s.format_skv_summary(decl)["skv_4700"]
        assert rutor["ruta_05_momspliktig_forsaljning"] == 120000
        assert rutor["ruta_42_ovrig_forsaljning"] == 5000
        assert not decl.warnings

    def test_ruta_42_sparas_och_gamla_deklarationer_lases_om(self, ar, test_db):
        from services.vat_report import VatReportService

        s = VatReportService()
        decl = s.generate_yearly(2025)
        saved = s.get_declaration(decl.id)
        assert saved.sales_25 == 10000000
        assert saved.sales_other == 500000

        # Sparad före migration 047: sales_12/sales_6 var försäljning 12 %
        # och 6 %, sales_exempt momsfri försäljning.
        test_db.execute("""INSERT INTO vat_declarations
               (id, period_year, period_month, sales_25, sales_12, sales_6,
                sales_exempt, vat_out_25, vat_out_12, vat_out_6, vat_in,
                vat_to_pay)
               VALUES ('gammal', 2024, 12, 100, 20, 30, 40, 25, 2, 2, 0, 29)""")
        test_db.commit()
        old = s.get_declaration("gammal")
        assert (old.sales_25, old.sales_12, old.sales_6) == (150, 0, 0)
        assert (old.sales_exempt, old.sales_other) == (0, 40)


def _importera(sie: str) -> str:
    from services.sie4_import import SIE4Importer

    importer = SIE4Importer("", "")
    assert importer.import_content(sie), importer.errors
    return importer.fiscal_year_resolution["id"]


class TestSkatt:
    def test_statslaneranta_for_brutet_ar_ar_slutarets(self, test_db):
        """Ett år 2024-07-01--2025-06-30 går ut 2025: november 2024
        (1,96 %), inte november 2023."""
        sie = (
            SIE.replace("#RAR 0 20250101 20251231", "#RAR 0 20240701 20250630")
            .replace("20251231", "20250630")
            .replace("20250131", "20240731")
        )
        f = _falt(_importera(sie))
        assert f["7654"] == 7840

    def test_bokford_avsattning_till_periodiseringsfond_ar_positiv(self, test_db):
        from services.bokslut import BokslutService

        sie = (
            SIE.replace(
                "#KONTO 8819",
                '#KONTO 2125 "Periodiseringsfond 2025"\n#KONTO 8811'
                ' "Avsättning till periodiseringsfond"\n#KONTO 8819',
            )
            + """#VER A 9 20251231 Avsattning periodiseringsfond
{
#TRANS 8811 {} 50000.00
#TRANS 2125 {} -50000.00
}
"""
        )
        fy = _importera(sie)
        skatt = BokslutService().overview(fy)["skatt"]
        assert skatt["bokford_avsattning"] == 50000
        assert skatt["max_avsattning_periodiseringsfond"] == (
            (skatt["overskott"] + 50000) * 25 // 100
        )


class TestArsredovisning:
    def test_flerarsoversikten_har_fyra_ar(self, ar):
        from services.arsredovisning import build_arsredovisning

        fo = build_arsredovisning(ar)["forvaltningsberattelse"]["flerarsoversikt"]
        assert [y["ar"] for y in fo] == ["2025", "2024", "2023", "2022"]
        # 2024 ur årets ingående balans, 2023 och 2022 finns inte i Bok.
        assert fo[1]["balansomslutning"] == 600000
        assert fo[2]["balansomslutning"] is None

    def test_rakningarna_gar_ihop(self, ar):
        from services.arsredovisning import build_arsredovisning

        r = build_arsredovisning(ar)
        br = r["balansrakning"]
        assert br["summa_tillgangar"][0] == br["summa_ek_skulder"][0]
        assert r["resultatrakning"]["arets_resultat"][0] == 326355
        assert br["arets_resultat"][0] == 326355
        # Jämförelsetalen är årets ingående balans.
        assert br["summa_tillgangar"][1] == 600000
        assert {m["key"] for m in r["missing"]} >= {"ar.verksamhet", "ar.utdelning"}

    def test_vinstdispositionen_foljer_angiven_utdelning(self, ar):
        from services.arsredovisning import build_arsredovisning
        from services.bokslut_inputs import BokslutInputsService

        BokslutInputsService().set_values(ar, {"ar.utdelning": 100000}, "test")
        vd = build_arsredovisning(ar)["forvaltningsberattelse"]["vinstdisposition"]
        assert vd["summa"] == 150000 + 326355
        assert vd["i_ny_rakning"] == vd["summa"] - 100000


class TestApi:
    def test_oversikt_kontroller_och_filer(self, ar, client):
        r = client.get(f"/api/v1/bokslut/{ar}")
        assert r.status_code == 200
        d = r.json()
        ids = {k["id"]: k["niva"] for k in d["kontroller"]}
        assert ids["balans"] == "ok"
        assert ids["momsavstamning"] == "ok"
        # Skatt och resultat är inte bokförda i testbolaget.
        assert ids["skatt"] == "varning"
        assert ids["resultat"] == "varning"
        for f in d["nedladdningar"]:
            if f["id"].endswith("_pdf"):
                continue  # WeasyPrint kräver systembibliotek
            resp = client.get(f["url"])
            assert resp.status_code == 200, f["id"]
            assert "attachment" in resp.headers["content-disposition"]

    def test_uppgifter_valideras_och_ar_append_only(self, ar, client, test_db):
        bad = client.post(
            f"/api/v1/bokslut/{ar}/uppgifter",
            json={"values": {"ar.utdelning": -1, "okand": 1}},
        )
        assert bad.status_code == 422
        assert set(bad.json()["detail"]["errors"]) == {"ar.utdelning", "okand"}

        for v in ("A", "B", None):
            ok = client.post(
                f"/api/v1/bokslut/{ar}/uppgifter", json={"values": {"ar.ort": v}}
            )
            assert ok.status_code == 200
        got = client.get(f"/api/v1/bokslut/{ar}/uppgifter").json()
        assert "ar.ort" not in got["values"]
        assert [h["value"] for h in got["history"] if h["key"] == "ar.ort"] == [
            "A",
            "B",
            None,
        ]
        with pytest.raises(Exception):
            test_db.execute("DELETE FROM bokslut_inputs")

    def test_okant_ar_och_okand_fil(self, ar, client):
        assert client.get("/api/v1/bokslut/finns-inte").status_code == 404
        assert client.get(f"/api/v1/bokslut/{ar}/filer/hemlig.txt").status_code == 404


def _kontroll(fy, id_):
    from services.bokslut import BokslutService

    return [k for k in BokslutService().overview(fy)["kontroller"] if k["id"] == id_]


class TestDisposition:
    """Förra årets resultat på 2099 ska föras till 2091 (och 2898)."""

    SIE_2099 = SIE.replace(
        "#IB 0 2091 -150000", "#IB 0 2091 -100000\n#IB 0 2099 -50000"
    )

    def test_odisponerat_resultat_ger_varning(self, test_db):
        [k] = _kontroll(_importera(self.SIE_2099), "disposition")
        assert k["niva"] == "varning"
        assert "50000 kr (vinst)" in k["text"]
        assert "2091" in k["text"]

    def test_disponerat_resultat_ar_ok(self, test_db):
        sie = self.SIE_2099 + """#VER A 9 20250515 Vinstdisposition
{
#TRANS 2099 {} 50000.00
#TRANS 2091 {} -40000.00
#TRANS 2898 {} -10000.00
}
"""
        sie = sie.replace(
            "#KONTO 2512", '#KONTO 2898 "Outtagen vinstutdelning"\n#KONTO 2512'
        )
        [k] = _kontroll(_importera(sie), "disposition")
        assert k["niva"] == "ok"

    def test_inget_ingaende_resultat_ingen_kontroll(self, ar):
        assert _kontroll(ar, "disposition") == []


class TestOversiktensBokslut:
    """Bokslut-fliken i översikten säger vad som återstår av bokslutet."""

    def _bokslut(self, fy, today):
        from datetime import date

        from services.overview import OverviewService

        o = OverviewService().get_overview(
            today=date.fromisoformat(today), fiscal_year_id=fy
        )
        return next(p for p in o.pages if p.key == "bokslut")

    def test_avslutat_ar_raknar_kontrollerna(self, ar):
        from services.bokslut import BokslutService

        page = self._bokslut(ar, "2026-02-01")
        kvar = [
            k
            for k in BokslutService().overview(ar)["kontroller"]
            if k["niva"] in ("fel", "varning")
        ]
        assert page.counters["closing_checks"] == len(kvar) > 0
        assert f"{len(kvar)} att åtgärda i bokslutet" in page.meta
        assert page.waiting is True

    def test_under_aret_bara_dispositionen(self, test_db):
        fy = _importera(TestDisposition.SIE_2099)
        assert self._bokslut(fy, "2025-06-01").counters["closing_checks"] == 1

    def test_under_aret_utan_ingaende_resultat_vantar_inget(self, ar):
        page = self._bokslut(ar, "2025-06-01")
        assert page.counters["closing_checks"] == 0
