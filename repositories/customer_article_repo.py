"""Repositories for customers and articles."""

from datetime import datetime
from typing import List, Optional
import uuid

from db.database import db
from domain.invoice_draft_models import Article, Customer


class CustomerRepository:
    @staticmethod
    def create(
        name: str,
        org_number: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
        payment_terms_days: int = 30,
        active: bool = True,
    ) -> Customer:
        customer_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT INTO customers
                (id, name, org_number, email, address, payment_terms_days, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_id,
                name,
                org_number,
                email,
                address,
                payment_terms_days,
                int(active),
                now,
                now,
            ),
        )
        db.commit()
        return Customer(
            id=customer_id,
            name=name,
            org_number=org_number,
            email=email,
            address=address,
            payment_terms_days=payment_terms_days,
            active=active,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def get(customer_id: str) -> Optional[Customer]:
        row = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        return CustomerRepository._row_to_customer(row) if row else None

    @staticmethod
    def find_by_org_number(org_number: str) -> Optional[Customer]:
        row = db.execute(
            "SELECT * FROM customers WHERE org_number = ? LIMIT 1", (org_number,)
        ).fetchone()
        return CustomerRepository._row_to_customer(row) if row else None

    @staticmethod
    def list_all(active_only: bool = True, search: Optional[str] = None) -> List[Customer]:
        clauses = []
        params = []
        if active_only:
            clauses.append("active = 1")
        if search:
            clauses.append("(name LIKE ? OR org_number LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = db.execute(f"SELECT * FROM customers{where} ORDER BY name", tuple(params)).fetchall()
        return [CustomerRepository._row_to_customer(row) for row in rows]

    @staticmethod
    def _row_to_customer(row) -> Customer:
        return Customer(
            id=row["id"],
            name=row["name"],
            org_number=row["org_number"],
            email=row["email"],
            address=row["address"],
            payment_terms_days=row["payment_terms_days"],
            active=bool(row["active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


class ArticleRepository:
    @staticmethod
    def create(
        article_number: str,
        name: str,
        description: Optional[str] = None,
        unit: str = "st",
        unit_price: int = 0,
        vat_code: str = "MP1",
        revenue_account: str = "3010",
        active: bool = True,
    ) -> Article:
        article_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT INTO articles
                (id, article_number, name, description, unit, unit_price, vat_code, revenue_account, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article_id,
                article_number,
                name,
                description,
                unit,
                unit_price,
                vat_code,
                revenue_account,
                int(active),
                now,
                now,
            ),
        )
        db.commit()
        return Article(
            id=article_id,
            article_number=article_number,
            name=name,
            description=description,
            unit=unit,
            unit_price=unit_price,
            vat_code=vat_code,
            revenue_account=revenue_account,
            active=active,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def get(article_id: str) -> Optional[Article]:
        row = db.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        return ArticleRepository._row_to_article(row) if row else None

    @staticmethod
    def find_by_article_number(article_number: str) -> Optional[Article]:
        row = db.execute(
            "SELECT * FROM articles WHERE article_number = ? LIMIT 1", (article_number,)
        ).fetchone()
        return ArticleRepository._row_to_article(row) if row else None

    @staticmethod
    def list_all(active_only: bool = True, search: Optional[str] = None) -> List[Article]:
        clauses = []
        params = []
        if active_only:
            clauses.append("active = 1")
        if search:
            clauses.append("(article_number LIKE ? OR name LIKE ? OR description LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = db.execute(
            f"SELECT * FROM articles{where} ORDER BY article_number", tuple(params)
        ).fetchall()
        return [ArticleRepository._row_to_article(row) for row in rows]

    @staticmethod
    def _row_to_article(row) -> Article:
        return Article(
            id=row["id"],
            article_number=row["article_number"],
            name=row["name"],
            description=row["description"],
            unit=row["unit"],
            unit_price=row["unit_price"],
            vat_code=row["vat_code"],
            revenue_account=row["revenue_account"],
            active=bool(row["active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
