"""Granskning: the review key's limits and the review API
(docs/granskning.md §3, §4)."""

import re
import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.deps import (
    REVIEW_KEY_REFUSED_READS,
    get_caller,
    get_current_actor,
    get_human_actor,
)
from api.main import app
from config import settings
from db.database import db
from repositories.account_repo import AccountRepository
from repositories.review_repository import ReviewRepository
from services.auth import AuthService
from services.review import current_instruction_sha256

REVIEW_KEY = "test-review-key-0123456789"
UPLOAD = ("POST", "/api/v1/review/reports")
#: Public routes: no bearer is read, so there is no key to refuse.
PUBLIC_WRITES = {("POST", "/api/v1/auth/login"), ("POST", "/api/v1/auth/logout")}


@pytest.fixture(autouse=True)
def review_key(monkeypatch):
    monkeypatch.setattr(settings, "review_api_key", REVIEW_KEY)
    return REVIEW_KEY


@pytest.fixture
def review_headers():
    return {"Authorization": f"Bearer {REVIEW_KEY}"}


@pytest.fixture
def human_headers():
    return {"Authorization": f"Bearer {AuthService().create_jwt('stefan')}"}


@pytest.fixture
def client(test_db):
    return TestClient(app)


@pytest.fixture
def books(ledger_service, fiscal_year, test_period):
    """Two posted vouchers and a draft in 2026, a posted voucher in 2027."""
    for code, name, kind in [
        ("1930", "Företagskonto", "asset"),
        ("5010", "Lokalhyra", "expense"),
    ]:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, kind)

    def voucher(period_id, day, text, post=True):
        v = ledger_service.create_voucher(
            series="A",
            date=day,
            period_id=period_id,
            description=text,
            rows_data=[
                {"account": "5010", "debit": 500000, "credit": 0},
                {"account": "1930", "debit": 0, "credit": 500000},
            ],
            created_by="test",
        )
        if post:
            ledger_service.post_voucher(v.id, actor="test")
        return v.id

    other_year = ledger_service.periods.create_fiscal_year(
        start_date=date(2027, 1, 1), end_date=date(2027, 12, 31)
    )
    other_period = ledger_service.periods.create_period(
        fiscal_year_id=other_year.id,
        year=2027,
        month=3,
        start_date=date(2027, 3, 1),
        end_date=date(2027, 3, 31),
    )
    return {
        "fy": fiscal_year.id,
        "other_fy": other_year.id,
        "posted": [
            voucher(test_period.id, date(2026, 3, 1), "Hyra mars"),
            voucher(test_period.id, date(2026, 3, 2), "Hyra april"),
        ],
        "draft": voucher(test_period.id, date(2026, 3, 3), "Utkast", post=False),
        "other_year": voucher(other_period.id, date(2027, 3, 1), "Hyra 2027"),
    }


def report_body(fiscal_year_id, **overrides):
    body = {
        "id": str(uuid.uuid4()),
        "fiscal_year_id": fiscal_year_id,
        "reviewer": {"agent": "Claude Code", "model": "claude-opus-5-5"},
        "instruction_sha256": current_instruction_sha256(),
        "summary_markdown": "Alla stora poster prövades.",
        "examined_voucher_ids": [],
        "findings": [],
    }
    body.update(overrides)
    return body


def finding(**overrides):
    item = {
        "severity": "should_fix",
        "area": "underlag",
        "title": "Kvitto saknas",
        "description": "Verifikationen har inget underlag.",
    }
    item.update(overrides)
    return item


def _routes():
    """(method, path template) for every route in the app.

    FastAPI keeps an included router as one entry in `app.routes`; its
    routes are its effective route contexts."""
    for route in app.routes:
        contexts = (
            list(route.effective_route_contexts())
            if hasattr(route, "effective_route_contexts")
            else [route]
        )
        for context in contexts:
            path = getattr(context, "path_format", None) or getattr(
                context, "path", None
            )
            for method in getattr(context, "methods", None) or ():
                yield method, path


def _url(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", path)


# -- §3: the review key -------------------------------------------------------


def test_the_review_key_reads(client, review_headers, books):
    fy, voucher_id = books["fy"], books["posted"][0]
    for url in [
        "/api/v1/accounts",
        "/api/v1/fiscal-years",
        f"/api/v1/vouchers?fiscal_year_id={fy}&status=posted",
        f"/api/v1/vouchers/{voucher_id}",
        f"/api/v1/vouchers/{voucher_id}/source-context",
        f"/api/v1/reports/balance-sheet?fiscal_year_id={fy}",
        f"/api/v1/reports/income-statement?fiscal_year_id={fy}",
        f"/api/v1/reports/general-ledger/1930?fiscal_year_id={fy}",
        f"/api/v1/bokslut/{fy}/filer/bokforing.si",
        "/api/v1/review/instructions",
        "/api/v1/review/reports",
    ]:
        response = client.get(url, headers=review_headers)
        assert response.status_code == 200, (url, response.text)


@pytest.mark.parametrize(
    "method, url",
    [
        ("POST", "/api/v1/agent/vouchers"),
        ("POST", "/api/v1/vouchers/x/correct"),
        ("PUT", "/api/v1/agent-instructions/accounting"),
    ],
)
def test_the_review_key_cannot_write(client, review_headers, method, url):
    response = client.request(method, url, headers=review_headers, json={})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "review_key_read_only"


def test_every_write_route_refuses_the_review_key(client, review_headers):
    """Walks `app.routes`: anything but GET/HEAD is refused, except the
    upload. A new write route gets the refusal without anyone adding it."""
    walked = set(_routes())
    # The walk sees every route the schema does (it would silently miss
    # them were FastAPI to nest routers differently).
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            assert (method.upper(), path) in walked

    checked = 0
    for method, path in sorted(walked):
        if method in ("GET", "HEAD") or (method, path) in PUBLIC_WRITES:
            continue
        response = client.request(method, _url(path), headers=review_headers)
        if (method, path) == UPLOAD:
            assert response.status_code != 403, path
            continue
        assert response.status_code == 403, (method, path, response.text)
        assert response.json()["detail"]["code"] == "review_key_read_only"
        checked += 1
    assert checked > 50


def test_reads_that_write_refuse_the_review_key(client, review_headers):
    """The company instruction reads create a default document on the first
    read, so they are not reads for the review key."""
    for path in REVIEW_KEY_REFUSED_READS:
        response = client.get(path, headers=review_headers)
        assert response.status_code == 403, path
        assert response.json()["detail"]["code"] == "review_key_read_only"
    count = db.execute("SELECT COUNT(*) FROM agent_instruction_documents").fetchone()
    assert count[0] == 0


def test_without_a_review_key_an_empty_bearer_is_not_access(client, monkeypatch):
    monkeypatch.setattr(settings, "review_api_key", "")
    for header in ["Bearer ", "Bearer", "Bearer  "]:
        response = client.get("/api/v1/accounts", headers={"Authorization": header})
        assert response.status_code == 401
    response = client.get(
        "/api/v1/accounts", headers={"Authorization": f"Bearer {REVIEW_KEY}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_the_review_key_is_not_a_human_nor_the_agent():
    with pytest.raises(HTTPException) as exc_info:
        await get_human_actor(REVIEW_KEY)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "human_only"

    assert await get_current_actor(REVIEW_KEY) == "review_key"
    assert await get_current_actor(settings.api_key) == "api"
    caller = await get_caller(REVIEW_KEY)
    assert (caller.actor, caller.human) == ("review_key", False)


@pytest.mark.asyncio
async def test_a_review_key_equal_to_the_api_key_is_read_only(monkeypatch):
    """Misconfigured with the API key's value, the key fails closed."""
    monkeypatch.setattr(settings, "review_api_key", settings.api_key)
    assert await get_current_actor(settings.api_key) == "review_key"


# -- §4.1: the entrypoint ----------------------------------------------------


def test_the_entrypoint_is_public(client):
    response = client.get("/api/v1/review/entrypoint")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "bokfoering-api"
    assert data["auth"]["value_format"] == "Bearer <BOKFOERING_REVIEW_KEY>"
    assert data["auth"]["check"]["path"] == "/api/v1/review/instructions"
    steps = [step["action"] for step in data["startup_sequence"]]
    assert steps == ["read_instructions", "review", "upload_report"]
    assert data["startup_sequence"][2]["path"] == "/api/v1/review/reports"


def test_the_rest_of_the_review_api_needs_the_bearer(client):
    for url in [
        "/api/v1/review/instructions",
        "/api/v1/review/reports",
        "/api/v1/review/reports/x",
        "/api/v1/review/coverage",
    ]:
        assert client.get(url).status_code == 401
    assert client.post("/api/v1/review/reports", json={}).status_code == 401


# -- §4.3: the upload --------------------------------------------------------


def test_a_report_is_stored(client, review_headers, books):
    first, second = books["posted"]
    body = report_body(
        books["fy"],
        examined_voucher_ids=[first, second],
        findings=[
            finding(voucher_ids=[first], amount_ore=125000, rule="BFL 5 kap. 6 §"),
            finding(severity="observation", area="ovrigt", title="Iakttagelse"),
        ],
    )
    response = client.post("/api/v1/review/reports", json=body, headers=review_headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["id"] == body["id"]
    assert data["uploaded_by"] == "review_key"
    assert data["instruction_outdated"] is False
    assert data["counts"] == {"material": 0, "should_fix": 1, "observation": 1}
    assert data["examined_voucher_count"] == 2
    assert [f["position"] for f in data["findings"]] == [1, 2]
    flagged = data["findings"][0]
    assert flagged["voucher_ids"] == [first]
    assert flagged["vouchers"][0]["voucher_number"] == "A-1"
    assert flagged["vouchers"][0]["date"] == "2026-03-01"
    assert flagged["rule"] == "BFL 5 kap. 6 §"
    assert data["findings"][1]["vouchers"] == []

    detail = client.get(f"/api/v1/review/reports/{body['id']}", headers=review_headers)
    assert detail.status_code == 200
    assert detail.json() == data


def test_no_findings_is_a_valid_report(client, review_headers, books):
    response = client.post(
        "/api/v1/review/reports", json=report_body(books["fy"]), headers=review_headers
    )
    assert response.status_code == 201
    assert response.json()["findings"] == []
    assert response.json()["finding_count"] == 0


def test_uploaded_by_names_the_credential(client, auth_headers, human_headers, books):
    by_key = client.post(
        "/api/v1/review/reports", json=report_body(books["fy"]), headers=auth_headers
    )
    by_human = client.post(
        "/api/v1/review/reports", json=report_body(books["fy"]), headers=human_headers
    )
    assert by_key.status_code == 201
    assert by_key.json()["uploaded_by"] == "api_key"
    assert by_human.status_code == 201
    assert by_human.json()["uploaded_by"] == "stefan"


def test_a_voucher_id_must_be_posted_in_the_year(client, review_headers, books):
    body = report_body(
        books["fy"],
        examined_voucher_ids=[books["posted"][0], books["draft"]],
        findings=[finding(voucher_ids=[books["other_year"], "made-up"])],
    )
    response = client.post("/api/v1/review/reports", json=body, headers=review_headers)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_voucher_id"
    assert detail["invalid_voucher_ids"] == [
        books["draft"],
        books["other_year"],
        "made-up",
    ]
    assert ReviewRepository.get_report(body["id"]) is None
    assert db.execute("SELECT COUNT(*) FROM review_findings").fetchone()[0] == 0


def test_an_unknown_fiscal_year_is_refused(client, review_headers, books):
    response = client.post(
        "/api/v1/review/reports", json=report_body("nope"), headers=review_headers
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "fiscal_year_not_found"


@pytest.mark.parametrize(
    "override",
    [
        {"id": "not-a-uuid"},
        {"findings": [finding(severity="critical")]},
        {"findings": [finding(area="skatt")]},
        {"findings": [finding(title="x" * 301)]},
        {"summary_markdown": ""},
        {"reviewer": {"agent": "A"}},
        {"unknown_field": 1},
    ],
)
def test_an_invalid_body_is_refused(client, review_headers, books, override):
    body = report_body(books["fy"], **override)
    response = client.post("/api/v1/review/reports", json=body, headers=review_headers)
    assert response.status_code == 422
    assert db.execute("SELECT COUNT(*) FROM review_reports").fetchone()[0] == 0


def test_the_same_id_twice_is_one_report(client, review_headers, books):
    body = report_body(
        books["fy"],
        examined_voucher_ids=[books["posted"][0]],
        findings=[finding(voucher_ids=[books["posted"][0]])],
    )
    first = client.post("/api/v1/review/reports", json=body, headers=review_headers)
    again = client.post("/api/v1/review/reports", json=body, headers=review_headers)
    assert first.status_code == 201
    assert again.status_code == 200
    assert again.json() == first.json()
    assert db.execute("SELECT COUNT(*) FROM review_reports").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM review_findings").fetchone()[0] == 1


def test_the_same_id_with_another_body_is_a_conflict(client, review_headers, books):
    body = report_body(books["fy"])
    client.post("/api/v1/review/reports", json=body, headers=review_headers)
    changed = {**body, "findings": [finding()]}
    response = client.post(
        "/api/v1/review/reports", json=changed, headers=review_headers
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "review_report_id_conflict"
    assert db.execute("SELECT COUNT(*) FROM review_findings").fetchone()[0] == 0


def test_an_unknown_report_is_404(client, review_headers, books):
    response = client.get("/api/v1/review/reports/nope", headers=review_headers)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "review_report_not_found"


# -- §4.4: the list and the coverage -----------------------------------------


def test_the_list(client, review_headers, books):
    first, _second = books["posted"]
    older = report_body(
        books["fy"],
        instruction_sha256="0" * 64,
        findings=[finding(severity="material", voucher_ids=[first]), finding()],
    )
    newer = report_body(books["fy"], reviewer={"agent": "Codex", "model": "gpt-x"})
    other = report_body(books["other_fy"])
    for body in (older, newer, other):
        assert (
            client.post(
                "/api/v1/review/reports", json=body, headers=review_headers
            ).status_code
            == 201
        )

    response = client.get(
        f"/api/v1/review/reports?fiscal_year_id={books['fy']}", headers=review_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["current_instruction_sha256"] == current_instruction_sha256()
    by_id = {r["id"]: r for r in data["reports"]}
    assert set(by_id) == {older["id"], newer["id"]}
    assert data["reports"][0]["id"] == newer["id"]
    assert by_id[older["id"]]["instruction_outdated"] is True
    assert by_id[older["id"]]["counts"] == {
        "material": 1,
        "should_fix": 1,
        "observation": 0,
    }
    assert by_id[newer["id"]]["instruction_outdated"] is False
    assert by_id[newer["id"]]["reviewer"] == {"agent": "Codex", "model": "gpt-x"}
    assert "summary_markdown" not in by_id[newer["id"]]

    every_year = client.get("/api/v1/review/reports", headers=review_headers)
    assert every_year.json()["total"] == 3
    unknown = client.get(
        "/api/v1/review/reports?fiscal_year_id=nope", headers=review_headers
    )
    assert unknown.status_code == 404


def test_the_coverage(client, review_headers, books):
    first, second = books["posted"]
    by_claude = report_body(
        books["fy"],
        examined_voucher_ids=[first, second],
        findings=[finding(severity="material", voucher_ids=[first])],
    )
    by_codex = report_body(
        books["fy"],
        reviewer={"agent": "Codex", "model": "gpt-x"},
        findings=[
            finding(voucher_ids=[first]),
            finding(severity="observation", voucher_ids=[first]),
        ],
    )
    for body in (by_claude, by_codex):
        client.post("/api/v1/review/reports", json=body, headers=review_headers)

    response = client.get(
        f"/api/v1/review/coverage?fiscal_year_id={books['fy']}",
        headers=review_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["report_count"] == 2
    assert [v["id"] for v in data["vouchers"]] == [first, second]
    flagged = data["vouchers"][0]
    assert flagged["voucher_number"] == "A-1"
    assert flagged["examined_count"] == 2
    assert flagged["flagged_count"] == 2
    by_report = {e["report_id"]: e for e in flagged["flagged_by"]}
    assert by_report[by_claude["id"]]["severities"] == ["material"]
    assert by_report[by_codex["id"]]["severities"] == ["should_fix", "observation"]
    assert by_report[by_codex["id"]]["model"] == "gpt-x"
    examined_only = data["vouchers"][1]
    assert (examined_only["examined_count"], examined_only["flagged_count"]) == (1, 0)
    assert examined_only["flagged_by"] == []
