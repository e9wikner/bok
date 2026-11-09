"""Fakturor och löner som bokförts utanför BokAI syns i Fakturering och Löner.

En faktura från ett annat system finns här bara som verifikation (debet
kundfordringar, kredit intäkt och utgående moms), och en lön bokförd från
ett annat lönesystem likaså. `GET /invoices` lämnar dem i `ledger_invoices`
och `GET /payroll/runs` i `ledger_payouts`, för årsväljarens år. En faktura
är betald när en senare verifikation minskar kundfordringarna med exakt dess
belopp.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from config import settings
from db.database import db
from repositories.account_repo import AccountRepository
from repositories.period_repo import PeriodRepository
from services.ledger import LedgerService

pytestmark = pytest.mark.usefixtures("test_db")


@pytest.fixture(autouse=True)
def accounts(test_db):
    for code, name, acc_type in [
        ("1500", "Kundfordringar", "asset"),
        ("1920", "Bankkonto", "asset"),
        ("2610", "Utgående moms 25%", "vat_out"),
        ("2710", "Personalskatt", "liability"),
        ("2730", "Avräkning arbetsgivaravgifter", "liability"),
        ("2920", "Upplupna semesterlöner", "liability"),
        ("3010", "Försäljning tjänster 25%", "revenue"),
        ("7000", "Löner till anställda", "expense"),
        ("7010", "Löner till tjänstemän", "expense"),
        ("7090", "Förändring semesterlöneskuld", "expense"),
        ("7510", "Arbetsgivaravgifter", "expense"),
    ]:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, acc_type)


@pytest.fixture
def years():
    out = []
    for y in (2025, 2026):
        fy = PeriodRepository.create_fiscal_year(
            start_date=date(y, 1, 1), end_date=date(y, 12, 31)
        )
        for m in range(1, 13):
            nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
            PeriodRepository.create_period(
                fiscal_year_id=fy.id,
                year=y,
                month=m,
                start_date=date(y, m, 1),
                end_date=nxt - timedelta(days=1),
            )
        out.append(fy)
    db.commit()
    return out


@pytest.fixture
def client(test_db):
    from api.main import app

    return TestClient(app)


@pytest.fixture
def headers():
    return {"Authorization": f"Bearer {settings.api_key}"}


def _post(day: date, text: str, rows: list) -> str:
    ledger = LedgerService()
    fy = next(
        f for f in PeriodRepository.list_fiscal_years() if f.start_date.year == day.year
    )
    period = PeriodRepository.get_period_by_date(fy.id, day)
    draft = ledger.create_voucher(
        series="A",
        date=day,
        period_id=period.id,
        description=text,
        rows_data=[{"account": a, "debit": d, "credit": c} for a, d, c in rows],
        created_by="sie4_import",
    )
    vid = ledger.post_voucher(draft.id, actor="sie4_import").id
    db.commit()
    return vid


def _invoice(day: date, text: str, inc: int) -> str:
    vat = inc // 5
    return _post(
        day, text, [("1500", inc, 0), ("3010", 0, inc - vat), ("2610", 0, vat)]
    )


def _payment(day: date, text: str, amount: int) -> str:
    return _post(day, text, [("1920", amount, 0), ("1500", 0, amount)])


def test_invoices_booked_outside_bokai_are_listed_with_payment(client, headers, years):
    y25, y26 = years
    dec = _invoice(date(2025, 12, 30), "Faktura #101275 skickad", 1600000)
    jan = _invoice(date(2026, 1, 29), "Faktura #101276 skickad", 920000)
    mar = _invoice(date(2026, 3, 31), "Faktura #101277 skickad", 920000)
    paid_dec = _payment(date(2026, 1, 20), "Faktura #101275 betald", 1600000)
    paid_jan = _payment(date(2026, 2, 25), "Faktura #101276 betald", 920000)

    r = client.get(
        "/api/v1/invoices", params={"fiscal_year_id": y26.id}, headers=headers
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 0  # no BokAI invoices
    rows = body["ledger_invoices"]
    # Newest first; last year's invoice stays in last year.
    assert [i["voucher_id"] for i in rows] == [mar, jan]
    assert rows[1]["paid"] is True
    assert rows[1]["payment_voucher_id"] == paid_jan
    assert rows[1]["amount_inc_vat"] == 920000
    assert rows[1]["vat_amount"] == 184000
    # Same amount as January's, but January's payment is taken.
    assert rows[0]["paid"] is False and rows[0]["payment_voucher_id"] is None

    r = client.get(
        "/api/v1/invoices", params={"fiscal_year_id": y25.id}, headers=headers
    )
    (only,) = r.json()["ledger_invoices"]
    assert only["voucher_id"] == dec
    assert only["payment_voucher_id"] == paid_dec  # paid in the next year


def test_a_cancelled_invoice_voucher_is_not_listed(client, headers, years):
    _, y26 = years
    vid = _invoice(date(2026, 2, 1), "Faktura fel", 500000)
    LedgerService().create_posted_correction(vid, [], reason="Fel", actor="stefan")
    db.commit()
    r = client.get(
        "/api/v1/invoices", params={"fiscal_year_id": y26.id}, headers=headers
    )
    assert r.json()["ledger_invoices"] == []


def test_salaries_booked_outside_bokai_are_listed(client, headers, years):
    _, y26 = years
    salary = _post(
        date(2026, 2, 25),
        "Lön till tjänstemän (februari)",
        [
            ("7000", 4358300, 0),
            ("7510", 1571000, 0),
            ("1920", 0, 3108800),
            ("2710", 0, 1249500),
            ("2730", 0, 1571000),
        ],
    )
    # An accrual is not a payout.
    _post(
        date(2026, 3, 31),
        "Semesterlöneskuld",
        [("7090", 100000, 0), ("2920", 0, 100000)],
    )

    r = client.get(
        "/api/v1/payroll/runs", params={"fiscal_year_id": y26.id}, headers=headers
    )
    assert r.status_code == 200, r.text
    (payout,) = r.json()["ledger_payouts"]
    assert payout["voucher_id"] == salary
    assert payout["date"] == "2026-02-25"
    assert payout["gross_salary"] == 4358300
    assert payout["preliminary_tax"] == 1249500
    assert payout["net_salary"] == 3108800
    assert payout["voucher_number"].startswith("A")


def test_a_salary_owed_to_the_employee_has_its_net(client, headers, years):
    """Nettolönen bokad som skuld (2820) och betald senare."""
    _, y26 = years
    if not AccountRepository.exists("2820"):
        AccountRepository.create(
            "2820", "Kortfristiga skulder till anställda", "liability"
        )
    _post(
        date(2026, 8, 25),
        "Lön augusti",
        [("7010", 5200000, 0), ("2710", 0, 1300000), ("2820", 0, 3900000)],
    )
    r = client.get(
        "/api/v1/payroll/runs", params={"fiscal_year_id": y26.id}, headers=headers
    )
    (payout,) = r.json()["ledger_payouts"]
    assert payout["net_salary"] == 3900000


def test_payroll_summary_reads_tax_and_fees_off_the_ledger(client, headers, years):
    """Årets lön, skatt och sociala avgifter ur huvudboken: avdragen skatt
    och påförda avgifter ur lönerna, betalda ur AGI:erna. Decembers AGI
    betalas i januari och räknas till det år den betalas."""
    y25, y26 = years
    if not AccountRepository.exists("1630"):
        AccountRepository.create("1630", "Skattekonto", "asset")

    def salary(day: date) -> str:
        return _post(
            day,
            "Lön",
            [
                ("7010", 4000000, 0),
                ("7510", 1256800, 0),
                ("1920", 0, 2800000),
                ("2710", 0, 1200000),
                ("2730", 0, 1256800),
            ],
        )

    def agi(day: date) -> str:
        return _post(
            day,
            "Arbetsgivardeklaration",
            [("2710", 1200000, 0), ("2730", 1256800, 0), ("1630", 0, 2456800)],
        )

    salary(date(2025, 12, 25))
    agi(date(2026, 1, 12))  # December's
    salary(date(2026, 1, 25))
    agi(date(2026, 2, 12))
    salary(date(2026, 2, 25))  # its AGI not yet booked
    # A makulerad salary counts nowhere.
    wrong = salary(date(2026, 3, 25))
    LedgerService().create_posted_correction(wrong, [], reason="Fel", actor="stefan")
    db.commit()
    # An accrual is a salary cost, not a tax.
    _post(
        date(2026, 3, 31),
        "Semesterlöneskuld",
        [("7090", 100000, 0), ("2920", 0, 100000)],
    )

    r = client.get(
        "/api/v1/payroll/runs", params={"fiscal_year_id": y26.id}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["summary"] == {
        "gross_salary": 8100000,
        "tax_withheld": 2400000,
        "tax_paid": 2400000,
        "employer_fee_charged": 2513600,
        "employer_fee_paid": 2513600,
    }

    r = client.get(
        "/api/v1/payroll/runs", params={"fiscal_year_id": y25.id}, headers=headers
    )
    assert r.json()["summary"] == {
        "gross_salary": 4000000,
        "tax_withheld": 1200000,
        "tax_paid": 0,
        "employer_fee_charged": 1256800,
        "employer_fee_paid": 0,
    }
