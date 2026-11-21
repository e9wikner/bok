"""Temporary review keys (migration 056, services/review_token.py): a human
copies a prompt with a key that lives an hour and can only read and upload a
review report."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from config import settings
from db.database import db
from services import review_token as review_token_module
from tests.test_review_api import (  # noqa: F401
    books,
    client,
    human_headers,
    report_body,
)

ENTRYPOINT = "http://bok.example:8000/api/v1/review/entrypoint"


@pytest.fixture(autouse=True)
def no_static_review_key(monkeypatch):
    """The temporary key works on its own; the static one may be unset."""
    monkeypatch.setattr(settings, "review_api_key", "")


def issue(client, headers, fy, url=ENTRYPOINT):  # noqa: F811
    return client.post(
        "/api/v1/review/tokens",
        json={"fiscal_year_id": fy, "entrypoint_url": url},
        headers=headers,
    )


@pytest.fixture
def token(client, human_headers, books):  # noqa: F811
    response = issue(client, human_headers, books["fy"])
    assert response.status_code == 201, response.text
    return response.json()


def bearer(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def test_a_human_gets_a_key_and_a_prompt(token, books):  # noqa: F811
    assert token["token"].startswith("bokrev_")
    prompt = token["prompt"]
    assert token["token"] in prompt
    assert ENTRYPOINT in prompt
    assert f"fiscal_year_id={books['fy']}" in prompt
    assert "http://bok.example:8000/api/v1/review/instructions" in prompt
    expires = datetime.fromisoformat(token["expires_at"])
    left = expires - datetime.now(timezone.utc)
    assert timedelta(minutes=55) < left <= timedelta(minutes=60)


def test_only_the_hash_is_stored(token):
    row = db.execute("SELECT * FROM review_tokens").fetchone()
    assert token["token"] not in tuple(row)


def test_the_agent_cannot_issue_a_key(client, auth_headers, books):  # noqa: F811
    response = issue(client, auth_headers, books["fy"])
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "human_only"


def test_a_review_key_cannot_issue_a_key(client, token, books):  # noqa: F811
    response = issue(client, bearer(token["token"]), books["fy"])
    assert response.status_code == 403
    listed = client.get("/api/v1/review/tokens", headers=bearer(token["token"]))
    assert listed.status_code == 403
    assert listed.json()["detail"]["code"] == "human_only"


@pytest.mark.parametrize(
    "url", ["http://bok/api/v1/vouchers", "ftp://bok/api/v1/review/entrypoint", ""]
)
def test_a_bad_entrypoint_url_is_refused(  # noqa: F811
    client, human_headers, books, url  # noqa: F811
):
    response = issue(client, human_headers, books["fy"], url)
    assert response.status_code == 422


def test_an_unknown_year_is_404(client, human_headers, books):  # noqa: F811
    assert issue(client, human_headers, "nope").status_code == 404


def test_the_key_reads_and_uploads(client, token, books):  # noqa: F811
    h = bearer(token["token"])
    fy = books["fy"]
    for url in [
        f"/api/v1/review/instructions?fiscal_year_id={fy}",
        f"/api/v1/vouchers?fiscal_year_id={fy}&status=posted",
        f"/api/v1/vouchers/{books['posted'][0]}",
    ]:
        assert client.get(url, headers=h).status_code == 200, url
    response = client.post("/api/v1/review/reports", json=report_body(fy), headers=h)
    assert response.status_code == 201, response.text
    assert response.json()["uploaded_by"] == "review_key"


@pytest.mark.parametrize(
    "method, url",
    [
        ("POST", "/api/v1/agent/vouchers"),
        ("POST", "/api/v1/vouchers/x/correct"),
        ("PUT", "/api/v1/company-info"),
    ],
)
def test_the_key_cannot_write(client, token, method, url):  # noqa: F811
    response = client.request(method, url, headers=bearer(token["token"]), json={})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "review_key_read_only"


def test_a_revoked_key_stops_working(client, human_headers, token):  # noqa: F811
    h = bearer(token["token"])
    assert client.get("/api/v1/accounts", headers=h).status_code == 200
    revoked = client.post(
        f"/api/v1/review/tokens/{token['id']}/revoke", headers=human_headers
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"]
    assert client.get("/api/v1/accounts", headers=h).status_code == 401
    # A replay is not an error.
    again = client.post(
        f"/api/v1/review/tokens/{token['id']}/revoke", headers=human_headers
    )
    assert again.status_code == 200
    listed = client.get("/api/v1/review/tokens", headers=human_headers).json()
    assert listed["tokens"] == []


def test_an_expired_key_stops_working(client, token, monkeypatch):  # noqa: F811
    later = datetime.now(timezone.utc) + timedelta(minutes=61)
    monkeypatch.setattr(review_token_module, "_now", lambda: later)
    assert (
        client.get("/api/v1/accounts", headers=bearer(token["token"])).status_code
        == 401
    )


def test_an_unknown_key_is_401(client, test_db):  # noqa: F811
    assert (
        client.get("/api/v1/accounts", headers=bearer("bokrev_nope")).status_code == 401
    )


def test_issue_and_revoke_are_audit_logged(client, human_headers, token):  # noqa: F811
    client.post(f"/api/v1/review/tokens/{token['id']}/revoke", headers=human_headers)
    actions = [
        r["action"]
        for r in db.execute(
            "SELECT action FROM audit_log WHERE entity_type = 'review_token'"
        ).fetchall()
    ]
    assert sorted(actions) == ["review_token_issued", "review_token_revoked"]


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE review_tokens SET expires_at = '2999-01-01'",
        "DELETE FROM review_tokens",
    ],
)
def test_the_tables_are_append_only(token, sql):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(sql)
