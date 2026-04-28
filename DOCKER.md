# Docker Setup & Usage

## Quick Start with Docker Compose

### 1. Prerequisites
- Docker Desktop (or Docker + Docker Compose)
- No Python installation needed!

### 2. Start the System

```bash
docker-compose up --build
```

This will:
- Build the Docker image
- Initialize the database
- Seed test company data (TestCorp AB)
- Start the API server on port 8000

### 3. Access the API

Once running:

```bash
# Health check
curl http://localhost:8000/health

# Swagger UI (interactive documentation)
open http://localhost:8000/docs

# ReDoc
open http://localhost:8000/redoc
```

### 4. Stop the System

```bash
docker-compose down
```

To also remove the database:
```bash
docker-compose down -v
```

## What's Pre-loaded?

When the container starts, it automatically:

✅ **Creates fiscal year 2026** (Jan 1 - Dec 31)
✅ **Creates 3 months of periods** (January, February, March)
✅ **Posts 4 sample vouchers:**
   - Invoice 1: 150,000 kr consulting services
   - Office rent: 500 kr
   - Invoice 2: 200,000 kr consulting services
   - Travel expenses: 3,000 kr
✅ **Locks March period** (immutable - demonstrates varaktighet)
✅ **Reports available** (income statement, balance sheet, account ledger)

## Example API Calls

### Get Account Ledger (Customer Receivables)

```bash
curl -H "Authorization: Bearer dev-key-change-in-production" \
  "http://localhost:8000/api/v1/reports/account/1510?period_id=<period_id>"
```

Response shows all transactions for account 1510 (Kundfordringar):
- Invoice 1: +150,000 kr
- Invoice 2: +200,000 kr
- Running balance: 350,000 kr

### Get Audit History (Behandlingshistorik)

```bash
# Get all changes to a voucher
curl -H "Authorization: Bearer dev-key-change-in-production" \
  "http://localhost:8000/api/v1/reports/audit/voucher/<voucher_id>"

# Shows: created, posted, actor, timestamp, payload
```

## Database

- **Location:** `./bokfoering.db` (mounted volume)
- **Type:** SQLite
- **Persistence:** Yes - survives container restarts
- **Backup:** Copy `bokfoering.db` to safe location

To reset:
```bash
rm bokfoering.db
docker-compose up --build
```

## Environment Variables

Configure in `docker-compose.yml`:

```yaml
environment:
  - DEBUG=False
  - BOKFOERING_API_KEY=dev-key-change-in-production  # Change in production!
  - DATABASE_URL=sqlite:///./bokfoering.db
```

## Logs

View logs:
```bash
docker-compose logs -f bokfoering-api
```

View seed output:
```bash
docker-compose logs bokfoering-api | grep "Seeding\|📊\|✅"
```

## Development Mode

To modify code and see changes:

```bash
# Rebuild and restart
docker-compose down
docker-compose up --build

# Or just restart the service
docker-compose restart bokfoering-api
```

To shell into the container:
```bash
docker exec -it bokfoering-api /bin/bash
```

## Production Considerations

For production deployment:
1. Use PostgreSQL instead of SQLite
2. Change `BOKFOERING_API_KEY` to a strong value
3. Set `DEBUG=False`
4. Add SSL/TLS (reverse proxy like Nginx)
5. Set up automated backups (7-year retention per BFL)
6. Use health checks in your orchestration

## Troubleshooting

### Port 8000 already in use
```bash
# Use a different port
docker-compose -f docker-compose.yml up
# Then modify docker-compose.yml ports: "9000:8000"
```

### Database locked error
```bash
# Restart container
docker-compose restart bokfoering-api
```

### Permission denied errors
```bash
# Check Docker permissions
sudo usermod -aG docker $USER
newgrp docker
```

## Next Steps

- Modify seed data in `scripts/seed_test_data.py`
- Add more test companies
- Implement Fas 2 (Fakturering & Moms)
- Set up CI/CD with GitHub Actions

Enjoy! 🚀
