# Testing Patterns

**Analysis Date:** 2026-05-14

## Test Framework

**Runner:**
- `pytest` 7.4.3
- Config: no dedicated `pytest.ini`/`pyproject.toml` test config detected; shared fixtures are in `tests/conftest.py`

**Assertion Library:**
- Native `assert` statements with `pytest` helpers (`pytest.raises`) in `tests/*.py`

**Run Commands:**
```bash
pytest                    # Run all tests
pytest -k <pattern>       # Run subset by name/expression
pytest -q                 # Less verbose output
```

## Test File Organization

**Location:**
- Backend tests are centralized in top-level `tests/` and target API, services, and integration flows.

**Naming:**
- File naming follows `test_<feature>.py` (`tests/test_api.py`, `tests/test_sie4_integration.py`, `tests/test_payroll.py`).
- Test function naming follows `test_<behavior>()`.

**Structure:**
```text
tests/
  conftest.py
  test_api.py
  test_ledger.py
  test_invoices.py
  test_sie4_integration.py
  ...
```

## Test Structure

**Suite Organization:**
```python
@pytest.fixture
def client(test_db):
    from api.main import app
    return TestClient(app)

def test_create_voucher(client, auth_headers, period_id):
    resp = client.post("/api/v1/vouchers", headers=auth_headers, json={...})
    assert resp.status_code == 201
```

**Patterns:**
- Setup pattern: reusable fixtures in `tests/conftest.py` create isolated temporary SQLite DB and seed base data.
- Teardown pattern: fixture finalizers disconnect DB and remove temp files (`tests/conftest.py`).
- Assertion pattern: response-code checks plus business-result assertions on payload/domain state (`tests/test_api.py`, `tests/test_ledger.py`).

## Mocking

**Framework:** `unittest.mock` (`patch`, `Mock`, `MagicMock`) integrated with `pytest`.

**Patterns:**
```python
with patch("services.pdf_export.PDFExportService.export_invoice") as mock_export:
    mock_export.return_value = b"fake pdf content"
    response = client.get("/api/v1/export/pdf/invoice/test-123")
    assert response.status_code in [200, 404]
```

**What to Mock:**
- External/slow boundaries (PDF generation, DB accessor indirection, service integration points) in unit-style tests (`tests/test_pdf_export.py`, `tests/test_sru_export.py`).

**What NOT to Mock:**
- Core accounting rules and repository interactions in integration-style flows using real SQLite state (`tests/test_ledger.py`, `tests/test_sie4_integration.py`, `tests/test_vat_report.py`).

## Fixtures and Factories

**Test Data:**
```python
@pytest.fixture(scope="function")
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    db.db_path = path
    db.init_db()
    yield db
    db.disconnect()
    os.remove(path)
```

**Location:**
- Shared fixtures live in `tests/conftest.py`.
- Local fixtures are defined per test module when setup differs (`tests/test_api.py`, `tests/test_invoices.py`, `tests/test_sie4_integration.py`).

## Coverage

**Requirements:** None enforced in-repo (no coverage threshold config detected).

**View Coverage:**
```bash
pytest --cov=. --cov-report=term-missing
```

## Test Types

**Unit Tests:**
- Pure/business-logic focus with mocks and targeted assertions (`tests/test_sru_export.py`, `tests/test_pdf_export.py`).

**Integration Tests:**
- End-to-end backend slices through DB + repositories + services + API client (`tests/test_api.py`, `tests/test_sie4_integration.py`, `tests/test_vat_report.py`).

**E2E Tests:**
- Frontend/browser E2E tests are not detected in repo test files; `playwright` is present as a frontend dependency in `frontend-v3/package.json`.

## Common Patterns

**Async Testing:**
```python
# API handlers are async, but tests use synchronous FastAPI TestClient wrappers.
client = TestClient(app)
resp = client.get("/health")
assert resp.status_code == 200
```

**Error Testing:**
```python
with pytest.raises(ValidationError) as exc_info:
    ledger_service.create_voucher(...unbalanced rows...)
assert exc_info.value.code == "balance_error"
```

---

*Testing analysis: 2026-05-14*
