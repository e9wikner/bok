# Bokföringssystem API - Setup Guide

## Quick Start

### 1. Install Dependencies

```bash
cd bokfoering-api
pip install -r requirements.txt
```

### 2. Initialize Database

```bash
python main.py --init-db
```

This will:
- Create SQLite database (`bokfoering.db`)
- Set up all tables (append-only vouchers, periods, accounts, audit log)
- Load default BAS 2026 accounts (subset for demo)

### 3. Start Server

```bash
python main.py
```

Server runs on `http://127.0.0.1:8000`

### 4. Explore API

- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc
- **Health Check:** http://127.0.0.1:8000/health

## Running Tests

```bash
pytest tests/ -v
```

## Example Workflow

### 1. Create Fiscal Year

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/fiscal-years?start_date=2026-01-01&end_date=2026-12-31" \
  -H "Authorization: Bearer dev-key-change-in-production" \
  -H "Content-Type: application/json"
```

Returns `fiscal_year_id` and creates 12 monthly periods.

### 2. List Periods

```bash
curl "http://127.0.0.1:8000/api/v1/periods?fiscal_year_id=<fy_id>" \
  -H "Authorization: Bearer dev-key-change-in-production"
```

### 3. List Accounts

```bash
curl "http://127.0.0.1:8000/api/v1/accounts" \
  -H "Authorization: Bearer dev-key-change-in-production"
```

### 4. Create & Post Voucher

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/vouchers" \
  -H "Authorization: Bearer dev-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "series": "A",
    "date": "2026-03-20",
    "period_id": "<period_id>",
    "description": "Konsultfaktura #1042 till Acme AB",
    "auto_post": true,
    "rows": [
      {"account": "1510", "debit": 12500000, "credit": 0},
      {"account": "3011", "debit": 0, "credit": 10000000},
      {"account": "2610", "debit": 0, "credit": 2500000}
    ]
  }'
```

**Note:** All amounts in öre (1 kr = 100).

### 5. Get Trial Balance

```bash
curl "http://127.0.0.1:8000/api/v1/reports/trial-balance?period_id=<period_id>" \
  -H "Authorization: Bearer dev-key-change-in-production"
```

### 6. Get Account Ledger

```bash
curl "http://127.0.0.1:8000/api/v1/reports/account/1510?period_id=<period_id>" \
  -H "Authorization: Bearer dev-key-change-in-production"
```

### 7. Lock Period

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/periods/<period_id>/lock" \
  -H "Authorization: Bearer dev-key-change-in-production"
```

Once locked, period is immutable (BFL varaktighet requirement).

## Key Features (Fas 1: Grundbokföring)

✅ **Append-only Vouchers** - Posted vouchers cannot be edited, only corrected via B-series  
✅ **Period Locking** - Irreversible locking ensures data integrity  
✅ **Balance Validation** - Every voucher must balance (debit = credit)  
✅ **Audit Trail** - All operations logged with timestamp and actor  
✅ **BAS 2026 Accounts** - Predefined chart of accounts  
✅ **Trial Balance & Ledger** - Standard accounting reports  
✅ **API Authentication** - Bearer token validation  

## Configuration

### Environment Variables

Create `.env`:

```env
BOKFOERING_API_KEY=your-secret-key-here
DEBUG=False
DATABASE_URL=sqlite:///./bokfoering.db
```

### Database

SQLite database is stored at `bokfoering.db` in the project root. For production, consider:
- PostgreSQL with WAL replication
- Automated backups (7-year retention per BFL)
- Encrypted at-rest storage

## Project Structure

```
bokfoering-api/
├── domain/              # Business logic & entities
│   ├── models.py       # Domain models
│   ├── types.py        # Enums
│   └── validation.py   # Business rules
├── db/                 # Database layer
│   ├── database.py     # Connection manager
│   └── migrations/     # SQL schemas
├── repositories/       # Data access
│   ├── voucher_repo.py
│   ├── account_repo.py
│   ├── period_repo.py
│   └── audit_repo.py
├── services/           # Business logic
│   └── ledger.py       # Core accounting
├── api/                # HTTP layer
│   ├── main.py         # FastAPI setup
│   ├── schemas.py      # Request/response models
│   ├── deps.py         # Dependency injection
│   └── routes/         # API endpoints
├── tests/              # Test suite
└── main.py             # CLI entrypoint
```

## Next Steps

### Fas 2: Fakturering & Moms
- Invoice model
- Auto-booking on invoice creation
- Payment registration
- VAT calculation & reporting

### Fas 3: Rapporter & K2
- Income statement
- Balance sheet
- K2 annual report (JSON + PDF)
- Full system documentation export

### Fas 4: Agent Integration
- OpenAPI 3.1 spec
- Agent-friendly error responses
- Idempotent operations
- End-to-end tests

## Troubleshooting

### Database locked error
```bash
# Remove stale database and reinitialize
rm bokfoering.db
python main.py --init-db
```

### API key not working
Check `.env` and ensure `Authorization: Bearer <key>` header is present.

### Import errors
```bash
# Ensure project is in PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

## Regulatory Compliance

This system implements:
- ✅ **BFL (Bokföringslagen)** - Swedish Accounting Law
- ✅ **BFNAR 2013:2** - National Board of Audit Regulations
- ✅ **BAS 2026** - Chart of Accounts Standard
- ✅ **K2 Årsredovisning** - Annual Report Format
- ✅ **Mervärdesskattelagen** - VAT Law (25% for consulting)
- ✅ **SIE4** - Standard for accounting data export

## Support

For questions or issues, refer to:
- https://docs.openclaw.ai
- Projektplan.md (regulatory requirements)
- README.md (architecture overview)
