"""`flode-underlag`: the predicate "saknar underlag" (FU2) and
`referenced_by` (FU16).

D3: a correction's underlag is the original and `accounting_corrections`,
so a posted correction does not lack underlag. D2: a voucher with a row in
`voucher_source_references` has its underlag through the reference.
Test case numbers refer to SPEC-flode-underlag.md §14.
"""

import re
from datetime import date

from repositories.voucher_repo import VoucherRepository
from services.compliance import ComplianceService
from tests import test_flode_underlag as fu
from tests.test_flode_underlag import (
    a118,
    interpret,
    make_decision,
    make_source,
    make_thread,
    posted_purchase,
)

# The module's fixtures, bound here so pytest finds them in this file.
accounts = fu.accounts
client = fu.client
period_id = fu.period_id


def posted_correction(original_id: str, *, total: int = 448000, day: int = 15) -> str:
    """A posted B-series correction of *original_id*, dated *day*: a
    reclassification whose debit sum is *total* -- the same amount as the
    purchase, so it would be a candidate by amount and date alone."""
    from services.ledger import LedgerService

    ledger = LedgerService()
    correction = ledger.create_correction(
        original_id,
        [
            {"account": "5410", "debit": total, "credit": 0},
            {"account": "1930", "debit": 0, "credit": total},
        ],
        actor="agent",
        voucher_date=date(2026, 3, day),
        description="Rättelse",
    )
    return ledger.post_voucher(correction.id, actor="agent").id


def reference(voucher_id: str, via_voucher_id: str, period_id: str) -> None:
    """A row in `voucher_source_references`: *voucher_id* refers to a
    receipt linked to *via_voucher_id*, through an answered decision."""
    from domain.intake_link import VoucherSourceReference
    from repositories.intake_link_repo import VoucherSourceReferenceRepository

    source_id = make_source()
    decision = make_decision(make_thread(period_id), source_id)
    VoucherSourceReferenceRepository.insert(
        VoucherSourceReference(
            voucher_id=voucher_id,
            intake_source_id=source_id,
            via_voucher_id=via_voucher_id,
            decision_id=decision.id,
        )
    )


def _listed(client, auth_headers, missing: str) -> set:
    body = client.get(
        "/api/v1/vouchers",
        headers=auth_headers,
        params={"missing_attachment": missing},
    ).json()
    return {v["id"] for v in body["vouchers"]}


def _counts(client, auth_headers) -> tuple:
    overview = client.get("/api/v1/overview", headers=auth_headers)
    assert overview.status_code == 200, overview.text
    counter = overview.json()["pages"][0]["counters"]["missing_attachments"]
    listed = client.get(
        "/api/v1/vouchers",
        headers=auth_headers,
        params={"missing_attachment": "true"},
    ).json()["total"]
    issues = ComplianceService()._check_missing_attachments()
    compliance = 0
    if issues:
        match = re.search(r"(\d+) verifikationer", issues[0].title)
        assert match is not None
        compliance = int(match.group(1))
    return counter, listed, compliance


# ---------------------------------------------------------------------------
# FU2 — the predicate (D3, D2)
# ---------------------------------------------------------------------------


def test_44_posted_correction_does_not_lack_underlag(client, auth_headers, period_id):
    """Testfall 44: the original lacks underlag, its posted correction does
    not; `/overview`, `/vouchers` and compliance give the same number."""
    original = posted_purchase(period_id, day=10)
    correction = posted_correction(original)

    assert VoucherRepository.get(correction).missing_attachment is False
    assert VoucherRepository.get(original).missing_attachment is True
    assert _listed(client, auth_headers, "true") == {original}
    assert _counts(client, auth_headers) == (1, 1, 1)


def test_44_missing_false_is_the_complement(client, auth_headers, period_id):
    """`?missing_attachment=false` is `NOT (…)` over the whole predicate
    (the parenthesis, U1): the correction and the referring voucher are on
    the complete side, the original on the missing side, each once."""
    original = posted_purchase(period_id, day=10)
    correction = posted_correction(original)
    difference = posted_purchase(period_id, total=12000, vat=0, day=16)
    via = posted_purchase(period_id, day=15)
    reference(difference, via, period_id)

    missing = _listed(client, auth_headers, "true")
    complete = _listed(client, auth_headers, "false")

    assert missing == {original, via}
    assert complete == {correction, difference}
    assert not missing & complete


def test_42_voucher_with_a_reference_does_not_lack_underlag(
    client, auth_headers, period_id
):
    """The predicate part of testfall 42: A-121 refers to the receipt
    through A-118 and does not lack underlag."""
    via = a118(period_id)
    # Over compliance's 500 kr threshold, so all three counters move.
    difference = posted_purchase(period_id, total=60000, vat=0, day=16)
    before = _counts(client, auth_headers)

    reference(difference, via, period_id)

    assert VoucherRepository.get(difference).missing_attachment is False
    # The reference does not give A-118 an underlag: that is the link's job.
    assert VoucherRepository.get(via).missing_attachment is True
    assert _counts(client, auth_headers) == tuple(n - 1 for n in before)


def test_fu2_correction_is_no_candidate(period_id):
    """`match_candidates` uses the same predicate: a correction of exactly
    the receipt's amount is not a candidate, the original is."""
    original = a118(period_id)
    correction = posted_correction(original)

    result = interpret(make_source(), "amount_diff")

    ids = {c["voucher_id"] for c in result["candidates"]}
    assert original in ids
    assert correction not in ids


def test_fu2_match_still_open_follows_the_predicate(period_id):
    """`match_still_open` reads the same predicate: a voucher that gets a
    reference is no longer an open match."""
    voucher = posted_purchase(period_id, total=12000, vat=0, day=16)
    via = a118(period_id)
    source_id = make_source()
    assert VoucherRepository.match_still_open(voucher, source_id) is True

    reference(voucher, via, period_id)

    assert VoucherRepository.match_still_open(voucher, source_id) is False


def test_fu2_the_predicate_names_both_new_conditions_once():
    """One shared predicate, no variants: the two conditions stand in
    `MISSING_ATTACHMENT_SQL`, inside its outer parenthesis."""
    from repositories import voucher_repo

    sql = voucher_repo.MISSING_ATTACHMENT_SQL
    assert sql.startswith("(") and sql.endswith(")")
    assert "vouchers.correction_of IS NULL" in sql
    assert "voucher_source_references" in sql
    source = voucher_repo.__file__
    with open(source, encoding="utf-8") as fh:
        text = fh.read()
    assert text.count("correction_of IS NULL") == 1


# ---------------------------------------------------------------------------
# FU16 — `referenced_by` on `VoucherResponse`, and the reference in
# `source-context` (§10.4; testfall 49d, 49e)
# ---------------------------------------------------------------------------


def _ref(voucher_id: str) -> dict:
    from repositories.voucher_repo import VoucherRepository

    voucher = VoucherRepository.get(voucher_id)
    assert voucher is not None
    return {"id": voucher.id, "series": voucher.series.value, "number": voucher.number}


def _listed_by_id(client, auth_headers, **params) -> dict:
    resp = client.get("/api/v1/vouchers", headers=auth_headers, params=params)
    assert resp.status_code == 200, resp.text
    return {v["id"]: v for v in resp.json()["vouchers"]}


def test_49e_referenced_by_names_the_difference_voucher(
    client, auth_headers, period_id
):
    """Testfall 49e: A-118 carries `referenced_by` = A-121 once A-121 refers
    to its receipt; every other voucher has `null`."""
    via = a118(period_id)
    difference = posted_purchase(period_id, total=12000, vat=0, day=16)
    other = posted_purchase(period_id, day=17)
    reference(difference, via, period_id)

    listed = _listed_by_id(client, auth_headers)
    single = client.get(f"/api/v1/vouchers/{via}", headers=auth_headers).json()

    assert listed[via]["referenced_by"] == _ref(difference)
    assert listed[difference]["referenced_by"] is None
    assert listed[other]["referenced_by"] is None
    assert single["referenced_by"] == _ref(difference)


def test_49e_the_latest_posted_of_several(client, auth_headers, period_id):
    via = a118(period_id)
    first = posted_purchase(period_id, total=12000, vat=0, day=16)
    second = posted_purchase(period_id, total=5000, vat=0, day=17)
    reference(first, via, period_id)
    reference(second, via, period_id)

    assert _listed_by_id(client, auth_headers)[via]["referenced_by"] == _ref(second)


def test_49e_no_query_per_row(client, auth_headers, period_id, monkeypatch):
    """Joined into the page's query like `corrected_by`: a page of five
    vouchers with references costs the same number of statements as a page
    of one."""
    from db.database import db

    def statements(n: int) -> int:
        calls: list = []
        original = db.execute

        def counting(sql, *args, **kwargs):
            calls.append(sql)
            return original(sql, *args, **kwargs)

        monkeypatch.setattr(db, "execute", counting)
        resp = client.get("/api/v1/vouchers", headers=auth_headers, params={"limit": n})
        monkeypatch.setattr(db, "execute", original)
        assert resp.status_code == 200
        assert len(resp.json()["vouchers"]) == n
        return len(calls)

    for day in range(10, 15):
        via = posted_purchase(period_id, day=day)
        reference(
            posted_purchase(period_id, total=1000, vat=0, day=day), via, period_id
        )

    assert statements(1) == statements(5)


def test_49d_source_context_of_the_difference_names_the_receipt_via_a118(
    client, auth_headers, period_id
):
    """The backend part of testfall 49d: A-121 has no link of its own; its
    `source-context` lists the receipt linked to A-118, as a
    `voucher_source` with `via_voucher_id` and that number, so the client
    can open it. A-118's own entry is unchanged and has no `via_`."""
    from repositories.intake_repo import IntakeRepository

    via = a118(period_id)
    difference = posted_purchase(period_id, total=12000, vat=0, day=16)
    source_id = make_source()
    IntakeRepository.create_voucher_link(
        intake_source_id=source_id, voucher_id=via, linked_by="agent"
    )
    from domain.intake_link import VoucherSourceReference
    from repositories.intake_link_repo import VoucherSourceReferenceRepository

    decision = make_decision(make_thread(period_id), source_id)
    VoucherSourceReferenceRepository.insert(
        VoucherSourceReference(
            voucher_id=difference,
            intake_source_id=source_id,
            via_voucher_id=via,
            decision_id=decision.id,
        )
    )

    own = client.get(f"/api/v1/vouchers/{via}/source-context", headers=auth_headers)
    referring = client.get(
        f"/api/v1/vouchers/{difference}/source-context", headers=auth_headers
    )

    assert own.status_code == referring.status_code == 200
    [direct] = own.json()["source_material"]
    assert direct["id"] == source_id
    assert "via_voucher_id" not in direct
    [through] = referring.json()["source_material"]
    assert through["kind"] == "voucher_source"
    assert through["id"] == source_id
    assert through["download_url"] == f"/api/v1/intake/{source_id}/file"
    assert through["via_voucher_id"] == via
    assert through["via_voucher_number"] == f"A-{_ref(via)['number']}"
