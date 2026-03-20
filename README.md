# Bokföringssystem API

Egenbyggt bokföringssystem med REST API för svenska aktiebolag. Uppfyller alla krav enligt Bokföringslagen (BFL) och BFNAR 2013:2.

**Status:** 
- ✅ **Fas 1** – Grundbokföring (Complete)
- 🚀 **Fas 2** – Fakturering & Moms (In Progress)
- 📋 **Fas 3** – Rapporter & K2 (Planned)
- 🔌 **Fas 4** – Agent Integration (Planned)

## Stack

- **Language:** Python 3.10+
- **Framework:** FastAPI
- **Database:** SQLite + migrations
- **Other:** Pydantic, SQLAlchemy, Alembic

## Project Structure

```
bokfoering-api/
├── db/
│   ├── migrations/          # SQL migration files
│   ├── schema.py            # SQLAlchemy models
│   └── init.py
├── domain/
│   ├── models.py            # Domain models (Voucher, Account, etc)
│   ├── validation.py        # Business rules
│   └── types.py             # Enums and types
├── services/
│   ├── ledger.py            # Core booking logic
│   ├── account.py           # Account management
│   └── period.py            # Period & fiscal year management
├── api/
│   ├── routes/
│   │   ├── vouchers.py
│   │   ├── accounts.py
│   │   ├── periods.py
│   │   └── reports.py
│   ├── schemas.py           # Pydantic request/response models
│   ├── deps.py              # Dependency injection
│   └── main.py              # FastAPI app setup
├── repositories/
│   ├── voucher_repo.py
│   ├── account_repo.py
│   ├── audit_repo.py
│   └── base.py
├── config.py                # Configuration
├── main.py                  # Application entrypoint
├── requirements.txt
└── tests/
    ├── test_ledger.py
    ├── test_api.py
    └── conftest.py
```

## Getting Started

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
python main.py --init-db

# Run server
uvicorn api.main:app --reload

# Run tests
pytest
```

## API Documentation

Once running, visit: `http://localhost:8000/docs`

## Regulatory Compliance

- ✅ Append-only voucher storage (varaktighet)
- ✅ Period locking (irreversible)
- ✅ BAS 2026 chart of accounts
- ✅ Audit trail logging
- ✅ Balance validation
- ✅ SIE4 export (Fas 2+)
