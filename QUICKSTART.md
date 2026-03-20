# Quick Start Guide

Get up and running in 2 minutes!

## 🚀 Fastest Way: Docker

### Prerequisites
- Docker & Docker Compose installed

### Start

```bash
docker-compose up --build
```

This will:
1. Build the image
2. Initialize SQLite database
3. Load BAS 2026 chart of accounts
4. Create TestCorp AB demo company
5. Generate sample invoices with payments
6. Start API on http://localhost:8000

### Explore

```bash
# Swagger interactive docs
open http://localhost:8000/docs

# ReDoc
open http://localhost:8000/redoc

# Health check
curl http://localhost:8000/health
```

---

## 💻 Local Development

### Prerequisites
- Python 3.11+
- pip/venv

### Setup

```bash
# Clone repo
git clone git@github.com:e9wikner/bok.git
cd bok

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize database with test data
python main.py --init-db --seed

# Start server
python main.py --host 127.0.0.1 --port 8000
```

### Endpoints

Open browser to:
- API Docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

---

## 📊 Test the System

All examples use the test company **TestCorp AB** with pre-loaded data.

### 1. List Accounts

```bash
curl -H "Authorization: Bearer dev-key-change-in-production" \
  http://localhost:8000/api/v1/accounts
```

### 2. List Periods

First, get a fiscal year ID from the database. Then:

```bash
curl -H "Authorization: Bearer dev-key-change-in-production" \
  "http://localhost:8000/api/v1/periods?fiscal_year_id=<fy_id>"
```

### 3. View Trial Balance

```bash
curl -H "Authorization: Bearer dev-key-change-in-production" \
  "http://localhost:8000/api/v1/reports/trial-balance?period_id=<period_id>"
```

**Expected output:** Trial balance for March 2026 with:
- Debit: 12,653,000 öre (126,530 kr)
- Credit: 12,653,000 öre (126,530 kr)
- ✅ Balanced!

### 4. Get Account Ledger

```bash
curl -H "Authorization: Bearer dev-key-change-in-production" \
  "http://localhost:8000/api/v1/reports/account/1510?period_id=<period_id>"
```

Shows all customer receivables transactions.

### 5. Create Your Own Voucher

```bash
curl -X POST http://localhost:8000/api/v1/vouchers \
  -H "Authorization: Bearer dev-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "series": "A",
    "date": "2026-03-20",
    "period_id": "<period_id>",
    "description": "Test voucher",
    "auto_post": true,
    "rows": [
      {"account": "1010", "debit": 100000, "credit": 0},
      {"account": "4020", "debit": 0, "credit": 100000}
    ]
  }'
```

### 6. Create an Invoice

```bash
curl -X POST http://localhost:8000/api/v1/invoices \
  -H "Authorization: Bearer dev-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Test Customer AB",
    "invoice_date": "2026-02-15",
    "due_date": "2026-03-15",
    "rows": [
      {
        "description": "Service",
        "quantity": 10,
        "unit_price": 100000,
        "vat_code": "MP1"
      }
    ]
  }'
```

---

## 🧪 Run Tests

```bash
source venv/bin/activate
pytest tests/ -v
```

---

## 📚 Learn More

- **API Reference:** [API.md](API.md)
- **System Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **Docker Setup:** [DOCKER.md](DOCKER.md)
- **Full Setup:** [SETUP.md](SETUP.md)
- **Change Log:** [CHANGELOG.md](CHANGELOG.md)

---

## 🔐 Security

⚠️ **Important:** Change the API key in production!

### Environment Variables

Create `.env`:

```env
BOKFOERING_API_KEY=your-secret-key-here
DEBUG=False
DATABASE_URL=sqlite:///./bokfoering.db
```

Then restart the server.

---

## 🐛 Troubleshooting

### Port 8000 Already in Use

```bash
python main.py --port 9000
```

### Database Issues

```bash
# Delete and reinitialize
rm bokfoering.db
python main.py --init-db --seed
```

### Python Version Mismatch

Ensure Python 3.11+:
```bash
python3 --version  # Should be 3.11 or higher
```

### Import Errors

```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest tests/
```

---

## 💡 Next Steps

1. **Read API.md** for full endpoint reference
2. **Explore ARCHITECTURE.md** to understand design
3. **Try example workflows** in QUICKSTART.md
4. **Check DOCKER.md** for container deployments
5. **Look at seed_test_data.py** to see how to create test data

---

## 🎯 Common Workflows

### Workflow 1: Create and Post a Voucher

```
1. POST /api/v1/vouchers          (create draft)
2. POST /api/v1/vouchers/{id}/post (post/immutable)
3. GET /api/v1/reports/trial-balance (verify balance)
```

### Workflow 2: Invoice → Payment → Ledger

```
1. POST /api/v1/invoices           (create draft)
2. POST /api/v1/invoices/{id}/send (send to customer)
3. POST /api/v1/invoices/{id}/book (auto-voucher)
4. POST /api/v1/invoices/{id}/payment (register payment)
5. GET /api/v1/reports/account/1510 (see receivables)
```

### Workflow 3: Correct a Posted Voucher

```
1. POST /api/v1/vouchers/{id}/correct (create B-series)
2. Add correction rows
3. POST /api/v1/vouchers/{correction_id}/post (post correction)
4. GET /api/v1/reports/audit/voucher/{original_id} (see history)
```

---

## 🚢 Deploy to Production

For production:
1. Use PostgreSQL instead of SQLite
2. Set strong API key
3. Enable HTTPS/TLS
4. Set up automated backups
5. Use environment-specific config
6. Enable logging & monitoring

See ARCHITECTURE.md for details.

---

## ❓ Questions?

Check the docs:
- **API Endpoints?** → [API.md](API.md)
- **How does it work?** → [ARCHITECTURE.md](ARCHITECTURE.md)
- **Docker issues?** → [DOCKER.md](DOCKER.md)
- **Setup help?** → [SETUP.md](SETUP.md)

Happy bookkeeping! 📊
