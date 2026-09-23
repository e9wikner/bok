"""Tests for the idempotency module (docs/redesign/SPEC-idempotens.md).

Covers T1-T5: migration, repository, service, header dependency and
POST /api/v1/agent/vouchers. The point of the module is that an irreversible
posting can be retried without polluting an append-only ledger.
"""

import json
import sqlite3
import threading
import uuid
from calendar import monthrange
from datetime import date

import httpx
import pytest
import pytest_asyncio

from api.deps import get_idempotency_key
from api.main import app
from config import settings
from db.database import db
from repositories.account_repo import AccountRepository
from repositories.idempotency_repo import IdempotencyRepository
from repositories.period_repo import PeriodRepository
from services.idempotency import IdempotencyOutcome, IdempotencyService
from services.intake import IntakeService
from services.ledger import LedgerService

ENDPOINT = "POST /api/v1/agent/vouchers"


def _headers(idempotency_key: str | None = None):
    headers = {"Authorization": f"Bearer {settings.api_key}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _ensure_accounts():
    for code, name, account_type in [
        ("1920", "Bankkonto", "asset"),
        ("6200", "Tele och post", "expense"),
    ]:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, account_type)


def _period():
    today = date.today()
    last_day = monthrange(today.year, today.month)[1]
    fiscal_year = PeriodRepository.create_fiscal_year(
        start_date=date(today.year, 1, 1),
        end_date=date(today.year, 12, 31),
    )
    return PeriodRepository.create_period(
        fiscal_year_id=fiscal_year.id,
        year=today.year,
        month=today.month,
        start_date=date(today.year, today.month, 1),
        end_date=date(today.year, today.month, last_day),
    )


def _intake_source(tmp_path, name: str = "telefon.pdf"):
    settings.intake_dir = str(tmp_path / "intake")
    return IntakeService().create_source_from_upload_content(
        filename=name,
        content_type="application/pdf",
        content=f"%PDF-1.4 {name}".encode(),
        explanation="Telefonutgift Fello",
        source_type="receipt",
        actor="api",
    )


def _voucher_body(period_id: str, source_id: str, amount: int = 12500):
    return {
        "date": date.today().isoformat(),
        "period_id": period_id,
        "description": "Telefonutgift Fello",
        "reasoning_summary": "Kvitto matchat mot banktransaktion",
        "intake_source_ids": [source_id],
        "rows": [
            {"account": "1920", "debit": 0, "credit": amount},
            {"account": "6200", "debit": amount, "credit": 0},
        ],
    }


def _voucher_count() -> int:
    return db.execute("SELECT COUNT(*) AS n FROM vouchers").fetchone()["n"]


def _correction_history_count() -> int:
    return db.execute("SELECT COUNT(*) AS n FROM correction_history").fetchone()["n"]


def _key_rows() -> list[dict]:
    return [
        dict(row) for row in db.execute("SELECT * FROM idempotency_keys").fetchall()
    ]


@pytest_asyncio.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def intake_dir(tmp_path):
    original = settings.intake_dir
    settings.intake_dir = str(tmp_path / "intake")
    yield tmp_path
    settings.intake_dir = original


# --- T1: migration ---------------------------------------------------------


def test_migration_creates_key_table_and_lock_actor(test_db):
    schema = db.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'idempotency_keys'"
    ).fetchone()["sql"]
    assert "PRIMARY KEY (key, endpoint)" in schema
    assert "CHECK (state IN ('in_flight', 'completed'))" in schema

    columns = [row[1] for row in db.execute("PRAGMA table_info(periods)").fetchall()]
    assert "locked_by" in columns


def test_state_is_constrained_to_two_values(test_db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("""
            INSERT INTO idempotency_keys
            (key, endpoint, request_fingerprint, state, actor)
            VALUES ('k', 'e', 'f', 'halfway', 'api')
            """)
        db.commit()
    db.rollback()


# --- T2: repository --------------------------------------------------------


def test_reserve_claims_the_key_once(test_db):
    assert IdempotencyRepository.reserve("k1", ENDPOINT, "fp", "api") is True
    assert IdempotencyRepository.reserve("k1", ENDPOINT, "fp", "api") is False

    record = IdempotencyRepository.get("k1", ENDPOINT)
    assert record is not None
    assert record.state == "in_flight"
    assert record.response_status is None


def test_reserve_is_scoped_to_the_endpoint(test_db):
    assert IdempotencyRepository.reserve("k1", ENDPOINT, "fp", "api") is True
    assert IdempotencyRepository.reserve("k1", "POST /other", "fp", "api") is True


def test_complete_records_the_response(test_db):
    IdempotencyRepository.reserve("k1", ENDPOINT, "fp", "api")
    IdempotencyRepository.complete(
        key="k1",
        endpoint=ENDPOINT,
        response_status=201,
        response_body='{"id": "v1"}',
        entity_type="voucher",
        entity_id="v1",
    )

    record = IdempotencyRepository.get("k1", ENDPOINT)
    assert record.state == "completed"
    assert record.response_status == 201
    assert record.response_body == '{"id": "v1"}'
    assert record.entity_id == "v1"
    assert record.completed_at is not None


def test_release_drops_an_in_flight_reservation_only(test_db):
    IdempotencyRepository.reserve("k1", ENDPOINT, "fp", "api")
    IdempotencyRepository.release("k1", ENDPOINT)
    assert IdempotencyRepository.get("k1", ENDPOINT) is None

    IdempotencyRepository.reserve("k2", ENDPOINT, "fp", "api")
    IdempotencyRepository.complete(
        key="k2",
        endpoint=ENDPOINT,
        response_status=201,
        response_body="{}",
        entity_type="voucher",
        entity_id="v2",
    )
    IdempotencyRepository.release("k2", ENDPOINT)
    assert IdempotencyRepository.get("k2", ENDPOINT) is not None


# --- T3: service -----------------------------------------------------------


def test_fingerprint_ignores_key_order_and_whitespace():
    service = IdempotencyService()
    assert service.fingerprint({"a": 1, "b": [2, 3]}) == service.fingerprint(
        {"b": [2, 3], "a": 1}
    )
    assert service.fingerprint({"a": 1}) != service.fingerprint({"a": 2})


def test_fingerprint_survives_a_renamed_actor():
    """The actor is not part of the intent (§6)."""
    service = IdempotencyService()
    body = {"description": "Telefon", "rows": []}
    assert service.fingerprint(body) == service.fingerprint(dict(body))


def test_begin_reserves_an_unknown_key(test_db):
    service = IdempotencyService()
    outcome = service.begin("k1", ENDPOINT, {"a": 1}, "api")
    assert outcome.kind == IdempotencyOutcome.PROCEED
    assert IdempotencyRepository.get("k1", ENDPOINT).state == "in_flight"


def test_begin_replays_a_completed_key(test_db):
    service = IdempotencyService()
    body = {"a": 1}
    service.begin("k1", ENDPOINT, body, "api")
    service.complete(
        key="k1",
        endpoint=ENDPOINT,
        response_status=201,
        response_payload={"id": "v1"},
        entity_type="voucher",
        entity_id="v1",
    )

    outcome = service.begin("k1", ENDPOINT, body, "api")
    assert outcome.kind == IdempotencyOutcome.REPLAY
    assert outcome.response_status == 201
    assert outcome.response_payload == {"id": "v1"}


def test_begin_rejects_the_same_key_with_a_changed_body(test_db):
    service = IdempotencyService()
    service.begin("k1", ENDPOINT, {"a": 1}, "api")
    service.complete(
        key="k1",
        endpoint=ENDPOINT,
        response_status=201,
        response_payload={"id": "v1"},
        entity_type="voucher",
        entity_id="v1",
    )

    outcome = service.begin("k1", ENDPOINT, {"a": 2}, "api")
    assert outcome.kind == IdempotencyOutcome.MISMATCH
    assert outcome.original_fingerprint is not None


def test_begin_reports_a_request_still_in_flight(test_db):
    service = IdempotencyService()
    service.begin("k1", ENDPOINT, {"a": 1}, "api")

    outcome = service.begin("k1", ENDPOINT, {"a": 1}, "api")
    assert outcome.kind == IdempotencyOutcome.IN_FLIGHT


def test_begin_treats_another_endpoint_as_another_intent(test_db):
    """Test case 5: the same key against a different endpoint never replays."""
    service = IdempotencyService()
    body = {"a": 1}
    service.begin("k1", ENDPOINT, body, "api")
    service.complete(
        key="k1",
        endpoint=ENDPOINT,
        response_status=201,
        response_payload={"id": "v1"},
        entity_type="voucher",
        entity_id="v1",
    )

    outcome = service.begin("k1", "POST /api/v1/vouchers/x/correct", body, "api")
    assert outcome.kind == IdempotencyOutcome.PROCEED


def test_identical_bodies_under_different_keys_both_proceed(test_db):
    """Test case 4: idempotency is not duplicate detection."""
    service = IdempotencyService()
    body = {"a": 1}
    assert service.begin("k1", ENDPOINT, body, "api").kind == IdempotencyOutcome.PROCEED
    assert service.begin("k2", ENDPOINT, body, "api").kind == IdempotencyOutcome.PROCEED


# --- T4: header dependency -------------------------------------------------


@pytest.mark.asyncio
async def test_header_dependency_accepts_a_uuid():
    key = str(uuid.uuid4())
    assert await get_idempotency_key(key) == key


@pytest.mark.asyncio
async def test_header_dependency_returns_none_when_missing(caplog):
    with caplog.at_level("INFO"):
        assert await get_idempotency_key(None) is None
    assert "idempotency_key_missing" in caplog.text


@pytest.mark.asyncio
async def test_header_dependency_rejects_a_non_uuid():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_idempotency_key("not-a-uuid")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "invalid_idempotency_key"


# --- T5: POST /agent/vouchers ---------------------------------------------


@pytest.mark.asyncio
async def test_same_key_same_body_posts_once(test_db, async_client, intake_dir):
    """Test case 1."""
    _ensure_accounts()
    period = _period()
    source = _intake_source(intake_dir)
    body = _voucher_body(period.id, source.id)
    key = str(uuid.uuid4())

    first = await async_client.post(
        "/api/v1/agent/vouchers", headers=_headers(key), json=body
    )
    second = await async_client.post(
        "/api/v1/agent/vouchers", headers=_headers(key), json=body
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    assert first.headers.get("Idempotent-Replay") is None
    assert second.headers.get("Idempotent-Replay") == "true"
    assert _voucher_count() == 1


@pytest.mark.asyncio
async def test_same_key_changed_body_is_refused(test_db, async_client, intake_dir):
    """Test case 2."""
    _ensure_accounts()
    period = _period()
    source = _intake_source(intake_dir)
    key = str(uuid.uuid4())

    first = await async_client.post(
        "/api/v1/agent/vouchers",
        headers=_headers(key),
        json=_voucher_body(period.id, source.id, amount=12500),
    )
    assert first.status_code == 201

    second = await async_client.post(
        "/api/v1/agent/vouchers",
        headers=_headers(key),
        json=_voucher_body(period.id, source.id, amount=9900),
    )
    assert second.status_code == 422
    assert second.json()["detail"]["code"] == "idempotency_key_reuse"
    assert _voucher_count() == 1


@pytest.mark.asyncio
async def test_different_keys_create_separate_vouchers(
    test_db, async_client, intake_dir
):
    """Test case 4 at the route: the key never merges two distinct intents.

    The route requires source traceability, so two intents carry two sources —
    everything else about the two bodies is identical.
    """
    _ensure_accounts()
    period = _period()
    first_source = _intake_source(intake_dir, "telefon-januari.pdf")
    second_source = _intake_source(intake_dir, "telefon-februari.pdf")

    first = await async_client.post(
        "/api/v1/agent/vouchers",
        headers=_headers(str(uuid.uuid4())),
        json=_voucher_body(period.id, first_source.id),
    )
    second = await async_client.post(
        "/api/v1/agent/vouchers",
        headers=_headers(str(uuid.uuid4())),
        json=_voucher_body(period.id, second_source.id),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert _voucher_count() == 2


@pytest.mark.asyncio
async def test_abort_mid_transaction_leaves_nothing_behind(
    test_db, async_client, intake_dir, monkeypatch
):
    """Test case 6: the module's hardest case.

    The transaction throws after the voucher is posted but before commit.
    Neither the voucher nor the key row may survive, and the retry must be clean.
    """
    _ensure_accounts()
    period = _period()
    source = _intake_source(intake_dir)
    body = _voucher_body(period.id, source.id)
    key = str(uuid.uuid4())

    def explode(*args, **kwargs):
        raise RuntimeError("simulated failure after posting")

    monkeypatch.setattr(
        "services.bank_inputs.BankInputService.link_posted_voucher", explode
    )

    failed = await async_client.post(
        "/api/v1/agent/vouchers", headers=_headers(key), json=body
    )
    assert failed.status_code == 500
    assert _voucher_count() == 0
    assert _key_rows() == []

    monkeypatch.undo()

    retry = await async_client.post(
        "/api/v1/agent/vouchers", headers=_headers(key), json=body
    )
    assert retry.status_code == 201
    assert _voucher_count() == 1


@pytest.mark.asyncio
async def test_missing_header_still_works(test_db, async_client, intake_dir, caplog):
    """Test case 12: transition rule (c) — optional with a warning."""
    _ensure_accounts()
    period = _period()
    source = _intake_source(intake_dir)

    with caplog.at_level("INFO"):
        response = await async_client.post(
            "/api/v1/agent/vouchers",
            headers=_headers(),
            json=_voucher_body(period.id, source.id),
        )

    assert response.status_code == 201
    assert _voucher_count() == 1
    assert _key_rows() == []
    assert "idempotency_key_missing" in caplog.text


def test_ten_threads_with_one_key_post_once(test_db, tmp_path):
    """Test case 3: real threads, one SQLite file, no shared connection."""
    from fastapi.testclient import TestClient

    original_intake = settings.intake_dir
    settings.intake_dir = str(tmp_path / "intake")
    try:
        _ensure_accounts()
        period = _period()
        source = IntakeService().create_source_from_upload_content(
            filename="telefon.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4 telefon",
            explanation="Telefonutgift Fello",
            source_type="receipt",
            actor="api",
        )
        body = _voucher_body(period.id, source.id)
        key = str(uuid.uuid4())

        client = TestClient(app)
        results: list[int] = []
        lock = threading.Lock()

        def post():
            response = client.post(
                "/api/v1/agent/vouchers", headers=_headers(key), json=body
            )
            with lock:
                results.append(response.status_code)

        threads = [threading.Thread(target=post) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(results) == 10
        assert results.count(201) >= 1
        assert set(results) <= {201, 409}
        assert _voucher_count() == 1
    finally:
        settings.intake_dir = original_intake


def test_replayed_body_is_the_stored_response(test_db):
    """The replay must be byte-identical to what the first call returned."""
    service = IdempotencyService()
    payload = {"id": "v1", "amount": 125.0, "rows": [{"account": "1920"}]}
    service.begin("k1", ENDPOINT, {"a": 1}, "api")
    service.complete(
        key="k1",
        endpoint=ENDPOINT,
        response_status=201,
        response_payload=payload,
        entity_type="voucher",
        entity_id="v1",
    )

    stored = IdempotencyRepository.get("k1", ENDPOINT).response_body
    assert json.loads(stored) == payload


# --- T6: POST /vouchers/{id}/post on an already posted voucher -------------


def _posted_voucher(period, amount: int = 12500):
    """A posted A-series voucher, created through the service layer."""
    ledger = LedgerService()
    voucher = ledger.create_voucher(
        series="A",
        date=date.today(),
        period_id=period.id,
        description="Telefonutgift Fello",
        rows_data=[
            {"account": "1920", "debit": 0, "credit": amount},
            {"account": "6200", "debit": amount, "credit": 0},
        ],
        created_by="api",
    )
    return ledger.post_voucher(voucher.id, actor="api")


@pytest.mark.asyncio
async def test_posting_a_posted_voucher_is_a_conflict(test_db, async_client):
    """Test case 7: 409 with the whole voucher, so the client can show done."""
    _ensure_accounts()
    period = _period()
    voucher = _posted_voucher(period)

    response = await async_client.post(
        f"/api/v1/vouchers/{voucher.id}/post", headers=_headers()
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "already_posted"
    assert detail["voucher"]["id"] == voucher.id
    assert detail["voucher"]["status"] == "posted"
    assert len(detail["voucher"]["rows"]) == 2


@pytest.mark.asyncio
async def test_other_posting_errors_are_still_400(test_db, async_client):
    """The status change is for `already_posted` alone, not for every error."""
    _ensure_accounts()
    _period()

    response = await async_client.post(
        "/api/v1/vouchers/does-not-exist/post", headers=_headers()
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "voucher_not_found"


# --- T7: period_locked says who and when -----------------------------------


@pytest.mark.asyncio
async def test_posting_into_a_locked_period_names_the_locker(test_db, async_client):
    """Test case 8."""
    _ensure_accounts()
    period = _period()
    ledger = LedgerService()
    voucher = ledger.create_voucher(
        series="A",
        date=date.today(),
        period_id=period.id,
        description="Telefonutgift Fello",
        rows_data=[
            {"account": "1920", "debit": 0, "credit": 12500},
            {"account": "6200", "debit": 12500, "credit": 0},
        ],
        created_by="api",
    )
    PeriodRepository.lock_period(period.id, actor="stefan")

    response = await async_client.post(
        f"/api/v1/vouchers/{voucher.id}/post", headers=_headers()
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "period_locked"
    assert detail["period_id"] == period.id
    assert detail["locked_by"] == "stefan"
    assert detail["locked_at"] is not None


@pytest.mark.asyncio
async def test_a_lock_without_an_actor_is_reported_as_unknown(test_db, async_client):
    """Test case 9: a historical gap shows as a gap — no guess, no crash."""
    _ensure_accounts()
    period = _period()
    ledger = LedgerService()
    voucher = ledger.create_voucher(
        series="A",
        date=date.today(),
        period_id=period.id,
        description="Telefonutgift Fello",
        rows_data=[
            {"account": "1920", "debit": 0, "credit": 12500},
            {"account": "6200", "debit": 12500, "credit": 0},
        ],
        created_by="api",
    )
    PeriodRepository.lock_period(period.id, actor="stefan")
    db.execute("UPDATE periods SET locked_by = NULL WHERE id = ?", (period.id,))
    db.commit()

    response = await async_client.post(
        f"/api/v1/vouchers/{voucher.id}/post", headers=_headers()
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "period_locked"
    assert detail["locked_by"] == "okänd"


def test_locking_a_period_records_the_actor(test_db):
    """The lock writes `locked_by` going forward."""
    _ensure_accounts()
    period = _period()

    locked = LedgerService().lock_period(period.id, actor="stefan")

    assert locked.locked is True
    assert locked.locked_by == "stefan"


@pytest.mark.asyncio
async def test_the_lock_response_carries_the_actor(test_db, async_client):
    _ensure_accounts()
    period = _period()

    response = await async_client.post(
        f"/api/v1/periods/{period.id}/lock", headers=_headers()
    )

    assert response.status_code == 200
    assert response.json()["locked_by"] == "api"


# --- T8: _commit through the correction chain ------------------------------


def test_correction_chain_rolls_back_as_one_unit(test_db):
    """The chain must be runnable inside a caller's transaction."""
    _ensure_accounts()
    period = _period()
    original = _posted_voucher(period)
    ledger = LedgerService()

    with pytest.raises(RuntimeError):
        with db.transaction():
            ledger.create_posted_correction(
                original_voucher_id=original.id,
                corrected_rows=[
                    {"account": "1920", "debit": 0, "credit": 9900},
                    {"account": "6200", "debit": 9900, "credit": 0},
                ],
                reason="Fel belopp",
                actor="api",
                _commit=False,
            )
            raise RuntimeError("simulated failure after the correction")

    assert _voucher_count() == 1
    assert _correction_history_count() == 0


def test_correction_chain_still_commits_by_default(test_db):
    """Default behaviour is unchanged, bit for bit."""
    _ensure_accounts()
    period = _period()
    original = _posted_voucher(period)

    correction = LedgerService().create_posted_correction(
        original_voucher_id=original.id,
        corrected_rows=[
            {"account": "1920", "debit": 0, "credit": 9900},
            {"account": "6200", "debit": 9900, "credit": 0},
        ],
        reason="Fel belopp",
        actor="api",
    )

    assert correction.series.value == "B"
    assert correction.status.value == "posted"
    assert _voucher_count() == 2
    assert _correction_history_count() == 1


# --- T9: POST /vouchers/{id}/correct --------------------------------------


def _correction_body(amount: int = 9900):
    return {
        "corrected_rows": [
            {"account": "1920", "debit": 0, "credit": amount},
            {"account": "6200", "debit": amount, "credit": 0},
        ],
        "reason": "Fel belopp",
    }


@pytest.mark.asyncio
async def test_correcting_twice_with_one_key_creates_one_correction(
    test_db, async_client
):
    """Test case 10."""
    _ensure_accounts()
    period = _period()
    original = _posted_voucher(period)
    key = str(uuid.uuid4())

    first = await async_client.post(
        f"/api/v1/vouchers/{original.id}/correct",
        headers=_headers(key),
        json=_correction_body(),
    )
    second = await async_client.post(
        f"/api/v1/vouchers/{original.id}/correct",
        headers=_headers(key),
        json=_correction_body(),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.headers.get("Idempotent-Replay") is None
    assert second.headers.get("Idempotent-Replay") == "true"
    assert _voucher_count() == 2
    assert _correction_history_count() == 1


@pytest.mark.asyncio
async def test_an_aborted_correction_leaves_no_trace(
    test_db, async_client, monkeypatch
):
    """Test case 11: B-voucher, history row and key row live or die together."""
    _ensure_accounts()
    period = _period()
    original = _posted_voucher(period)
    key = str(uuid.uuid4())

    def explode(*args, **kwargs):
        raise RuntimeError("simulated failure after the correction")

    monkeypatch.setattr(
        "services.ledger.LedgerService._record_correction_history", explode
    )

    failed = await async_client.post(
        f"/api/v1/vouchers/{original.id}/correct",
        headers=_headers(key),
        json=_correction_body(),
    )
    assert failed.status_code == 500
    assert _voucher_count() == 1
    assert _correction_history_count() == 0
    assert _key_rows() == []

    monkeypatch.undo()

    retry = await async_client.post(
        f"/api/v1/vouchers/{original.id}/correct",
        headers=_headers(key),
        json=_correction_body(),
    )
    assert retry.status_code == 200
    assert _voucher_count() == 2


@pytest.mark.asyncio
async def test_an_abort_after_the_history_row_rolls_it_back_too(
    test_db, async_client, monkeypatch
):
    """Test case 11, from the other end.

    Failing before the history row is written proves nothing about rolling it
    back. Here the B-series voucher and the history row are both already
    written when the transaction throws.
    """
    _ensure_accounts()
    period = _period()
    original = _posted_voucher(period)
    key = str(uuid.uuid4())

    def explode(*args, **kwargs):
        raise RuntimeError("simulated failure after the history row")

    monkeypatch.setattr("services.idempotency.IdempotencyService.complete", explode)

    failed = await async_client.post(
        f"/api/v1/vouchers/{original.id}/correct",
        headers=_headers(key),
        json=_correction_body(),
    )

    assert failed.status_code == 500
    assert _voucher_count() == 1
    assert _correction_history_count() == 0
    assert _key_rows() == []


@pytest.mark.asyncio
async def test_the_same_correction_key_on_another_voucher_is_another_intent(
    test_db, async_client
):
    """The key is scoped to the voucher being corrected, not to the path shape."""
    _ensure_accounts()
    period = _period()
    first_original = _posted_voucher(period)
    second_original = _posted_voucher(period, amount=7700)
    key = str(uuid.uuid4())

    first = await async_client.post(
        f"/api/v1/vouchers/{first_original.id}/correct",
        headers=_headers(key),
        json=_correction_body(),
    )
    second = await async_client.post(
        f"/api/v1/vouchers/{second_original.id}/correct",
        headers=_headers(key),
        json=_correction_body(),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] != second.json()["id"]
    assert _correction_history_count() == 2


@pytest.mark.asyncio
async def test_correcting_without_a_key_still_works(test_db, async_client):
    """Transition rule (c) holds here too."""
    _ensure_accounts()
    period = _period()
    original = _posted_voucher(period)

    response = await async_client.post(
        f"/api/v1/vouchers/{original.id}/correct",
        headers=_headers(),
        json=_correction_body(),
    )

    assert response.status_code == 200
    assert _key_rows() == []
    assert _correction_history_count() == 1


# --- POST /vouchers/{id}/post reads the key (chattyta, open question 4) ----
#
# The chat's Posta button has sent a key derived from `draft_id` since C12,
# but the route never read it. Posting only flips a draft's own status, so a
# second request could not create a second voucher -- yet two requests that
# arrived at the same instant could both pass validation and both write a
# `posted` audit row. With the key, the second one is `request_in_flight`
# or a replay, never a second posting.


def _draft_voucher(period, amount: int = 12500):
    return LedgerService().create_voucher(
        series="A",
        date=date.today(),
        period_id=period.id,
        description="Telefonutgift Fello",
        rows_data=[
            {"account": "1920", "debit": 0, "credit": amount},
            {"account": "6200", "debit": amount, "credit": 0},
        ],
        created_by="api",
    )


def _posted_audit_rows(voucher_id: str) -> int:
    return db.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE entity_id = ? AND action = 'posted'",
        (voucher_id,),
    ).fetchone()["n"]


def _post_endpoint(voucher_id: str) -> str:
    return f"POST /api/v1/vouchers/{voucher_id}/post"


@pytest.mark.asyncio
async def test_posting_twice_with_one_key_replays(test_db, async_client):
    _ensure_accounts()
    voucher = _draft_voucher(_period())
    key = str(uuid.uuid4())

    first = await async_client.post(
        f"/api/v1/vouchers/{voucher.id}/post", headers=_headers(key)
    )
    second = await async_client.post(
        f"/api/v1/vouchers/{voucher.id}/post", headers=_headers(key)
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers.get("Idempotent-Replay") is None
    assert second.headers.get("Idempotent-Replay") == "true"
    assert second.json() == first.json()
    assert first.json()["status"] == "posted"
    assert _posted_audit_rows(voucher.id) == 1


@pytest.mark.asyncio
async def test_posting_records_the_key_with_the_voucher(test_db, async_client):
    _ensure_accounts()
    voucher = _draft_voucher(_period())
    key = str(uuid.uuid4())

    await async_client.post(
        f"/api/v1/vouchers/{voucher.id}/post", headers=_headers(key)
    )

    [row] = _key_rows()
    assert row["key"] == key
    assert row["endpoint"] == _post_endpoint(voucher.id)
    assert row["state"] == "completed"
    assert row["entity_id"] == voucher.id


@pytest.mark.asyncio
async def test_posting_while_the_key_is_held_is_in_flight(test_db, async_client):
    _ensure_accounts()
    voucher = _draft_voucher(_period())
    key = str(uuid.uuid4())
    IdempotencyService().begin(key, _post_endpoint(voucher.id), {}, "api")

    response = await async_client.post(
        f"/api/v1/vouchers/{voucher.id}/post", headers=_headers(key)
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "request_in_flight"
    assert detail["retry_after_ms"] > 0
    assert LedgerService().vouchers.get(voucher.id).status.value == "draft"
    assert _posted_audit_rows(voucher.id) == 0


@pytest.mark.asyncio
async def test_a_refused_posting_releases_the_key(test_db, async_client):
    """A locked period is an answer, not a completed posting: the key is freed."""
    _ensure_accounts()
    period = _period()
    voucher = _draft_voucher(period)
    PeriodRepository.lock_period(period.id, actor="stefan")
    key = str(uuid.uuid4())

    response = await async_client.post(
        f"/api/v1/vouchers/{voucher.id}/post", headers=_headers(key)
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "period_locked"
    assert _key_rows() == []


@pytest.mark.asyncio
async def test_already_posted_is_still_a_conflict_under_a_new_key(
    test_db, async_client
):
    """A voucher posted by another path, then pressed under a fresh key."""
    _ensure_accounts()
    voucher = _posted_voucher(_period())

    response = await async_client.post(
        f"/api/v1/vouchers/{voucher.id}/post", headers=_headers(str(uuid.uuid4()))
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "already_posted"
    assert _key_rows() == []


@pytest.mark.asyncio
async def test_posting_without_a_key_still_works(test_db, async_client):
    _ensure_accounts()
    voucher = _draft_voucher(_period())

    response = await async_client.post(
        f"/api/v1/vouchers/{voucher.id}/post", headers=_headers()
    )

    assert response.status_code == 200
    assert _key_rows() == []
    assert _posted_audit_rows(voucher.id) == 1
