"""Deterministic verification for Phase 7 deployment documentation."""

from pathlib import Path

import pytest


DEPLOYMENT_PATH = Path("DEPLOYMENT.md")


@pytest.fixture
def deployment_text():
    """Read DEPLOYMENT.md as a single string."""
    assert DEPLOYMENT_PATH.exists()
    return DEPLOYMENT_PATH.read_text(encoding="utf-8")


@pytest.fixture
def openclaw_section(deployment_text):
    """Extract the OpenClaw setup section from DEPLOYMENT.md."""
    start = deployment_text.find("### 10. Koppla OpenClaw")
    assert start != -1, "OpenClaw setup section not found"
    end = deployment_text.find("## Uppdatera säkert på LAN", start)
    assert end != -1, "OpenClaw section end not found"
    return deployment_text[start:end]


# --- Section ordering tests ---


def test_deployment_has_openclaw_section_after_first_login(deployment_text):
    first_login = deployment_text.find("### 9. Första inloggning")
    openclaw = deployment_text.find("### 10. Koppla OpenClaw")
    update_lan = deployment_text.find("## Uppdatera säkert på LAN")
    assert first_login < openclaw < update_lan


# --- OpenClaw setup section content tests ---


def test_openclaw_section_has_api_url(openclaw_section):
    assert 'BOK_API_URL="http://SERVER_IP_OR_HOSTNAME:8000"' in openclaw_section


def test_openclaw_section_has_api_key(openclaw_section):
    assert "API_KEY=" in openclaw_section


def test_openclaw_section_has_bearer_auth(openclaw_section):
    assert "Authorization: Bearer ${API_KEY}" in openclaw_section


def test_openclaw_section_has_health_path(openclaw_section):
    assert "/health" in openclaw_section


def test_openclaw_section_has_entrypoint_path(openclaw_section):
    assert "/api/v1/agent-instructions/entrypoint" in openclaw_section


def test_openclaw_section_has_ping_path(openclaw_section):
    assert "/api/v1/agent/test/ping" in openclaw_section


# --- URL separation tests ---


def test_deployment_has_frontend_url(deployment_text):
    assert "http://SERVER_IP_OR_HOSTNAME:3000/login" in deployment_text


def test_deployment_has_backend_url(deployment_text):
    assert "http://SERVER_IP_OR_HOSTNAME:8000" in deployment_text


def test_deployment_warns_about_docker_internal_url(deployment_text):
    assert "BACKEND_URL=http://api:8000" in deployment_text


def test_deployment_has_public_https_urls(deployment_text):
    assert "https://${API_DOMAIN}" in deployment_text
    assert "https://${APP_DOMAIN}" in deployment_text


# --- Troubleshooting tests ---


def test_troubleshooting_covers_401(deployment_text):
    assert "401" in deployment_text


def test_troubleshooting_covers_wrong_port_or_url(deployment_text):
    text = deployment_text.lower()
    assert "3000" in text or "fel" in text or "port" in text
    assert "backend-url" in text or "base url" in text or "url" in text


def test_troubleshooting_covers_docker_internal_url(deployment_text):
    troubleshooting = deployment_text.find("## Felsökning")
    assert troubleshooting != -1
    felsokning_text = deployment_text[troubleshooting:]
    assert "BACKEND_URL=http://api:8000" in felsokning_text
    assert "Docker-intern" in felsokning_text or "docker" in felsokning_text.lower()


# --- Unsupported features absence tests ---


def test_openclaw_section_does_not_claim_mcp(openclaw_section):
    assert "MCP" not in openclaw_section


def test_openclaw_section_does_not_claim_persistent_key_lifecycle(openclaw_section):
    assert "persistent" not in openclaw_section.lower()
    assert "key lifecycle" not in openclaw_section.lower()


def test_openclaw_section_does_not_claim_generated_tool_schema(openclaw_section):
    assert "generated tool" not in openclaw_section.lower()


def test_openclaw_section_does_not_claim_durable_idempotency(openclaw_section):
    assert "durable idempotency" not in openclaw_section.lower()


def test_openclaw_section_does_not_claim_model_provider_setup(openclaw_section):
    assert "model provider" not in openclaw_section.lower()
    assert "openai" not in openclaw_section.lower()
    assert "anthropic" not in openclaw_section.lower()


def test_openclaw_section_has_no_expected_response_snippets(openclaw_section):
    """Setup docs should not include expected JSON or response-body snippets."""
    assert "```json" not in openclaw_section
    assert "status" not in openclaw_section or "status" in openclaw_section
    # A stricter check: no block that looks like a JSON response example
    lines = openclaw_section.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("{") and i > 0 and lines[i - 1].strip().startswith("```"):
            pytest.fail(f"Expected JSON response snippet found: {line}")


def test_openclaw_section_has_setup_only_constraint(openclaw_section):
    assert "behandla inte pending intake" in openclaw_section.lower() or "pending intake" in openclaw_section.lower()
    assert "starta inte bokföringen" in openclaw_section.lower() or "bokföringen" in openclaw_section.lower()
