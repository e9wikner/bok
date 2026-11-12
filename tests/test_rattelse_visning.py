"""How a corrected voucher reads, and what a correction does to the
underlag queue.

- A makulerad voucher (it nets to zero with its posted corrections) leaves
  "Saknar underlag": B-1 documents it, and no statement row can ever match.
- A statement account is read after the corrections: one a correction took
  off needs no statement, one it added does.
- A correction is never dated before the voucher it corrects.
- `correction` in the API: makulering or ändring, the net per account
  before and after, who, when and why.
"""

from datetime import date

import pytest

from repositories.account_repo import AccountRepository
from repositories.voucher_repo import VoucherRepository
from services.ledger import LedgerService
from tests import test_flode_underlag as fu
from tests.test_flode_underlag_predikat import _counts, _listed

accounts = fu.accounts
client = fu.client
period_id = fu.period_id


@pytest.fixture(autouse=True)
def tax_accounts(test_db):
    for code, name, acc_type in [
        ("1630", "Skattekonto", "asset"),
        ("1650", "Momsfordran", "asset"),
        ("2650", "Momsskuld", "liability"),
        ("2710", "Personalskatt", "liability"),
    ]:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, acc_type)


@pytest.fixture
def today(monkeypatch):
    import services.ledger as ledger

    def set_today(value: date) -> None:
        monkeypatch.setattr(ledger, "_today", lambda: value, raising=False)

    set_today(date(2026, 3, 20))
    return set_today


def _posted(period_id: str, rows: list, day: int = 12, text: str = "AGI") -> str:
    ledger = LedgerService()
    draft = ledger.create_voucher(
        series="A",
        date=date(2026, 3, day),
        period_id=period_id,
        description=text,
        rows_data=rows,
        created_by="agent",
    )
    return ledger.post_voucher(draft.id, actor="agent").id


def _agi(period_id: str, day: int = 12) -> str:
    """A-53: avdragen skatt 13 000 kr, 2710 debit, 1630 credit."""
    return _posted(
        period_id,
        [
            {"account": "2710", "debit": 1300000, "credit": 0},
            {"account": "1630", "debit": 0, "credit": 1300000},
        ],
        day=day,
        text="Arbetsgivardeklaration, avdragen skatt",
    )


def _correct(original_id: str, rows: list, reason: str = "Fel månad") -> str:
    return (
        LedgerService()
        .create_posted_correction(original_id, rows, reason=reason, actor="stefan")
        .id
    )


# ---------------------------------------------------------------------------
# The underlag queue
# ---------------------------------------------------------------------------


def test_a_makulerad_voucher_leaves_saknar_underlag(
    client, auth_headers, period_id, today
):
    original = _agi(period_id)
    assert VoucherRepository.get(original).missing_statement_accounts == ["1630"]
    assert _listed(client, auth_headers, "true") == {original}

    _correct(original, [])

    assert VoucherRepository.get(original).missing_attachment is False
    assert _listed(client, auth_headers, "true") == set()
    assert _counts(client, auth_headers) == (0, 0, 0)


def test_an_andring_still_lacks_underlag(client, auth_headers, period_id, today):
    original = fu.posted_purchase(period_id, day=10)
    _correct(
        original,
        [
            {"account": "5410", "debit": 358400, "credit": 0},
            {"account": "2640", "debit": 89600, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 448000},
        ],
    )
    assert VoucherRepository.get(original).missing_attachment is True


def test_statement_accounts_are_read_after_the_correction(period_id, today):
    """1630 replaced by 1930: the skattekonto statement is no longer asked
    for, the bank statement is."""
    original = _agi(period_id)
    _correct(
        original,
        [
            {"account": "2710", "debit": 1300000, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 1300000},
        ],
    )
    assert VoucherRepository.get(original).missing_statement_accounts == ["1930"]


# ---------------------------------------------------------------------------
# The correction's date (§7.2)
# ---------------------------------------------------------------------------


def test_a_correction_is_not_dated_before_its_original(period_id, today):
    """A-53 dated the 12th (the AGI's due date), corrected on the 5th: B-1
    is dated the 12th."""
    today(date(2026, 3, 5))
    original = _agi(period_id, day=12)

    correction = VoucherRepository.get(_correct(original, []))

    assert correction.date == date(2026, 3, 12)


def test_a_correction_after_its_original_is_dated_today(period_id, today):
    today(date(2026, 3, 20))
    original = _agi(period_id, day=12)

    correction = VoucherRepository.get(_correct(original, []))

    assert correction.date == date(2026, 3, 20)


# ---------------------------------------------------------------------------
# `correction` in the API
# ---------------------------------------------------------------------------


def _get(client, auth_headers, voucher_id: str) -> dict:
    response = client.get(f"/api/v1/vouchers/{voucher_id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_makulering_reads_as_one(client, auth_headers, period_id, today):
    original = _agi(period_id)
    correction = _correct(original, [], reason="Bokförd i fel månad")

    on_original = _get(client, auth_headers, original)["correction"]
    on_correction = _get(client, auth_headers, correction)["correction"]

    for summary in (on_original, on_correction):
        assert summary["kind"] == "makulering"
        assert summary["original"]["id"] == original
        assert summary["correction"]["id"] == correction
        assert summary["actor"] == "stefan"
        assert summary["reason"] == "Bokförd i fel månad"
        assert summary["before_total"] == 1300000
        assert summary["after_total"] == 0
        assert summary["title"].startswith("Makulering av A-1: ")
        assert {
            a["account_code"]: (a["before"], a["after"]) for a in summary["accounts"]
        } == {"2710": (1300000, 0), "1630": (-1300000, 0)}


def test_an_andring_nets_per_account(client, auth_headers, period_id, today):
    """1650 replaced by 2650, as in iOrdning's example: 1630 is unchanged,
    not debited and credited."""
    original = _posted(
        period_id,
        [
            {"account": "1650", "debit": 26974500, "credit": 0},
            {"account": "1630", "debit": 0, "credit": 26974500},
        ],
        text="Moms jan-dec 2025",
    )
    _correct(
        original,
        [
            {"account": "2650", "debit": 26974500, "credit": 0},
            {"account": "1630", "debit": 0, "credit": 26974500},
        ],
    )

    summary = _get(client, auth_headers, original)["correction"]

    assert summary["kind"] == "andring"
    assert [
        (a["account_code"], a["before"], a["after"]) for a in summary["accounts"]
    ] == [
        ("1650", 26974500, 0),
        ("1630", -26974500, -26974500),
        ("2650", 0, 26974500),
    ]
    assert summary["accounts"][0]["account_name"] == "Momsfordran"


def test_the_list_carries_correction_and_a_plain_voucher_has_none(
    client, auth_headers, period_id, today
):
    original = _agi(period_id)
    correction = _correct(original, [])
    plain = _agi(period_id, day=14)

    listed = {
        v["id"]: v
        for v in client.get("/api/v1/vouchers", headers=auth_headers).json()["vouchers"]
    }

    assert listed[original]["correction"]["kind"] == "makulering"
    assert listed[correction]["correction"]["kind"] == "makulering"
    assert listed[plain]["correction"] is None


def test_the_general_ledger_carries_correction_on_both_vouchers(
    client, auth_headers, period_id, today
):
    """The ledger reads the pair as the list does, so the client can strike
    out the makulerad voucher's row."""
    original = _agi(period_id)
    correction = _correct(original, [])
    plain = _agi(period_id, day=14)

    report = client.get("/api/v1/reports/general-ledger/1630", headers=auth_headers)
    assert report.status_code == 200, report.text
    by_voucher = {t["voucher_id"]: t for t in report.json()["transactions"]}

    for voucher in (original, correction):
        summary = by_voucher[voucher]["correction"]
        assert summary["kind"] == "makulering"
        assert summary["original"]["id"] == original
        assert summary["correction"]["id"] == correction
        accounts = {a["account_code"]: a for a in summary["accounts"]}
        assert (accounts["1630"]["before"], accounts["1630"]["after"]) == (
            -1300000,
            0,
        )
    assert by_voucher[plain]["correction"] is None
