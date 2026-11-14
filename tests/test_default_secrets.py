"""The server refuses to start with the well-known default secrets."""

import pytest

import main
from config import (
    DEFAULT_API_KEY,
    DEFAULT_AUTH_PASSWORD,
    DEFAULT_JWT_SECRET,
    settings,
)


@pytest.fixture
def uvicorn_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(main.uvicorn, "run", lambda *a, **kw: calls.append(kw))
    return calls


def _set_secrets(monkeypatch, api_key, password, jwt_secret, debug):
    monkeypatch.setattr(settings, "api_key", api_key)
    monkeypatch.setattr(settings, "auth_password", password)
    monkeypatch.setattr(settings, "jwt_secret", jwt_secret)
    monkeypatch.setattr(settings, "debug", debug)


def test_refused_with_default_secrets_and_debug_off(monkeypatch, uvicorn_calls, capsys):
    _set_secrets(
        monkeypatch,
        DEFAULT_API_KEY,
        "a-real-password",
        DEFAULT_JWT_SECRET,
        debug=False,
    )
    with pytest.raises(SystemExit) as exc:
        main.run_server()
    assert exc.value.code != 0
    assert uvicorn_calls == []
    err = capsys.readouterr().err
    assert "BOKFOERING_API_KEY" in err
    assert "JWT_SECRET" in err
    assert "AUTH_PASSWORD" not in err
    assert "DEBUG=true" in err


def test_allowed_with_default_secrets_and_debug_on(monkeypatch, uvicorn_calls):
    _set_secrets(
        monkeypatch,
        DEFAULT_API_KEY,
        DEFAULT_AUTH_PASSWORD,
        DEFAULT_JWT_SECRET,
        debug=True,
    )
    main.run_server()
    assert len(uvicorn_calls) == 1


def test_allowed_with_all_secrets_set(monkeypatch, uvicorn_calls):
    _set_secrets(monkeypatch, "k" * 32, "a-real-password", "s" * 32, debug=False)
    assert settings.default_secrets() == []
    main.run_server()
    assert len(uvicorn_calls) == 1
