"""Failed logins are throttled: after five, login is refused for a minute."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import services.auth as auth_module
from config import settings
from services.auth import (
    LOGIN_LOCKOUT_SECONDS,
    MAX_FAILED_LOGINS,
    reset_login_throttle,
)


@pytest.fixture(autouse=True)
def _reset_throttle():
    """The counter is process-global; leave it clean for other test files."""
    reset_login_throttle()
    yield
    reset_login_throttle()


@pytest.fixture
def clock(monkeypatch):
    """A controllable monotonic clock, seen only by services.auth."""
    now = [1000.0]
    monkeypatch.setattr(auth_module, "time", SimpleNamespace(monotonic=lambda: now[0]))
    return now


@pytest.fixture
def client(test_db):
    from api.main import app

    return TestClient(app)


def _login(client, password):
    return client.post(
        "/api/v1/auth/login",
        json={"username": settings.auth_username, "password": password},
    )


def _fail(client, times):
    for _ in range(times):
        assert _login(client, "wrong-password").status_code == 401


def test_sixth_attempt_is_refused_even_with_the_right_password(client, clock):
    _fail(client, MAX_FAILED_LOGINS)

    resp = _login(client, settings.auth_password)
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == str(LOGIN_LOCKOUT_SECONDS)


def test_login_works_again_after_the_window(client, clock):
    _fail(client, MAX_FAILED_LOGINS)

    clock[0] += LOGIN_LOCKOUT_SECONDS - 1
    assert _login(client, settings.auth_password).status_code == 429

    clock[0] += 1
    resp = _login(client, settings.auth_password)
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_success_resets_the_count(client, clock):
    _fail(client, MAX_FAILED_LOGINS - 1)
    assert _login(client, settings.auth_password).status_code == 200

    # Counting starts over: four more failures still do not lock.
    _fail(client, MAX_FAILED_LOGINS - 1)
    assert _login(client, settings.auth_password).status_code == 200
