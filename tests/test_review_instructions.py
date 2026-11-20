"""The review instruction (docs/granskning.md §6): it exists, its hash is
stable, the bookkeeping agent never gets it, and `read_endpoints` names
routes that exist."""

import hashlib
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from config import settings
from repositories.system_instructions import (
    DOCS_TO_REVIEWER_DIR,
    REVIEWER_INSTRUCTION_FILES,
    get_accounting_system_instructions,
    get_reviewer_instructions,
    get_system_instructions,
)
from services.review import ReviewReportIn, read_endpoints

REVIEW_KEY = "test-review-key-0123456789"
HEADINGS = [
    "Roll",
    "Ordning",
    "Företagets instruktioner",
    "Urval",
    "Riskområden",
    "Bevis",
    "Allvarlighet",
    "Begränsningar",
    "Rapporten",
]
FORBIDDEN = re.compile(r"revision\w*|revisor\w*", re.IGNORECASE)


@pytest.fixture
def client(test_db, monkeypatch):
    monkeypatch.setattr(settings, "review_api_key", REVIEW_KEY)
    return TestClient(app, headers={"Authorization": f"Bearer {REVIEW_KEY}"})


def test_every_instruction_file_exists():
    for filename, _title in REVIEWER_INSTRUCTION_FILES:
        assert (Path(DOCS_TO_REVIEWER_DIR) / filename).is_file(), filename


def test_the_instruction_has_its_headings():
    markdown = get_reviewer_instructions()["content_markdown"]
    headings = re.findall(r"^#+ (.+)$", markdown, re.MULTILINE)
    for heading in HEADINGS:
        assert heading in headings, heading


def test_the_hash_is_stable_and_over_the_markdown():
    first = get_reviewer_instructions()
    second = get_reviewer_instructions()
    assert first["sha256"] == second["sha256"]
    assert (
        first["sha256"]
        == hashlib.sha256(first["content_markdown"].encode("utf-8")).hexdigest()
    )


def test_the_instruction_never_calls_itself_an_audit():
    """The words appear only in a sentence that says it is not one."""
    markdown = get_reviewer_instructions()["content_markdown"]
    sentences = re.split(r"(?<=[.!?])\s+", markdown)
    for sentence in sentences:
        if FORBIDDEN.search(sentence):
            assert re.search(r"\b(inte|ingen)\b", sentence), sentence


def test_the_bookkeeping_agent_does_not_get_it():
    review = get_reviewer_instructions()["content_markdown"]
    marker = "Du granskar ett räkenskapsår för styrelsens räkning"
    assert marker in review
    for instructions in (
        get_system_instructions(),
        get_accounting_system_instructions(),
    ):
        assert marker not in instructions["content_markdown"]
        assert not set(instructions["files"]) & {
            f for f, _ in REVIEWER_INSTRUCTION_FILES
        }


def test_the_instructions_route(client, ledger_service):
    older = ledger_service.periods.create_fiscal_year(
        start_date=date(2025, 1, 1), end_date=date(2025, 12, 31)
    )
    latest = ledger_service.periods.create_fiscal_year(
        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
    )
    response = client.get("/api/v1/review/instructions")
    assert response.status_code == 200
    data = response.json()
    assert data["fiscal_year"]["id"] == latest.id
    assert [y["id"] for y in data["fiscal_years"]] == [older.id, latest.id]
    instruction = get_reviewer_instructions()
    assert data["instructions_markdown"] == instruction["content_markdown"]
    assert data["instruction_sha256"] == instruction["sha256"]
    assert data["report_schema"] == ReviewReportIn.model_json_schema()
    assert data["read_endpoints"]["sie4"] == (
        f"/api/v1/bokslut/{latest.id}/filer/bokforing.si"
    )
    assert data["company_instructions"]["is_default"] is True
    assert data["company_instructions"]["content_markdown"]

    chosen = client.get(f"/api/v1/review/instructions?fiscal_year_id={older.id}")
    assert chosen.json()["fiscal_year"]["id"] == older.id
    # The instruction tells the reviewer how to treat a year that is not over.
    assert chosen.json()["fiscal_year"]["ended"] is True
    assert isinstance(data["fiscal_year"]["ended"], bool)
    unknown = client.get("/api/v1/review/instructions?fiscal_year_id=nope")
    assert unknown.status_code == 404


def test_the_instructions_route_writes_nothing(client, ledger_service, test_db):
    ledger_service.periods.create_fiscal_year(
        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
    )
    client.get("/api/v1/review/instructions")
    count = test_db.execute("SELECT COUNT(*) FROM agent_instruction_documents")
    assert count.fetchone()[0] == 0


def test_every_read_endpoint_is_a_get_route_the_review_key_may_read():
    """Each path in `read_endpoints` matches a GET route in the app with the
    same query parameters, and none is refused to the review key."""
    from api.deps import review_key_allows

    schema = app.openapi()["paths"]
    patterns = {
        re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", path) + "$"): path
        for path, operations in schema.items()
        if "get" in operations
    }
    for name, url in read_endpoints("FY").items():
        path, _, query = url.partition("?")
        matches = [template for rx, template in patterns.items() if rx.match(path)]
        assert matches, (name, url)
        template = max(matches, key=lambda t: t.count("/") - t.count("{"))
        assert review_key_allows("GET", template), (name, template)
        params = {p["name"] for p in schema[template]["get"].get("parameters", [])}
        for pair in filter(None, query.split("&")):
            assert pair.split("=")[0] in params, (name, pair)
