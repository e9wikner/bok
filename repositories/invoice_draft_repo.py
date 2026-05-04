"""Repository for agent-created invoice drafts."""

from datetime import datetime
from typing import List, Optional
import uuid

from db.database import db
from domain.invoice_draft_models import InvoiceDraft, InvoiceDraftRow


class InvoiceDraftRepository:
    @staticmethod
    def create(
        customer_name: str,
        invoice_date,
        due_date,
        customer_id: Optional[str] = None,
        customer_org_number: Optional[str] = None,
        customer_email: Optional[str] = None,
        reference: Optional[str] = None,
        description: Optional[str] = None,
        status: str = "needs_review",
        agent_summary: Optional[str] = None,
        agent_confidence: Optional[float] = None,
        agent_warnings: Optional[str] = None,
        created_by: str = "system",
    ) -> InvoiceDraft:
        draft_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT INTO invoice_drafts
                (id, customer_id, customer_name, customer_org_number, customer_email,
                 invoice_date, due_date, reference, description, status,
                 agent_summary, agent_confidence, agent_warnings, created_at, created_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft_id,
                customer_id,
                customer_name,
                customer_org_number,
                customer_email,
                invoice_date,
                due_date,
                reference,
                description,
                status,
                agent_summary,
                agent_confidence,
                agent_warnings,
                now,
                created_by,
                now,
            ),
        )
        db.commit()
        return InvoiceDraftRepository.get(draft_id)

    @staticmethod
    def add_row(
        draft_id: str,
        description: str,
        quantity: int,
        unit_price: int,
        vat_code: str,
        revenue_account: str,
        amount_ex_vat: int,
        vat_amount: int,
        amount_inc_vat: int,
        article_id: Optional[str] = None,
        source_note: Optional[str] = None,
    ) -> InvoiceDraftRow:
        row_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT INTO invoice_draft_rows
                (id, draft_id, article_id, description, quantity, unit_price, vat_code,
                 revenue_account, amount_ex_vat, vat_amount, amount_inc_vat, source_note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                draft_id,
                article_id,
                description,
                quantity,
                unit_price,
                vat_code,
                revenue_account,
                amount_ex_vat,
                vat_amount,
                amount_inc_vat,
                source_note,
                now,
            ),
        )
        db.commit()
        return InvoiceDraftRow(
            id=row_id,
            draft_id=draft_id,
            article_id=article_id,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            vat_code=vat_code,
            revenue_account=revenue_account,
            amount_ex_vat=amount_ex_vat,
            vat_amount=vat_amount,
            amount_inc_vat=amount_inc_vat,
            source_note=source_note,
            created_at=now,
        )

    @staticmethod
    def replace_rows(draft_id: str, rows: List[dict]) -> None:
        db.execute("DELETE FROM invoice_draft_rows WHERE draft_id = ?", (draft_id,))
        db.commit()
        for row in rows:
            InvoiceDraftRepository.add_row(draft_id=draft_id, **row)
        InvoiceDraftRepository.recalculate_totals(draft_id)

    @staticmethod
    def recalculate_totals(draft_id: str) -> None:
        row = db.execute(
            """
            SELECT
                COALESCE(SUM(amount_ex_vat), 0) AS amount_ex_vat,
                COALESCE(SUM(vat_amount), 0) AS vat_amount,
                COALESCE(SUM(amount_inc_vat), 0) AS amount_inc_vat
            FROM invoice_draft_rows
            WHERE draft_id = ?
            """,
            (draft_id,),
        ).fetchone()
        db.execute(
            """
            UPDATE invoice_drafts
            SET amount_ex_vat = ?, vat_amount = ?, amount_inc_vat = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                row["amount_ex_vat"],
                row["vat_amount"],
                row["amount_inc_vat"],
                datetime.now(),
                draft_id,
            ),
        )
        db.commit()

    @staticmethod
    def get(draft_id: str) -> Optional[InvoiceDraft]:
        row = db.execute("SELECT * FROM invoice_drafts WHERE id = ?", (draft_id,)).fetchone()
        if not row:
            return None
        rows = db.execute(
            "SELECT * FROM invoice_draft_rows WHERE draft_id = ? ORDER BY created_at",
            (draft_id,),
        ).fetchall()
        draft = InvoiceDraftRepository._row_to_draft(row)
        draft.rows = [InvoiceDraftRepository._row_to_draft_row(r) for r in rows]
        return draft

    @staticmethod
    def list_all(status: Optional[str] = None) -> List[InvoiceDraft]:
        sql = "SELECT id FROM invoice_drafts"
        params = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY invoice_date DESC, created_at DESC"
        rows = db.execute(sql, tuple(params)).fetchall()
        return [draft for row in rows if (draft := InvoiceDraftRepository.get(row["id"]))]

    @staticmethod
    def mark_booked(draft_id: str, invoice_id: str, voucher_id: str) -> None:
        db.execute(
            """
            UPDATE invoice_drafts
            SET status = 'booked', approved_invoice_id = ?, approved_voucher_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (invoice_id, voucher_id, datetime.now(), draft_id),
        )
        db.commit()

    @staticmethod
    def update_status(draft_id: str, status: str) -> None:
        db.execute(
            "UPDATE invoice_drafts SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now(), draft_id),
        )
        db.commit()

    @staticmethod
    def _row_to_draft(row) -> InvoiceDraft:
        return InvoiceDraft(
            id=row["id"],
            customer_id=row["customer_id"],
            customer_name=row["customer_name"],
            customer_org_number=row["customer_org_number"],
            customer_email=row["customer_email"],
            invoice_date=datetime.fromisoformat(row["invoice_date"]).date(),
            due_date=datetime.fromisoformat(row["due_date"]).date(),
            reference=row["reference"],
            description=row["description"],
            status=row["status"],
            amount_ex_vat=row["amount_ex_vat"],
            vat_amount=row["vat_amount"],
            amount_inc_vat=row["amount_inc_vat"],
            agent_summary=row["agent_summary"],
            agent_confidence=row["agent_confidence"],
            agent_warnings=row["agent_warnings"],
            approved_invoice_id=row["approved_invoice_id"],
            approved_voucher_id=row["approved_voucher_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=row["created_by"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _row_to_draft_row(row) -> InvoiceDraftRow:
        return InvoiceDraftRow(
            id=row["id"],
            draft_id=row["draft_id"],
            article_id=row["article_id"],
            description=row["description"],
            quantity=row["quantity"],
            unit_price=row["unit_price"],
            vat_code=row["vat_code"],
            revenue_account=row["revenue_account"],
            amount_ex_vat=row["amount_ex_vat"],
            vat_amount=row["vat_amount"],
            amount_inc_vat=row["amount_inc_vat"],
            source_note=row["source_note"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
