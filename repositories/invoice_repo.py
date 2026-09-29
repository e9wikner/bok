"""Invoice repository - data access for invoices (Fas 2).

Nothing here commits. The caller owns the transaction, so that issuing an
invoice can run in one `with db.transaction():` (SPEC-fakturering.md §5).
"""

import uuid
from datetime import date, datetime
from typing import List, Optional

from db.database import db
from domain.invoice_models import CreditNote, Invoice, InvoiceRow, Payment


def _col(row, name: str):
    """A column that only exists after a later migration, or None."""
    return row[name] if name in row.keys() else None


def _as_date(value) -> Optional[date]:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _as_datetime(value) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class InvoiceRepository:
    """Manage invoices."""

    @staticmethod
    def create(
        customer_name: str,
        invoice_date: date,
        due_date: date,
        customer_org_number: Optional[str] = None,
        customer_email: Optional[str] = None,
        description: Optional[str] = None,
        created_by: str = "system",
    ) -> Invoice:
        """Create new draft invoice."""
        invoice_id = str(uuid.uuid4())
        # Generate invoice number (YYYYMMDD001, etc)
        invoice_number = f"{invoice_date.strftime('%Y%m%d')}{InvoiceRepository._get_next_invoice_num(invoice_date.year)}"

        sql = """
        INSERT INTO invoices (id, invoice_number, customer_name, customer_org_number, customer_email,
                             invoice_date, due_date, description, status, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)
        """
        now = datetime.now()
        db.execute(
            sql,
            (
                invoice_id,
                invoice_number,
                customer_name,
                customer_org_number,
                customer_email,
                invoice_date,
                due_date,
                description,
                created_by,
                now,
            ),
        )

        return Invoice(
            id=invoice_id,
            invoice_number=invoice_number,
            customer_name=customer_name,
            customer_org_number=customer_org_number,
            customer_email=customer_email,
            invoice_date=invoice_date,
            due_date=due_date,
            description=description,
            created_by=created_by,
            created_at=now,
        )

    @staticmethod
    def add_row(
        invoice_id: str,
        description: str,
        quantity: int,
        unit_price: int,
        vat_code: str,
        revenue_account: Optional[str] = None,
    ) -> InvoiceRow:
        """Add row to invoice."""
        row_id = str(uuid.uuid4())
        amount_ex_vat = quantity * unit_price
        # Simple VAT calculation
        vat_rates = {"MP1": 0.25, "MP2": 0.12, "MP3": 0.06, "MF": 0.0}
        vat_rate = vat_rates.get(vat_code, 0)
        vat_amount = int(amount_ex_vat * vat_rate)
        amount_inc_vat = amount_ex_vat + vat_amount

        sql = """
        INSERT INTO invoice_rows (id, invoice_id, description, quantity, unit_price, vat_code,
                                 amount_ex_vat, vat_amount, amount_inc_vat, revenue_account, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = datetime.now()
        db.execute(
            sql,
            (
                row_id,
                invoice_id,
                description,
                quantity,
                unit_price,
                vat_code,
                amount_ex_vat,
                vat_amount,
                amount_inc_vat,
                revenue_account,
                now,
            ),
        )

        return InvoiceRow(
            id=row_id,
            invoice_id=invoice_id,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            vat_code=vat_code,
            amount_ex_vat=amount_ex_vat,
            vat_amount=vat_amount,
            amount_inc_vat=amount_inc_vat,
            revenue_account=revenue_account,
            created_at=now,
        )

    @staticmethod
    def get(invoice_id: str) -> Optional[Invoice]:
        """Get invoice by ID with all rows."""
        sql = "SELECT * FROM invoices WHERE id = ? LIMIT 1"
        cursor = db.execute(sql, (invoice_id,))
        row = cursor.fetchone()

        if not row:
            return None

        # Get rows
        rows_sql = "SELECT * FROM invoice_rows WHERE invoice_id = ? ORDER BY created_at"
        rows_cursor = db.execute(rows_sql, (invoice_id,))
        rows = []
        for row_data in rows_cursor.fetchall():
            rows.append(
                InvoiceRow(
                    id=row_data["id"],
                    invoice_id=row_data["invoice_id"],
                    description=row_data["description"],
                    quantity=row_data["quantity"],
                    unit_price=row_data["unit_price"],
                    vat_code=row_data["vat_code"],
                    amount_ex_vat=row_data["amount_ex_vat"],
                    vat_amount=row_data["vat_amount"],
                    amount_inc_vat=row_data["amount_inc_vat"],
                    revenue_account=(
                        row_data["revenue_account"]
                        if "revenue_account" in row_data.keys()
                        else None
                    ),
                    created_at=datetime.fromisoformat(row_data["created_at"]),
                    quantity_centi=_col(row_data, "quantity_centi"),
                    unit=_col(row_data, "unit") or "st",
                    delivery_from=_as_date(_col(row_data, "delivery_from")),
                    delivery_to=_as_date(_col(row_data, "delivery_to")),
                    delivery_month=_col(row_data, "delivery_month"),
                    article_number=_col(row_data, "article_number"),
                )
            )

        sent_at = row["sent_at"]
        if sent_at:
            sent_at = datetime.fromisoformat(sent_at)

        return Invoice(
            id=row["id"],
            invoice_number=row["invoice_number"],
            customer_name=row["customer_name"],
            customer_org_number=row["customer_org_number"],
            customer_email=row["customer_email"],
            invoice_date=datetime.fromisoformat(row["invoice_date"]).date(),
            due_date=datetime.fromisoformat(row["due_date"]).date(),
            description=row["description"],
            rows=rows,
            amount_ex_vat=row["amount_ex_vat"],
            vat_amount=row["vat_amount"],
            amount_inc_vat=row["amount_inc_vat"],
            status=row["status"],
            paid_amount=row["paid_amount"],
            voucher_id=row["voucher_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=row["created_by"],
            sent_at=sent_at,
            customer_address=_col(row, "customer_address"),
            customer_reference=_col(row, "customer_reference"),
            payment_terms_days=_col(row, "payment_terms_days"),
            source_draft_id=_col(row, "source_draft_id"),
            pdf_sha256=_col(row, "pdf_sha256"),
            pdf_path=_col(row, "pdf_path"),
            issued_at=_as_datetime(_col(row, "issued_at")),
            issued_by=_col(row, "issued_by"),
        )

    @staticmethod
    def list_all(status: Optional[str] = None) -> List[Invoice]:
        """List all invoices, optionally filtered by status."""
        sql = "SELECT id FROM invoices"
        params = []

        if status:
            sql += " WHERE status = ?"
            params.append(status)

        sql += " ORDER BY invoice_date DESC, invoice_number DESC"

        cursor = db.execute(sql, tuple(params))
        invoices = []
        for row in cursor.fetchall():
            invoice = InvoiceRepository.get(row["id"])
            if invoice:
                invoices.append(invoice)
        return invoices

    @staticmethod
    def list_for_customer(customer_name: str) -> List[Invoice]:
        """List all invoices for a customer."""
        sql = (
            "SELECT id FROM invoices WHERE customer_name = ? ORDER BY invoice_date DESC"
        )
        cursor = db.execute(sql, (customer_name,))
        invoices = []
        for row in cursor.fetchall():
            invoice = InvoiceRepository.get(row["id"])
            if invoice:
                invoices.append(invoice)
        return invoices

    @staticmethod
    def update_status(invoice_id: str, status: str) -> bool:
        """Update invoice status."""
        sql = "UPDATE invoices SET status = ? WHERE id = ?"
        db.execute(sql, (status, invoice_id))
        return True

    @staticmethod
    def update_sent(invoice_id: str) -> bool:
        """Mark invoice as sent."""
        sql = "UPDATE invoices SET status = 'sent', sent_at = ? WHERE id = ?"
        db.execute(sql, (datetime.now(), invoice_id))
        return True

    @staticmethod
    def update_paid_amount(invoice_id: str, payment_amount: int) -> bool:
        """Update cumulative paid amount."""
        sql = """
        UPDATE invoices
        SET paid_amount = paid_amount + ?,
            status = CASE
                WHEN paid_amount + ? >= amount_inc_vat THEN 'paid'
                ELSE 'partially_paid'
            END
        WHERE id = ?
        """
        db.execute(sql, (payment_amount, payment_amount, invoice_id))
        return True

    @staticmethod
    def link_voucher(invoice_id: str, voucher_id: str) -> bool:
        """Link invoice to accounting voucher."""
        sql = "UPDATE invoices SET voucher_id = ? WHERE id = ?"
        db.execute(sql, (voucher_id, invoice_id))
        return True

    @staticmethod
    def update_totals(invoice_id: str, ex_vat: int, vat: int, inc_vat: int) -> bool:
        """Update invoice totals."""
        sql = "UPDATE invoices SET amount_ex_vat = ?, vat_amount = ?, amount_inc_vat = ? WHERE id = ?"
        db.execute(sql, (ex_vat, vat, inc_vat, invoice_id))
        return True

    # --- Utfärdande (SPEC-fakturering.md §5) --------------------------------
    #
    # Migration 038 locks every column but status and paid_amount once
    # issued_at is set. The issue path therefore inserts the invoice with
    # issued_at NULL, links the voucher, and sets the issue columns in one
    # last UPDATE (`mark_issued`).

    @staticmethod
    def create_for_issue(
        invoice_number: str,
        source_draft_id: str,
        customer_name: str,
        invoice_date: date,
        due_date: date,
        customer_org_number: Optional[str],
        customer_email: Optional[str],
        customer_address: str,
        customer_reference: Optional[str],
        payment_terms_days: int,
        description: Optional[str],
        amount_ex_vat: int,
        vat_amount: int,
        amount_inc_vat: int,
        created_by: str,
    ) -> str:
        """Insert the invoice with the given number, not yet issued. The
        UNIQUE number and the unique index on `source_draft_id` raise
        `sqlite3.IntegrityError` for a taken number or an issued draft."""
        invoice_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO invoices (
                id, invoice_number, customer_name, customer_org_number,
                customer_email, customer_address, customer_reference,
                payment_terms_days, invoice_date, due_date, description,
                status, amount_ex_vat, vat_amount, amount_inc_vat, paid_amount,
                source_draft_id, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                invoice_id,
                invoice_number,
                customer_name,
                customer_org_number,
                customer_email,
                customer_address,
                customer_reference,
                payment_terms_days,
                invoice_date.isoformat(),
                due_date.isoformat(),
                description,
                amount_ex_vat,
                vat_amount,
                amount_inc_vat,
                source_draft_id,
                created_by,
                datetime.now(),
            ),
        )
        return invoice_id

    @staticmethod
    def insert_issue_row(
        invoice_id: str,
        description: str,
        quantity: int,
        quantity_centi: int,
        unit: str,
        unit_price: int,
        vat_code: str,
        revenue_account: Optional[str],
        amount_ex_vat: int,
        vat_amount: int,
        amount_inc_vat: int,
        delivery_from: Optional[date],
        delivery_to: Optional[date],
        delivery_month: Optional[str],
        article_number: Optional[str],
    ) -> str:
        """Insert one row as given. The amounts are the caller's, computed
        on `quantity_centi` (§4.2); `quantity` is the legacy column."""
        row_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO invoice_rows (
                id, invoice_id, description, quantity, quantity_centi, unit,
                unit_price, vat_code, revenue_account, amount_ex_vat, vat_amount,
                amount_inc_vat, delivery_from, delivery_to, delivery_month,
                article_number, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                invoice_id,
                description,
                quantity,
                quantity_centi,
                unit,
                unit_price,
                vat_code,
                revenue_account,
                amount_ex_vat,
                vat_amount,
                amount_inc_vat,
                delivery_from.isoformat() if delivery_from else None,
                delivery_to.isoformat() if delivery_to else None,
                delivery_month,
                article_number,
                datetime.now(),
            ),
        )
        return row_id

    @staticmethod
    def mark_issued(
        invoice_id: str,
        pdf_sha256: str,
        pdf_path: str,
        issued_at: datetime,
        issued_by: str,
        status: str = "sent",
    ) -> None:
        """The last write to the invoice: after it, the triggers let only
        status and paid_amount change."""
        db.execute(
            """
            UPDATE invoices
            SET pdf_sha256 = ?, pdf_path = ?, issued_at = ?, issued_by = ?,
                status = ?
            WHERE id = ? AND issued_at IS NULL
            """,
            (pdf_sha256, pdf_path, issued_at, issued_by, status, invoice_id),
        )

    @staticmethod
    def find_id_by_number(invoice_number: str) -> Optional[str]:
        row = db.execute(
            "SELECT id FROM invoices WHERE invoice_number = ? LIMIT 1",
            (invoice_number,),
        ).fetchone()
        return row["id"] if row else None

    @staticmethod
    def find_id_by_source_draft(draft_id: str) -> Optional[str]:
        row = db.execute(
            "SELECT id FROM invoices WHERE source_draft_id = ? LIMIT 1",
            (draft_id,),
        ).fetchone()
        return row["id"] if row else None

    @staticmethod
    def _get_next_invoice_num(year: int) -> str:
        """Get next sequential invoice number for year."""
        sql = "SELECT COUNT(*) as cnt FROM invoices WHERE strftime('%Y', invoice_date) = ?"
        cursor = db.execute(sql, (str(year),))
        row = cursor.fetchone()
        count = row["cnt"] + 1
        return f"{count:03d}"


class PaymentRepository:
    """Manage payments."""

    @staticmethod
    def create(
        invoice_id: str,
        amount: int,
        payment_date: date,
        payment_method: str,
        reference: Optional[str] = None,
        notes: Optional[str] = None,
        created_by: str = "system",
    ) -> Payment:
        """Record a payment."""
        payment_id = str(uuid.uuid4())
        sql = """
        INSERT INTO payments (id, invoice_id, amount, payment_date, payment_method, reference, notes, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = datetime.now()
        db.execute(
            sql,
            (
                payment_id,
                invoice_id,
                amount,
                payment_date,
                payment_method,
                reference,
                notes,
                created_by,
                now,
            ),
        )

        return Payment(
            id=payment_id,
            invoice_id=invoice_id,
            amount=amount,
            payment_date=payment_date,
            payment_method=payment_method,
            reference=reference,
            notes=notes,
            created_by=created_by,
            created_at=now,
        )

    @staticmethod
    def get(payment_id: str) -> Optional[Payment]:
        """Get payment by ID."""
        sql = "SELECT * FROM payments WHERE id = ? LIMIT 1"
        cursor = db.execute(sql, (payment_id,))
        row = cursor.fetchone()

        if not row:
            return None

        return Payment(
            id=row["id"],
            invoice_id=row["invoice_id"],
            amount=row["amount"],
            payment_date=datetime.fromisoformat(row["payment_date"]).date(),
            payment_method=row["payment_method"],
            reference=row["reference"],
            voucher_id=row["voucher_id"],
            notes=row["notes"],
            created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def list_for_invoice(invoice_id: str) -> List[Payment]:
        """List all payments for an invoice."""
        sql = "SELECT id FROM payments WHERE invoice_id = ? ORDER BY payment_date DESC"
        cursor = db.execute(sql, (invoice_id,))
        payments = []
        for row in cursor.fetchall():
            payment = PaymentRepository.get(row["id"])
            if payment:
                payments.append(payment)
        return payments

    @staticmethod
    def link_voucher(payment_id: str, voucher_id: str) -> bool:
        """Link payment to accounting voucher."""
        sql = "UPDATE payments SET voucher_id = ? WHERE id = ?"
        db.execute(sql, (voucher_id, payment_id))
        return True


class CreditNoteRepository:
    """Manage credit notes."""

    @staticmethod
    def create(
        invoice_id: str,
        reason: str,
        amount_ex_vat: int,
        vat_amount: int,
        credit_date: date,
        created_by: str = "system",
    ) -> CreditNote:
        """Create credit note."""
        credit_id = str(uuid.uuid4())
        credit_number = (
            f"CN-{credit_date.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        )
        amount_inc_vat = amount_ex_vat + vat_amount

        sql = """
        INSERT INTO credit_notes (id, credit_note_number, invoice_id, reason, amount_ex_vat,
                                 vat_amount, amount_inc_vat, credit_date, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = datetime.now()
        db.execute(
            sql,
            (
                credit_id,
                credit_number,
                invoice_id,
                reason,
                amount_ex_vat,
                vat_amount,
                amount_inc_vat,
                credit_date,
                created_by,
                now,
            ),
        )

        return CreditNote(
            id=credit_id,
            credit_note_number=credit_number,
            invoice_id=invoice_id,
            reason=reason,
            amount_ex_vat=amount_ex_vat,
            vat_amount=vat_amount,
            amount_inc_vat=amount_inc_vat,
            credit_date=credit_date,
            created_by=created_by,
            created_at=now,
        )

    @staticmethod
    def get(credit_id: str) -> Optional[CreditNote]:
        """Get credit note by ID."""
        sql = "SELECT * FROM credit_notes WHERE id = ? LIMIT 1"
        cursor = db.execute(sql, (credit_id,))
        row = cursor.fetchone()

        if not row:
            return None

        return CreditNote(
            id=row["id"],
            credit_note_number=row["credit_note_number"],
            invoice_id=row["invoice_id"],
            reason=row["reason"],
            amount_ex_vat=row["amount_ex_vat"],
            vat_amount=row["vat_amount"],
            amount_inc_vat=row["amount_inc_vat"],
            credit_date=datetime.fromisoformat(row["credit_date"]).date(),
            voucher_id=row["voucher_id"],
            created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def link_voucher(credit_id: str, voucher_id: str) -> bool:
        """Link credit note to accounting voucher."""
        sql = "UPDATE credit_notes SET voucher_id = ? WHERE id = ?"
        db.execute(sql, (voucher_id, credit_id))
        return True
