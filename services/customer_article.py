"""Services for customer and article registers."""

from typing import Optional

from domain.invoice_validation import VATCalculator, ValidationError
from repositories.account_repo import AccountRepository
from repositories.customer_article_repo import ArticleRepository, CustomerRepository


class CustomerService:
    def create_customer(
        self,
        name: str,
        org_number: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
        payment_terms_days: int = 30,
    ):
        if not name.strip():
            raise ValidationError("invalid_customer", "Customer name is required")
        if payment_terms_days < 0:
            raise ValidationError("invalid_payment_terms", "Payment terms must be non-negative")
        if org_number and CustomerRepository.find_by_org_number(org_number):
            raise ValidationError("duplicate_customer", "Customer org number already exists")
        return CustomerRepository.create(
            name=name.strip(),
            org_number=org_number,
            email=email,
            address=address,
            payment_terms_days=payment_terms_days,
        )

    def list_customers(self, active_only: bool = True, search: Optional[str] = None):
        return CustomerRepository.list_all(active_only=active_only, search=search)


class ArticleService:
    def create_article(
        self,
        article_number: str,
        name: str,
        description: Optional[str] = None,
        unit: str = "st",
        unit_price: int = 0,
        vat_code: str = "MP1",
        revenue_account: str = "3010",
    ):
        if not article_number.strip() or not name.strip():
            raise ValidationError("invalid_article", "Article number and name are required")
        if ArticleRepository.find_by_article_number(article_number):
            raise ValidationError("duplicate_article", "Article number already exists")
        if unit_price < 0:
            raise ValidationError("invalid_unit_price", "Unit price must be non-negative")
        if not VATCalculator.validate_vat_code(vat_code):
            raise ValidationError("invalid_vat_code", f"Invalid VAT code: {vat_code}")
        account = AccountRepository.get(revenue_account)
        if not account:
            raise ValidationError("invalid_revenue_account", f"Account {revenue_account} does not exist")
        return ArticleRepository.create(
            article_number=article_number.strip(),
            name=name.strip(),
            description=description,
            unit=unit,
            unit_price=unit_price,
            vat_code=vat_code,
            revenue_account=revenue_account,
        )

    def list_articles(self, active_only: bool = True, search: Optional[str] = None):
        return ArticleRepository.list_all(active_only=active_only, search=search)
