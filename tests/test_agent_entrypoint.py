"""Tests for the public agent instruction entrypoint."""

import json
from collections.abc import Iterator

import httpx
import pytest
import pytest_asyncio

from api.main import app


ENTRYPOINT_PATH = "/api/v1/agent-instructions/entrypoint"
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
async def test_agent_entrypoint_contains_expected_links_and_workflow_paths(async_client):
    data = await _entrypoint(async_client)
    serialized = json.dumps(data)

    for path in EXPECTED_PATHS:
        assert path in serialized

    assert data["links"]["openapi"] == "/openapi.json"
    assert data["workflow_endpoints"]["ping"]["path"] == "/api/v1/agent/test/ping"
    assert data["workflow_endpoints"]["post_voucher"]["path"] == "/api/v1/agent/vouchers"


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


@pytest.mark.asyncio
async def test_agent_entrypoint_discloses_unsupported_features(async_client):
    data = await _entrypoint(async_client)
    unsupported = " ".join(data["unsupported_features"]).lower()

    assert "persistent" in unsupported
    assert "credential lifecycle" in unsupported
    assert "generated tool-schema discovery" in unsupported
    assert "durable idempotency" in unsupported


@pytest.mark.asyncio
async def test_agent_entrypoint_excludes_sensitive_or_company_state_fields(async_client):
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
