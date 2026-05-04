"""Invoice repository - data access for invoices (Fas 2)."""

from typing import Optional, List
from datetime import date, datetime
import uuid
from db.database import db
from domain.invoice_models import Invoice, InvoiceRow, Payment, CreditNote


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
        db.execute(sql, (
            invoice_id, invoice_number, customer_name, customer_org_number, customer_email,
            invoice_date, due_date, description, created_by, now
        ))
        db.commit()
        
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
            created_at=now
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
        db.execute(sql, (
            row_id, invoice_id, description, quantity, unit_price, vat_code,
            amount_ex_vat, vat_amount, amount_inc_vat, revenue_account, now
        ))
        db.commit()
        
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
            created_at=now
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
            rows.append(InvoiceRow(
                id=row_data["id"],
                invoice_id=row_data["invoice_id"],
                description=row_data["description"],
                quantity=row_data["quantity"],
                unit_price=row_data["unit_price"],
                vat_code=row_data["vat_code"],
                amount_ex_vat=row_data["amount_ex_vat"],
                vat_amount=row_data["vat_amount"],
                amount_inc_vat=row_data["amount_inc_vat"],
                revenue_account=row_data["revenue_account"] if "revenue_account" in row_data.keys() else None,
                created_at=datetime.fromisoformat(row_data["created_at"])
            ))
        
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
            sent_at=sent_at
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
        sql = "SELECT id FROM invoices WHERE customer_name = ? ORDER BY invoice_date DESC"
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
        db.commit()
        return True
    
    @staticmethod
    def update_sent(invoice_id: str) -> bool:
        """Mark invoice as sent."""
        sql = "UPDATE invoices SET status = 'sent', sent_at = ? WHERE id = ?"
        db.execute(sql, (datetime.now(), invoice_id))
        db.commit()
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
        db.commit()
        return True
    
    @staticmethod
    def link_voucher(invoice_id: str, voucher_id: str) -> bool:
        """Link invoice to accounting voucher."""
        sql = "UPDATE invoices SET voucher_id = ? WHERE id = ?"
        db.execute(sql, (voucher_id, invoice_id))
        db.commit()
        return True
    
    @staticmethod
    def update_totals(invoice_id: str, ex_vat: int, vat: int, inc_vat: int) -> bool:
        """Update invoice totals."""
        sql = "UPDATE invoices SET amount_ex_vat = ?, vat_amount = ?, amount_inc_vat = ? WHERE id = ?"
        db.execute(sql, (ex_vat, vat, inc_vat, invoice_id))
        db.commit()
        return True
    
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
        db.execute(sql, (
            payment_id, invoice_id, amount, payment_date, payment_method, reference, notes, created_by, now
        ))
        db.commit()
        
        return Payment(
            id=payment_id,
            invoice_id=invoice_id,
            amount=amount,
            payment_date=payment_date,
            payment_method=payment_method,
            reference=reference,
            notes=notes,
            created_by=created_by,
            created_at=now
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
            created_at=datetime.fromisoformat(row["created_at"])
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
        db.commit()
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
        credit_number = f"CN-{credit_date.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        amount_inc_vat = amount_ex_vat + vat_amount
        
        sql = """
        INSERT INTO credit_notes (id, credit_note_number, invoice_id, reason, amount_ex_vat, 
                                 vat_amount, amount_inc_vat, credit_date, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = datetime.now()
        db.execute(sql, (
            credit_id, credit_number, invoice_id, reason, amount_ex_vat, vat_amount, 
            amount_inc_vat, credit_date, created_by, now
        ))
        db.commit()
        
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
            created_at=now
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
            created_at=datetime.fromisoformat(row["created_at"])
        )
    
    @staticmethod
    def link_voucher(credit_id: str, voucher_id: str) -> bool:
        """Link credit note to accounting voucher."""
        sql = "UPDATE credit_notes SET voucher_id = ? WHERE id = ?"
        db.execute(sql, (voucher_id, credit_id))
        db.commit()
        return True
