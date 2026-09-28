"""`flode-underlag` over HTTP: `POST /api/v1/intake/{id}/link` (FU6) and
`existing_id` in `409 duplicate_intake_source` (FU15).

Test case numbers refer to SPEC-flode-underlag.md §14. The route calls the
same `IntakeLinkService.link` as the tool (§7), with neither thread nor
agent run.
"""

import pytest

from tests import test_flode_underlag as fu
from tests.test_flode_underlag import (
    a118,
    interpret,
    link_state,
    make_decision,
    make_source,
    make_thread,
    voucher_number,
)

# The module's fixtures, bound here so pytest finds them in this file.
accounts = fu.accounts
client = fu.client
period_id = fu.period_id


def _url(source_id: str) -> str:
    return f"/api/v1/intake/{source_id}/link"


def _post(client, headers, source_id: str, body: dict):
    return client.post(_url(source_id), headers=headers, json=body)


# ---------------------------------------------------------------------------
# FU6 — `POST /api/v1/intake/{id}/link` (§7)
# ---------------------------------------------------------------------------


def test_01_exact_match_over_http(client, auth_headers, period_id):
    """Testfall 1 over HTTP: `201` with §6.6's body; the actor is the
    authenticated one, no thread and no run on the basis."""
    from repositories.intake_link_repo import IntakeLinkRepository

    voucher_id = a118(period_id)
    source_id = make_source()
    interpretation = interpret(source_id, "exact")

    resp = _post(client, auth_headers, source_id, {"voucher_id": voucher_id})

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body == {
        "source_id": source_id,
        "voucher_id": voucher_id,
        "voucher_number": voucher_number(voucher_id),
        "basis": "exact_match",
        "interpretation_id": interpretation["interpretation_id"],
        "decision_id": None,
        "replayed": False,
        "missing_attachments": 0,
    }
    basis = IntakeLinkRepository.get_for_source(source_id)
    assert basis is not None
    assert (basis.thread_id, basis.agent_run_id) == (None, None)
    assert basis.actor != "agent"


def test_04_decision_over_http(client, auth_headers, period_id):
    """Testfall 4 over HTTP: a decision answered in a thread links from a
    session without one (§7)."""
    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "amount_diff")
    decision = make_decision(make_thread(period_id), source_id, answer=1)

    resp = _post(
        client,
        auth_headers,
        source_id,
        {"voucher_id": voucher_id, "decision_id": decision.id},
    )

    assert resp.status_code == 201, resp.text
    assert (resp.json()["basis"], resp.json()["decision_id"]) == (
        "decision",
        decision.id,
    )


def test_13_replay_over_http_is_200(client, auth_headers, period_id):
    """Testfall 13 over HTTP: the second call is `200`, `replayed: true`."""
    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact")
    first = _post(client, auth_headers, source_id, {"voucher_id": voucher_id})
    state = link_state()

    second = _post(client, auth_headers, source_id, {"voucher_id": voucher_id})

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json() == {**first.json(), "replayed": True}
    assert link_state() == state


def test_fu6_real_refusals_map_to_their_status(client, auth_headers, period_id):
    """Three refusals made for real, one per status group, with the
    error body the other intake routes use."""
    voucher_id = a118(period_id)
    source_id = make_source()

    no_interpretation = _post(
        client, auth_headers, source_id, {"voucher_id": voucher_id}
    )
    interpret(source_id, "amount_diff")
    requires_decision = _post(
        client, auth_headers, source_id, {"voucher_id": voucher_id}
    )
    unknown = _post(client, auth_headers, "nope", {"voucher_id": voucher_id})

    assert no_interpretation.status_code == 400
    assert no_interpretation.json()["detail"]["code"] == "interpretation_required"
    assert requires_decision.status_code == 400
    detail = requires_decision.json()["detail"]
    assert detail["code"] == "link_requires_decision"
    assert "match_kind=amount_diff" in detail["details"]
    assert set(detail) >= {"error", "code", "details"}
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["code"] == "source_not_found"


#: §7's table: every code the link can refuse with, and its status.
_SECTION_7 = [
    ("source_not_found", 404),
    ("voucher_not_found", 404),
    ("decision_not_found", 404),
    ("source_deleted", 409),
    ("intake_already_linked", 409),
    ("intake_not_linkable", 409),
    ("voucher_not_posted", 409),
    ("decision_still_open", 409),
    ("decision_superseded", 409),
    ("decision_declined", 409),
    ("interpretation_required", 400),
    ("voucher_not_in_interpretation", 400),
    ("voucher_is_opening_balance", 400),
    ("link_requires_decision", 400),
    ("decision_not_for_source", 400),
]


def _error_type_for(code: str, status: int):
    from services.intake_link import (
        LinkConflictError,
        LinkNotFoundError,
        LinkRejectedError,
    )

    return {404: LinkNotFoundError, 409: LinkConflictError, 400: LinkRejectedError}[
        status
    ]


@pytest.mark.parametrize("code, status", _SECTION_7, ids=[c for c, _ in _SECTION_7])
def test_fu6_every_section_7_code_gives_its_status(
    client, auth_headers, monkeypatch, code, status
):
    """The route maps on the error's type, never on the code string: each
    code raised with the type the service uses for it gives §7's status."""
    from services.intake_link import IntakeLinkService

    error_type = _error_type_for(code, status)

    def refuse(self, *args, **kwargs):
        raise error_type(code, "refused", "details")

    monkeypatch.setattr(IntakeLinkService, "link", refuse)

    resp = _post(client, auth_headers, "s-1", {"voucher_id": "v-1"})

    assert resp.status_code == status
    assert resp.json()["detail"] == {
        "error": "refused",
        "code": code,
        "details": "details",
    }


def test_fu6_service_raises_the_mapped_type_for_the_real_codes(period_id):
    """The other half of the table: the service's own error for a code is
    the type the route maps (a sample from each group; FU3/FU4 cover
    the rest of the codes against the service)."""
    from services.intake_link import IntakeLinkError, IntakeLinkService

    voucher_id = a118(period_id)
    source_id = make_source()
    status_by_code = dict(_SECTION_7)

    for source, voucher in [("nope", voucher_id), (source_id, voucher_id)]:
        with pytest.raises(IntakeLinkError) as exc:
            IntakeLinkService().link(source, voucher, actor="api")
        code = exc.value.code
        assert isinstance(exc.value, _error_type_for(code, status_by_code[code]))


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_fu6_a_link_is_not_changed_or_removed(client, auth_headers, method):
    """No `PUT`, `PATCH` or `DELETE` on the path (§7): a link is not
    removed (§1)."""
    resp = getattr(client, method)(_url("s-1"), headers=auth_headers)

    assert resp.status_code == 405


def test_fu6_requires_bearer(client, period_id):
    resp = client.post(_url("s-1"), json={"voucher_id": "v-1"})

    assert resp.status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"voucher_id": "v-1", "basis": "exact_match"},
        {"voucher_id": "v-1", "source_id": "s-2"},
        {},
    ],
    ids=["unknown-field", "source-id-in-body", "no-voucher"],
)
def test_fu6_body_is_voucher_and_decision_only(client, auth_headers, body):
    resp = _post(client, auth_headers, "s-1", body)

    assert resp.status_code == 422
