import sqlite3
from unittest.mock import patch

from services.vat_report import VatReportService


def test_yearly_vat_declaration_matches_eskd_and_excludes_settlement_voucher():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE company_info (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE accounts (code TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE vouchers (
            id TEXT PRIMARY KEY,
            date DATE,
            status TEXT
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

        INSERT INTO vouchers VALUES ('sales', '2025-12-30', 'posted');
        INSERT INTO voucher_rows VALUES ('sales', '3010', 0, 113932000);
        INSERT INTO voucher_rows VALUES ('sales', '2610', 0, 28483000);
        INSERT INTO voucher_rows VALUES ('sales', '2640', 1508480, 0);

        INSERT INTO vouchers VALUES ('settlement', '2025-12-31', 'posted');
        INSERT INTO voucher_rows VALUES ('settlement', '2610', 28483000, 0);
        INSERT INTO voucher_rows VALUES ('settlement', '2640', 0, 1508480);
        INSERT INTO voucher_rows VALUES ('settlement', '2650', 0, 26974520);
        """
    )

    with patch("services.vat_report.get_db", return_value=db), patch(
        "services.vat_report.PeriodRepository.list_fiscal_years", return_value=[]
    ):
        service = VatReportService()
        declaration = service.preview_yearly(2025)
        summary = service.format_skv_summary(declaration)["skv_4700"]
        eskd = service.export_eskd(declaration).decode("iso-8859-1")

    assert summary == {
        "ruta_05_forsaljning_25": 1139320,
        "ruta_06_forsaljning_12": 0,
        "ruta_07_forsaljning_6": 0,
        "ruta_08_momsfri_forsaljning": 0,
        "ruta_10_utgaende_moms_25": 284830,
        "ruta_11_utgaende_moms_12": 0,
        "ruta_12_utgaende_moms_6": 0,
        "ruta_48_ingaende_moms": 15085,
        "ruta_49_moms_att_betala": 269745,
    }
    assert "<OrgNr>556819-4731</OrgNr>" in eskd
    assert "<Period>202512</Period>" in eskd
    assert "<ForsMomsEjAnnan>1139320</ForsMomsEjAnnan>" in eskd
    assert "<MomsUtgHog>284830</MomsUtgHog>" in eskd
    assert "<MomsIngAvdr>15085</MomsIngAvdr>" in eskd
    assert "<MomsBetala>269745</MomsBetala>" in eskd
