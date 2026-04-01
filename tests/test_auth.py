"""Tests for auth endpoints — register, login, logout, and /me."""

import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from db.database import db, Database


@pytest.fixture(scope="function")
def auth_db():
    """Create temporary test database for auth tests."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Swap the global db to use the temp path
    original_path = db.db_path
    db.db_path = path
    db.disconnect()

    db.init_db()

    yield db

    db.disconnect()
    db.db_path = original_path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture(scope="function")
def client(auth_db):
    """FastAPI test client."""
    from api.main import app
    return TestClient(app)


# --------------------------------------------------------------------------
# Register
# --------------------------------------------------------------------------

class TestRegister:
    def test_register_success(self, client):
        resp = client.post(
            "/auth/register",
            json={"email": "alice@example.com", "password": "secret123", "full_name": "Alice"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "alice@example.com"
        assert data["full_name"] == "Alice"
        assert "id" in data

    def test_register_duplicate_email(self, client):
        client.post(
            "/auth/register",
            json={"email": "bob@example.com", "password": "pass1"},
        )
        resp = client.post(
            "/auth/register",
            json={"email": "bob@example.com", "password": "pass2"},
        )
        assert resp.status_code == 409

    def test_register_invalid_email(self, client):
        resp = client.post(
            "/auth/register",
            json={"email": "not-an-email", "password": "secret"},
        )
        assert resp.status_code == 422


# --------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------

class TestLogin:
    def test_login_success(self, client):
        client.post(
            "/auth/register",
            json={"email": "carol@example.com", "password": "mypass"},
        )
        resp = client.post(
            "/auth/login",
            json={"email": "carol@example.com", "password": "mypass"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client):
        client.post(
            "/auth/register",
            json={"email": "dave@example.com", "password": "rightpass"},
        )
        resp = client.post(
            "/auth/login",
            json={"email": "dave@example.com", "password": "wrongpass"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": "pass"},
        )
        assert resp.status_code == 401


# --------------------------------------------------------------------------
# Logout
# --------------------------------------------------------------------------

class TestLogout:
    def test_logout_returns_200(self, client):
        resp = client.post("/auth/logout")
        assert resp.status_code == 200


# --------------------------------------------------------------------------
# /me
# --------------------------------------------------------------------------

class TestMe:
    def test_me_success(self, client):
        client.post(
            "/auth/register",
            json={"email": "eve@example.com", "password": "pass"},
        )
        login_resp = client.post(
            "/auth/login",
            json={"email": "eve@example.com", "password": "pass"},
        )
        token = login_resp.json()["access_token"]
        resp = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "eve@example.com"

    def test_me_missing_token(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_invalid_token(self, client):
        resp = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401
