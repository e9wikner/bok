import sqlite3
from unittest.mock import patch

from services.vat_report import VatReportService


def test_yearly_vat_declaration_matches_eskd_and_excludes_settlement_voucher():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE company_info (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE accounts (code TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE vouchers (
            id TEXT PRIMARY KEY,
            date DATE,
            status TEXT,
            series TEXT NOT NULL DEFAULT 'A'
        );
        CREATE TABLE voucher_rows (
            voucher_id TEXT,
            account_code TEXT,
            debit INTEGER,
            credit INTEGER
        );

        INSERT INTO company_info VALUES ('name', 'Stefan Wikner Consulting AB');
        INSERT INTO company_info VALUES ('org_number', '556819-4731');
        INSERT INTO accounts VALUES ('3010', 'Försäljning');
        INSERT INTO accounts VALUES ('2610', 'Utgående moms 25%');
        INSERT INTO accounts VALUES ('2640', 'Ingående moms');
        INSERT INTO accounts VALUES ('2650', 'Redovisningskonto moms');

        INSERT INTO vouchers (id, date, status) VALUES ('sales', '2025-12-30', 'posted');
        INSERT INTO voucher_rows VALUES ('sales', '3010', 0, 113932000);
        INSERT INTO voucher_rows VALUES ('sales', '2610', 0, 28483000);
        INSERT INTO voucher_rows VALUES ('sales', '2640', 1508480, 0);

        INSERT INTO vouchers (id, date, status) VALUES ('settlement', '2025-12-31', 'posted');
        INSERT INTO voucher_rows VALUES ('settlement', '2610', 28483000, 0);
        INSERT INTO voucher_rows VALUES ('settlement', '2640', 0, 1508480);
        INSERT INTO voucher_rows VALUES ('settlement', '2650', 0, 26974520);
        """)

    with patch("services.vat_report.get_db", return_value=db), patch(
        "services.vat_report.PeriodRepository.list_fiscal_years", return_value=[]
    ):
        service = VatReportService()
        declaration = service.preview_yearly(2025)
        summary = service.format_skv_summary(declaration)["skv_4700"]
        eskd = service.export_eskd(declaration).decode("iso-8859-1")

    assert summary == {
        "ruta_05_momspliktig_forsaljning": 1139320,
        "ruta_06_momspliktiga_uttag": 0,
        "ruta_07_vinstmarginal": 0,
        "ruta_08_hyresinkomster": 0,
        "ruta_42_ovrig_forsaljning": 0,
        "ruta_10_utgaende_moms_25": 284830,
        "ruta_11_utgaende_moms_12": 0,
        "ruta_12_utgaende_moms_6": 0,
        "ruta_21_inkop_tjanster_eu": 0,
        "ruta_22_inkop_tjanster_utanfor_eu": 0,
        "ruta_30_utgaende_moms_inkop_25": 0,
        "ruta_48_ingaende_moms": 15085,
        "ruta_49_moms_att_betala": 269745,
    }
    assert "<OrgNr>556819-4731</OrgNr>" in eskd
    assert "<Period>202512</Period>" in eskd
    assert "<ForsMomsEjAnnan>1139320</ForsMomsEjAnnan>" in eskd
    assert "<MomsUtgHog>284830</MomsUtgHog>" in eskd
    assert "<MomsIngAvdr>15085</MomsIngAvdr>" in eskd
    assert "<MomsBetala>269745</MomsBetala>" in eskd


def test_reverse_charge_service_from_outside_eu_fills_boxes_22_30_48():
    """Migration 045: an utlägg for a US SaaS subscription, 224,69 kr. The
    base on 4531 (against 4598) is box 22, the calculated VAT on 2614 box 30
    and on 2645 box 48 -- and the net to pay is unchanged."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE company_info (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE accounts (code TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE vouchers (
            id TEXT PRIMARY KEY,
            date DATE,
            status TEXT,
            series TEXT NOT NULL DEFAULT 'A'
        );
        CREATE TABLE voucher_rows (
            voucher_id TEXT,
            account_code TEXT,
            debit INTEGER,
            credit INTEGER
        );
        INSERT INTO vouchers (id, date, status) VALUES ('saas', '2026-10-14', 'posted');
        INSERT INTO voucher_rows VALUES ('saas', '6540', 22469, 0);
        INSERT INTO voucher_rows VALUES ('saas', '2820', 0, 22469);
        INSERT INTO voucher_rows VALUES ('saas', '2645', 5617, 0);
        INSERT INTO voucher_rows VALUES ('saas', '2614', 0, 5617);
        INSERT INTO voucher_rows VALUES ('saas', '4531', 22469, 0);
        INSERT INTO voucher_rows VALUES ('saas', '4598', 0, 22469);

        INSERT INTO vouchers (id, date, status) VALUES ('eu', '2026-10-15', 'posted');
        INSERT INTO voucher_rows VALUES ('eu', '6540', 10000, 0);
        INSERT INTO voucher_rows VALUES ('eu', '2820', 0, 10000);
        INSERT INTO voucher_rows VALUES ('eu', '2645', 2500, 0);
        INSERT INTO voucher_rows VALUES ('eu', '2614', 0, 2500);
        INSERT INTO voucher_rows VALUES ('eu', '4535', 10000, 0);
        INSERT INTO voucher_rows VALUES ('eu', '4598', 0, 10000);
        """)

    with patch("services.vat_report.get_db", return_value=db), patch(
        "services.vat_report.PeriodRepository.list_fiscal_years", return_value=[]
    ):
        service = VatReportService()
        declaration = service.preview_yearly(2026)
        summary = service.format_skv_summary(declaration)["skv_4700"]
        eskd = service.export_eskd(declaration).decode("iso-8859-1")

    assert declaration.purchases_services_non_eu == 22469
    assert declaration.purchases_services_eu == 10000
    assert declaration.vat_out_reverse_25 == 8117
    assert declaration.vat_in == 8117
    assert declaration.vat_to_pay == 0
    assert summary["ruta_21_inkop_tjanster_eu"] == 100
    assert summary["ruta_22_inkop_tjanster_utanfor_eu"] == 225
    assert summary["ruta_30_utgaende_moms_inkop_25"] == 81
    assert summary["ruta_48_ingaende_moms"] == 81
    assert summary["ruta_49_moms_att_betala"] == 0
    # The 25 % fallback for box 05 must not read box 30 as sales.
    assert summary["ruta_05_momspliktig_forsaljning"] == 0
    assert "<InkopTjanstAnnatEg>100</InkopTjanstAnnatEg>" in eskd
    assert "<InkopTjanstUtomEg>225</InkopTjanstUtomEg>" in eskd
    assert "<MomsInkopUtgHog>81</MomsInkopUtgHog>" in eskd


def test_sales_lines_are_sorted_against_the_vouchers_vat():
    classify = VatReportService._classify_sales
    # No output VAT: all of it is ruta 42.
    assert classify([("3010", "F", 10000)], {}) == (
        [("42", "3010", "F", 10000)],
        False,
    )
    # 25 % VAT on 10 000 and an exempt 4 000 line: the lines are kept whole.
    out, unsure = classify([("3010", "F", 10000), ("3100", "M", 4000)], {"10": 2500})
    assert out == [("05", "3010", "F", 10000), ("42", "3100", "M", 4000)]
    assert not unsure
    # 12 % and 25 % on one voucher, both lines taxable.
    out, _ = classify(
        [("3010", "F", 10000), ("3020", "L", 5000)], {"10": 2500, "11": 600}
    )
    assert {box for box, *_ in out} == {"05"}
    # No whole line matches the base: split pro rata, and say so.
    out, unsure = classify([("3010", "F", 15000), ("3011", "G", 5000)], {"10": 2500})
    assert unsure
    assert sum(a for box, *_, a in out if box == "05") == 10000
    assert sum(a for box, *_, a in out if box == "42") == 10000
