"""A human approves a voucher without underlag (migration 051).

One press takes a posted voucher out of `Saknar underlag`, for `later` (the
underlag comes after the posting) or `none` (an accrual is its own
document). The waiver is append-only and undone by a revocation; the agent's
API key cannot waive or undo.
"""

import sqlite3

import pytest

from db.database import db
from repositories.audit_repo import AuditRepository
from repositories.voucher_repo import VoucherRepository
from services.auth import AuthService
from tests import test_flode_underlag as fu
from tests.test_flode_underlag import (
    a118,
    interpret,
    link,
    make_source,
    posted_purchase,
)
from tests.test_flode_underlag_predikat import _counts, _listed

accounts = fu.accounts
client = fu.client
period_id = fu.period_id


@pytest.fixture
def human_headers():
    return {"Authorization": f"Bearer {AuthService().create_jwt('stefan')}"}


def _attach(voucher_id: str) -> None:
    db.execute(
        "INSERT INTO attachments (id, voucher_id, filename, sha256, mime_type,"
        " stored_path, size_bytes) VALUES (?, ?, 'kvitto.pdf', 'x',"
        " 'application/pdf', '/tmp/x.pdf', 1)",
        (f"att-{voucher_id}", voucher_id),
    )
    db.commit()


def _waive(client, headers, voucher_id, reason="later", note=None):
    body = {"reason": reason}
    if note is not None:
        body["note"] = note
    return client.post(
        f"/api/v1/vouchers/{voucher_id}/underlag-waiver", headers=headers, json=body
    )


def _revoke(client, headers, voucher_id):
    return client.post(
        f"/api/v1/vouchers/{voucher_id}/underlag-waiver/revoke", headers=headers
    )


@pytest.mark.parametrize("reason", ["later", "none"])
def test_a_waived_voucher_leaves_the_list_and_every_count(
    client, auth_headers, human_headers, period_id, reason
):
    voucher_id = a118(period_id)
    assert voucher_id in _listed(client, auth_headers, "true")
    assert _counts(client, auth_headers)[:2] == (1, 1)

    response = _waive(client, human_headers, voucher_id, reason, note="Periodisering")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reason"] == reason
    assert body["note"] == "Periodisering"
    assert body["waived_by"] == "stefan"

    assert voucher_id not in _listed(client, auth_headers, "true")
    assert voucher_id in _listed(client, auth_headers, "false")
    assert _counts(client, auth_headers) == (0, 0, 0)

    detail = client.get(f"/api/v1/vouchers/{voucher_id}", headers=auth_headers).json()
    assert detail["missing_attachment"] is False
    assert detail["underlag_waiver"]["reason"] == reason


def test_the_agent_cannot_waive_or_undo(client, auth_headers, human_headers, period_id):
    voucher_id = a118(period_id)
    response = _waive(client, auth_headers, voucher_id)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "human_only"

    assert _waive(client, human_headers, voucher_id).status_code == 200
    response = _revoke(client, auth_headers, voucher_id)
    assert response.status_code == 403
    assert voucher_id not in _listed(client, auth_headers, "true")


def test_undo_puts_it_back_and_a_new_waiver_can_follow(
    client, auth_headers, human_headers, period_id
):
    voucher_id = a118(period_id)
    _waive(client, human_headers, voucher_id, "later")

    response = _revoke(client, human_headers, voucher_id)
    assert response.status_code == 200, response.text
    assert response.json()["revoked_by"] == "stefan"
    assert voucher_id in _listed(client, auth_headers, "true")
    # Undoing again is a replay, not an error.
    assert _revoke(client, human_headers, voucher_id).json() is None

    assert _waive(client, human_headers, voucher_id, "none").status_code == 200
    detail = client.get(f"/api/v1/vouchers/{voucher_id}", headers=auth_headers).json()
    assert detail["underlag_waiver"]["reason"] == "none"

    actions = [
        e.action.value for e in AuditRepository.get_history("voucher", voucher_id)
    ]
    assert actions[-3:] == [
        "underlag_waived",
        "underlag_waiver_revoked",
        "underlag_waived",
    ]


def test_same_reason_is_a_replay_another_is_a_conflict(
    client, human_headers, period_id
):
    voucher_id = a118(period_id)
    first = _waive(client, human_headers, voucher_id, "later").json()
    again = _waive(client, human_headers, voucher_id, "later")
    assert again.status_code == 200
    assert again.json()["id"] == first["id"]

    other = _waive(client, human_headers, voucher_id, "none")
    assert other.status_code == 409
    assert other.json()["detail"]["code"] == "waiver_exists"


def test_only_a_posted_voucher_without_underlag(client, human_headers, period_id):
    draft_id = posted_purchase(period_id, post=False)
    response = _waive(client, human_headers, draft_id)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "voucher_not_posted"

    voucher_id = a118(period_id)
    _attach(voucher_id)
    response = _waive(client, human_headers, voucher_id)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "not_missing_underlag"

    assert _waive(client, human_headers, "nope").status_code == 404
    assert _waive(client, human_headers, a118(period_id), "maybe").status_code == 422


def test_a_later_underlag_is_still_matched(client, human_headers, period_id):
    """`later` keeps the voucher a candidate: the underlag that arrives is
    set against it and linked without a decision."""
    voucher_id = a118(period_id)
    _waive(client, human_headers, voucher_id, "later")
    source_id = make_source()
    assert VoucherRepository.match_still_open(voucher_id, source_id) is True

    interpret(source_id, "exact")
    link(source_id, voucher_id)
    voucher = VoucherRepository.get(voucher_id)
    assert voucher.missing_attachment is False
    # The voucher has its document now; the waiver no longer speaks for it.
    assert voucher.underlag_waiver is None


def test_waivers_are_append_only(client, human_headers, period_id):
    voucher_id = a118(period_id)
    waiver_id = _waive(client, human_headers, voucher_id).json()["id"]
    _revoke(client, human_headers, voucher_id)
    for sql in (
        "UPDATE voucher_underlag_waivers SET reason = 'none' WHERE id = ?",
        "DELETE FROM voucher_underlag_waivers WHERE id = ?",
        "UPDATE voucher_underlag_waiver_revocations SET revoked_by = 'x'"
        " WHERE waiver_id = ?",
        "DELETE FROM voucher_underlag_waiver_revocations WHERE waiver_id = ?",
    ):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            db.execute(sql, (waiver_id,))
        db.rollback()
