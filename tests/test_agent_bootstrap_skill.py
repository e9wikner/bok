"""Contract tests for the setup-only Bok agent skill."""

import os
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
SKILL_PATH = ROOT / ".agents/skills/bok-connect/SKILL.md"
CLAUDE_LINK = ROOT / ".claude/skills/bok-connect"
WRAPPER_PATH = ROOT / "scripts/bok-curl"

# A secret in any shape, not just a KEY=<value> assignment.
SECRET_SHAPE = re.compile(r"\b(?:[0-9a-fA-F]{32,}|[A-Za-z0-9+/]{40,}={0,2})\b")


def test_skill_documents_default_host_and_public_entrypoint():
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "http://localhost:8000" in text
    assert "/api/v1/agent-instructions/entrypoint" in text


def test_skill_stays_within_bootstrap_line_budget():
    assert len(SKILL_PATH.read_text(encoding="utf-8").splitlines()) <= 60


def test_skill_contains_no_api_key_value():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert not re.search(
        r"BOKFOERING_API_KEY\s*[=:]\s*[A-Za-z0-9+/=_-]{16,}",
        text,
    )


def test_skill_contains_no_secret_like_token():
    assert not SECRET_SHAPE.search(SKILL_PATH.read_text(encoding="utf-8"))


def test_skill_symlink_resolves_to_existing_file():
    assert CLAUDE_LINK.is_symlink()
    assert (CLAUDE_LINK.resolve() / "SKILL.md").is_file()


def test_wrapper_script_is_executable():
    assert WRAPPER_PATH.is_file()
    assert os.access(WRAPPER_PATH, os.X_OK)


def test_wrapper_resolves_host_and_key_itself():
    text = WRAPPER_PATH.read_text(encoding="utf-8")

    assert "BOK_API_URL" in text
    assert "BOKFOERING_API_KEY" in text
    assert "http://localhost:8000" in text


def test_wrapper_contains_no_secret_like_token():
    assert not SECRET_SHAPE.search(WRAPPER_PATH.read_text(encoding="utf-8"))


def test_skill_names_the_vendored_wrapper():
    """Keeps the skill and the script in the repo from drifting apart."""
    assert "bok-curl" in SKILL_PATH.read_text(encoding="utf-8")
