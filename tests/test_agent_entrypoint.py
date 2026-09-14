"""Tests for the public agent instruction entrypoint."""

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from api.main import app
from config import settings

ENTRYPOINT_PATH = "/api/v1/agent-instructions/entrypoint"
DRIFT_DOC_PATH = Path("docs/to_agent/01_drift_och_atkomst.md")
PROCESS_DOC_PATH = Path("docs/to_agent/02_bokforingsprocess.md")
EXPECTED_PATHS = {
    "/api/v1/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/agent/test/ping",
    "/api/v1/agent-instructions/accounting",
    "/api/v1/accounting-corrections",
    "/api/v1/agent/intake/pending",
    "/api/v1/agent/intake/{source_id}/processing",
    "/api/v1/agent/intake/{source_id}/failed",
    "/api/v1/agent/vouchers",
    "/api/v1/vouchers/{voucher_id}/source-context",
    "/api/v1/vouchers/{voucher_id}/correction-draft",
    "/api/v1/vouchers/{voucher_id}/correction-notes/{note_id}/suggest",
    "/api/v1/vouchers/{voucher_id}/correction-notes/{note_id}/reject",
}


@pytest_asyncio.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _entrypoint(async_client: httpx.AsyncClient) -> dict:
    response = await async_client.get(ENTRYPOINT_PATH)
    assert response.status_code == 200
    return response.json()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.api_key}"}


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


@pytest.mark.asyncio
async def test_agent_entrypoint_is_public_without_auth(async_client):
    response = await async_client.get(ENTRYPOINT_PATH)

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "bokfoering-api"
    assert "version" in data
    assert data["auth"]["value_format"] == "Bearer <BOKFOERING_API_KEY>"


@pytest.mark.asyncio
async def test_agent_entrypoint_contains_expected_links_and_workflow_paths(
    async_client,
):
    data = await _entrypoint(async_client)
    serialized = json.dumps(data)

    for path in EXPECTED_PATHS:
        assert path in serialized

    assert data["links"]["openapi"] == "/openapi.json"
    assert data["workflow_endpoints"]["ping"]["path"] == "/api/v1/agent/test/ping"
    assert (
        data["workflow_endpoints"]["post_voucher"]["path"] == "/api/v1/agent/vouchers"
    )


@pytest.mark.asyncio
async def test_agent_entrypoint_documents_correction_note_workflow(async_client):
    data = await _entrypoint(async_client)
    serialized = json.dumps(data)

    assert "correction_note" in serialized
    assert "/api/v1/vouchers/{voucher_id}/correction-draft" in serialized
    assert "/api/v1/vouchers/{voucher_id}/source-context" in serialized
    assert "draft B-series" in serialized
    assert "Never edit the original posted voucher directly" in serialized


@pytest.mark.asyncio
async def test_agent_entrypoint_uses_relative_paths_only(async_client):
    data = await _entrypoint(async_client)

    for value in _strings(data):
        assert "http://" not in value
        assert "https://" not in value

    path_values = [value for value in _strings(data) if value.startswith("/")]
    assert path_values
    assert all(value.startswith("/") for value in path_values)


@pytest.mark.asyncio
async def test_agent_entrypoint_prescribes_startup_order_and_guardrails(async_client):
    data = await _entrypoint(async_client)
    sequence = data["startup_sequence"]

    assert sequence[0]["path"] == ENTRYPOINT_PATH
    assert sequence[0]["auth_required"] is False
    assert sequence[1]["path"] == "/api/v1/agent/test/ping"
    assert sequence[1]["auth_required"] is True
    assert sequence[2]["path"] == "/api/v1/agent-instructions/accounting"
    assert sequence[3]["path"] == "/api/v1/accounting-corrections"
    assert sequence[4]["path"] == "/api/v1/agent/intake/pending"

    guidance = json.dumps(data["startup_sequence"] + data["guardrails"])
    assert "one item at a time" in guidance
    assert "immutable" in guidance
    assert "correction vouchers" in guidance
    assert "failed or warning" in guidance
    assert "intake_source_ids" in guidance
    assert "pending queue" in guidance
    assert "guidance" in guidance
    assert "Idempotency-Key" in guidance
    assert "Idempotent-Replay" in guidance


@pytest.mark.asyncio
async def test_agent_entrypoint_tells_agents_to_stop_on_auth_failure(async_client):
    data = await _entrypoint(async_client)
    serialized = json.dumps(data).lower()

    assert data["auth"]["required_on"] == (
        "all workflow endpoints except this public entrypoint and health checks"
    )
    assert data["auth"]["check"]["on_401"]
    assert "401" in serialized
    assert "fix auth" in serialized or "fix the authorization header" in serialized
    assert "until ping returns 200" in serialized


@pytest.mark.asyncio
async def test_agent_entrypoint_documents_bank_input_transaction_source(async_client):
    data = await _entrypoint(async_client)
    contract = data["bank_input_contract"]
    serialized = json.dumps(contract)

    assert contract["queue_source"] == "/api/v1/agent/intake/pending"
    assert "transaction_ids" in contract["transaction_ids_source"]
    assert contract["download"] == "/api/v1/bank-inputs/{bank_input_id}/file"
    assert contract["post_voucher_fields"] == ["bank_input_ids", "bank_transaction_ids"]
    assert "/api/v1/bank-transactions" in serialized
    assert "not part of the current agent API" in serialized


@pytest.mark.asyncio
async def test_agent_entrypoint_discloses_unsupported_features(async_client):
    data = await _entrypoint(async_client)
    unsupported = " ".join(data["unsupported_features"]).lower()

    assert "persistent" in unsupported
    assert "credential lifecycle" in unsupported
    assert "generated tool-schema discovery" in unsupported
    # Durable idempotency now covers posting and correcting. The disclosure
    # narrows as the implementation grows; it never disappears.
    assert (
        "durable idempotency covers /api/v1/agent/vouchers and "
        "/api/v1/vouchers/{voucher_id}/correct" in unsupported
    )
    assert "/api/v1/bank-transactions" in unsupported


@pytest.mark.asyncio
async def test_agent_entrypoint_documents_idempotency_contract(async_client):
    data = await _entrypoint(async_client)
    contract = data["idempotency_contract"]

    assert contract["header"] == "Idempotency-Key"
    assert "UUID" in contract["value_format"]
    assert contract["required_on"] == [
        "/api/v1/agent/vouchers",
        "/api/v1/vouchers/{voucher_id}/correct",
    ]
    assert contract["server_enforced"] is False
    assert "same key" in contract["retry_rule"]
    assert "Idempotent-Replay: true" in contract["retry_rule"]
    assert "new key" in contract["one_key_per_event"]
    assert contract["conflicts"]["422"].startswith("idempotency_key_reuse")
    assert contract["conflicts"]["409"].startswith("request_in_flight")
    assert contract["conflicts"]["400"].startswith("invalid_idempotency_key")
    assert "idempotency_key_missing" in contract["transition"]


def test_agent_process_doc_requires_an_idempotency_key_on_posting():
    text = PROCESS_DOC_PATH.read_text(encoding="utf-8")

    assert "Idempotency-Key" in text
    assert "Idempotent-Replay: true" in text
    assert "idempotency_key_reuse" in text
    assert "request_in_flight" in text
    assert "En affärshändelse, en nyckel" in text
    assert "Omförsök använder samma nyckel" in text


@pytest.mark.asyncio
async def test_agent_entrypoint_excludes_sensitive_or_company_state_fields(
    async_client,
):
    serialized = json.dumps(await _entrypoint(async_client))

    for forbidden in [
        "http://",
        "https://",
        "secret_key",
        "api_key",
        "token_value",
        "original_filename",
    ]:
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_agent_ping_requires_auth(async_client):
    response = await async_client.post("/api/v1/agent/test/ping")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_agent_ping_returns_dynamic_bounded_auth_data(async_client):
    response = await async_client.post(
        "/api/v1/agent/test/ping",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "bokfoering-api"
    assert data["version"] == settings.api_version
    assert data["agent"] == "api"
    assert "timestamp" in data
    assert datetime.fromisoformat(data["timestamp"]).tzinfo is not None
    assert data["timestamp"] != "2026-03-21" + "T10:00:00"


@pytest.mark.asyncio
async def test_placeholder_agent_routes_are_removed(async_client):
    removed_routes = [
        ("GET", "/api/v1/agent/" + "spec/openapi", None),
        ("POST", "/api/v1/agent/" + "spec/tools", {}),
        ("GET", "/api/v1/agent/" + "keys", None),
        ("POST", "/api/v1/agent/" + "operations/idempotent/test-op", {}),
    ]

    for method, path, payload in removed_routes:
        response = await async_client.request(
            method,
            path,
            headers=_auth_headers(),
            json=payload,
        )
        assert response.status_code in {404, 405}


def test_agent_system_access_doc_does_not_advertise_removed_schema_routes():
    text = DRIFT_DOC_PATH.read_text(encoding="utf-8")

    assert "GET /api/v1/agent/spec/openapi" not in text
    assert "POST /api/v1/agent/spec/tools" not in text
    assert "finns inte i aktuell version" in text
