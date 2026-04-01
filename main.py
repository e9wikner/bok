"""Application entrypoint."""

import sys
import argparse
import uvicorn
from db.database import db
from repositories.account_repo import AccountRepository
from config import settings


def init_db():
    """Initialize database and load BAS 2026 default accounts."""
    print(f"🔧 Initializing database ({settings.database_url})...")
    db.init_db()

    print("📊 Loading BAS 2026 Chart of Accounts...")
    _load_default_accounts()

    print("✅ Database initialization complete!")


def _load_default_accounts():
    """Load BAS 2026 default account chart."""
    # BAS 2026 Chart of Accounts (simplified subset)
    default_accounts = [
        # Assets (1000-1999)
        ("1000", "Kassa", "asset"),
        ("1010", "PlusGiro", "asset"),
        ("1200", "Kundfordringar", "asset"),
        ("1510", "Kundfordringar konsult", "asset"),
        ("1710", "Inventarier", "asset"),

        # Liabilities (2000-2799)
        ("2000", "Leverantörskulder", "liability"),
        ("2610", "Utgående moms 25%", "vat_out"),
        ("2620", "Utgående moms 12%", "vat_out"),
        ("2630", "Utgående moms 6%", "vat_out"),
        ("2640", "Ingående moms", "vat_in"),
        ("2740", "Privat uttag", "liability"),

        # Equity (2900-2999)
        ("2900", "Aktiekapital", "equity"),
        ("2950", "Balanserat resultat", "equity"),

        # Revenue (3000-3999)
        ("3010", "Försäljning tjänster 25%", "revenue"),
        ("3011", "Försäljning tjänster 25%", "revenue"),
        ("3020", "Försäljning tjänster 12%", "revenue"),
        ("3030", "Försäljning tjänster 6%", "revenue"),

        # Expenses (4000-8999)
        ("4010", "Personalkostnader", "expense"),
        ("4020", "Hyra kontorslokal", "expense"),
        ("4030", "Tele och Internet", "expense"),
        ("4040", "Resor", "expense"),
        ("5010", "Förbrukningsmaterial", "expense"),
        ("5020", "Telefon och post", "expense"),
        ("6000", "Övriga driftskostnader", "expense"),
        ("8000", "Avskrivning möbler", "expense"),
    ]

    for code, name, account_type in default_accounts:
        if not AccountRepository.exists(code):
            AccountRepository.create(
                code=code,
                name=name,
                account_type=account_type
            )
            print(f"  ✓ {code} - {name}")


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run FastAPI server."""
    print(f"🚀 Starting server on {host}:{port}...")
    # Disable auto-reload in Docker (causes Pydantic recursion errors)
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=False,  # Disable to avoid Pydantic schema generation recursion
        log_level="info"
    )


def main():
    """Main entrypoint."""
    parser = argparse.ArgumentParser(description="Bokföringssystem API")
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Initialize database"
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Seed test data (requires initialized database)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000)"
    )

    args = parser.parse_args()

    if args.init_db:
        init_db()
        if args.seed:
            print("\n🌱 Seeding test data...")
            # Import and run seed script
            from scripts.seed_test_data import seed_test_company
            seed_test_company()
        sys.exit(0)

    # Run server
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
