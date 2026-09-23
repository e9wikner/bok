"""Voucher repository - data access for vouchers."""

import uuid
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence, Tuple

from db.database import db
from domain.models import Voucher, VoucherRow
from domain.types import VoucherSeries, VoucherStatus

# Derived voucher fields (SPEC-oversikt.md §3). Never stored: migration 014
# aborts every UPDATE on a posted voucher, so a flag column could not be kept
# in sync without softening the trigger. Both fragments reference the table by
# name, so they only work in queries where `vouchers` is unaliased.
MISSING_ATTACHMENT_SQL = (
    "NOT EXISTS (SELECT 1 FROM attachments a WHERE a.voucher_id = vouchers.id)"
)
# Age of the business event, not of the posting: counted from vouchers.date,
# in whole days, local time.
AGE_DAYS_SQL = (
    "CAST(julianday(date('now', 'localtime')) - julianday(vouchers.date) AS INTEGER)"
)


class VoucherRepository:
    """Manage vouchers (Verifikationer) - append-only storage."""

    @staticmethod
    def create(
        series: str,
        date: date,
        period_id: str,
        description: str,
        fiscal_year_id: str,
        created_by: str = "system",
        _commit: bool = True,
    ) -> Voucher:
        """Create new draft voucher.

        A draft has no number: it gets one when it is posted (`post`), so a
        draft that is deleted or never posted leaves no gap in the series.
        """
        voucher_id = str(uuid.uuid4())
        sql = """
        INSERT INTO vouchers (id, series, date, period_id, fiscal_year_id, description, status, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?)
        """
        now = datetime.now()
        db.execute(
            sql,
            (
                voucher_id,
                series,
                date,
                period_id,
                fiscal_year_id,
                description,
                created_by,
                now,
            ),
        )
        if _commit:
            db.commit()

        return Voucher(
            id=voucher_id,
            series=VoucherSeries(series),
            number=None,
            date=date,
            period_id=period_id,
            description=description,
            status=VoucherStatus.DRAFT,
            fiscal_year_id=fiscal_year_id,
            created_at=now,
            created_by=created_by,
        )

    @staticmethod
    def add_row(
        voucher_id: str,
        account_code: str,
        debit: int = 0,
        credit: int = 0,
        description: Optional[str] = None,
        _commit: bool = True,
    ) -> VoucherRow:
        """Add accounting row to draft voucher."""
        row_id = str(uuid.uuid4())
        sql = """
        INSERT INTO voucher_rows (id, voucher_id, account_code, debit, credit, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        now = datetime.now()
        db.execute(
            sql, (row_id, voucher_id, account_code, debit, credit, description, now)
        )
        if _commit:
            db.commit()

        return VoucherRow(
            id=row_id,
            voucher_id=voucher_id,
            account_code=account_code,
            debit=debit,
            credit=credit,
            description=description,
            created_at=now,
        )

    @staticmethod
    def get(voucher_id: str) -> Optional[Voucher]:
        """Get voucher by ID with all rows.

        The two derived fields ride along in this query, so reading a voucher
        costs no more than it did before they existed.
        """
        sql = f"""
            SELECT *,
                   {MISSING_ATTACHMENT_SQL} AS missing_attachment,
                   {AGE_DAYS_SQL} AS age_days
            FROM vouchers WHERE id = ? LIMIT 1
        """
        cursor = db.execute(sql, (voucher_id,))
        row = cursor.fetchone()

        if not row:
            return None

        # Get rows
        rows_sql = "SELECT * FROM voucher_rows WHERE voucher_id = ? ORDER BY created_at"
        rows_cursor = db.execute(rows_sql, (voucher_id,))
        rows = []
        for row_data in rows_cursor.fetchall():
            rows.append(
                VoucherRow(
                    id=row_data["id"],
                    voucher_id=row_data["voucher_id"],
                    account_code=row_data["account_code"],
                    debit=row_data["debit"],
                    credit=row_data["credit"],
                    description=row_data["description"],
                    created_at=datetime.fromisoformat(row_data["created_at"]),
                )
            )

        posted_at = row["posted_at"]
        if posted_at:
            posted_at = datetime.fromisoformat(posted_at)

        return Voucher(
            id=row["id"],
            series=VoucherSeries(row["series"]),
            number=row["number"],
            date=datetime.fromisoformat(row["date"]).date(),
            period_id=row["period_id"],
            description=row["description"],
            status=VoucherStatus(row["status"]),
            fiscal_year_id=(
                row["fiscal_year_id"] if "fiscal_year_id" in row.keys() else None
            ),
            rows=rows,
            correction_of=row["correction_of"],
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=row["created_by"],
            posted_at=posted_at,
            missing_attachment=bool(row["missing_attachment"]),
            age_days=row["age_days"],
        )

    @staticmethod
    def list_for_period(period_id: str, status: Optional[str] = None) -> List[Voucher]:
        """List vouchers for a period."""
        sql = "SELECT id FROM vouchers WHERE period_id = ?"
        params = [period_id]

        if status:
            sql += " AND status = ?"
            params.append(status)

        sql += " ORDER BY date, series, number"

        cursor = db.execute(sql, tuple(params))
        vouchers = []
        for row in cursor.fetchall():
            voucher = VoucherRepository.get(row["id"])
            if voucher:
                vouchers.append(voucher)
        return vouchers

    @staticmethod
    def list_all(
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        fiscal_year_id: Optional[str] = None,
        exclude_series: Optional[List[str]] = None,
        missing_attachment: Optional[bool] = None,
    ) -> tuple[List[Voucher], int]:
        """List all vouchers across all periods.

        Returns (vouchers, total_count) to support pagination.
        When *search* is given, filters on description (LIKE) or voucher number.
        *missing_attachment* selects posted vouchers with (False) or without
        (True) a linked attachment; a draft is neither (SPEC-oversikt.md §6.4).
        *sort_order* defaults to descending, except for ``sort_by="age"`` where
        oldest first is what the caller asked for.
        """
        where_clauses = []
        params: list = []

        if status:
            where_clauses.append("status = ?")
            params.append(status)

        if fiscal_year_id:
            where_clauses.append("fiscal_year_id = ?")
            params.append(fiscal_year_id)

        if exclude_series:
            placeholders = ", ".join(["?"] * len(exclude_series))
            where_clauses.append(f"series NOT IN ({placeholders})")
            params.extend(exclude_series)

        if search:
            where_clauses.append("(description LIKE ? OR CAST(number AS TEXT) LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like])

        if missing_attachment is not None:
            # The flag only means something on a posted voucher: a draft
            # without an attachment is a draft, not a complement to chase.
            negation = "" if missing_attachment else "NOT "
            where_clauses.append(
                f"(status = 'posted' AND {negation}{MISSING_ATTACHMENT_SQL})"
            )

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # Total count
        count_sql = f"SELECT COUNT(*) as cnt FROM vouchers{where_sql}"
        total = db.execute(count_sql, tuple(params)).fetchone()["cnt"]

        # Sorting. The whitelist is the boundary against SQL injection in
        # ORDER BY - it stays a whitelist. "age" sorts on the same column as
        # "date"; what differs is that it defaults to oldest first.
        allowed_sort = {"date", "number", "age"}
        sort_col = sort_by if sort_by in allowed_sort else "date"
        if sort_order is None:
            sort_order = "asc" if sort_col == "age" else "desc"
        sort_dir = "ASC" if sort_order == "asc" else "DESC"
        if sort_col == "number":
            # A draft has no number (SPEC-flode-verifikationer §4.3). SQLite
            # puts NULL first in ASC and last in DESC; drafts go last in both
            # directions, after the posted series they have not joined yet.
            order_clause = (
                f"number IS NULL, series {sort_dir}, number {sort_dir}, "
                f"date {sort_dir}"
            )
        else:
            order_clause = f"date {sort_dir}, series, number"

        # Fetch page
        sql = f"SELECT id FROM vouchers{where_sql} ORDER BY {order_clause}"
        page_params = list(params)

        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            page_params.extend([limit, offset])

        cursor = db.execute(sql, tuple(page_params))
        vouchers = []
        for row in cursor.fetchall():
            voucher = VoucherRepository.get(row["id"])
            if voucher:
                vouchers.append(voucher)
        return vouchers, total

    @staticmethod
    def count_missing_attachments() -> int:
        """Posted vouchers with no attachment linked (SPEC-oversikt.md §3)."""
        sql = f"""
            SELECT COUNT(*) AS cnt FROM vouchers
            WHERE status = 'posted' AND {MISSING_ATTACHMENT_SQL}
        """
        return db.execute(sql).fetchone()["cnt"]

    @staticmethod
    def numbers_for(voucher_ids: Sequence[str]) -> Dict[str, Tuple[str, int]]:
        """`{id: (series, number)}` for those of `voucher_ids` that are
        posted, in one query -- a list of drafts asks once, not once per
        row (SPEC-flode-verifikationer §10). Drafts have no number and are
        left out, as are ids with no voucher (a superseded draft's voucher
        is deleted)."""
        ids = list(dict.fromkeys(voucher_ids))
        if not ids:
            return {}
        placeholders = ", ".join("?" for _ in ids)
        rows = db.execute(
            f"SELECT id, series, number FROM vouchers "
            f"WHERE status = 'posted' AND id IN ({placeholders})",
            tuple(ids),
        ).fetchall()
        return {row["id"]: (row["series"], row["number"]) for row in rows}

    @staticmethod
    def account_balances_around(voucher_id: str) -> List[Tuple[str, int, int]]:
        """Each account a posted voucher touches, once, in the order its rows
        first name it, with the account's balance (debit - credit, öre) in
        the voucher's fiscal year before and after the voucher
        (SPEC-flode-verifikationer §8.2, the receipt).

        *Before* sums the posted rows of vouchers in the same fiscal year
        that were posted earlier than this one (`posted_at`, then `rowid`
        for a tie), so a receipt written late -- on a resumed replay --
        still says what the posting changed when it happened. *After* is
        before plus the voucher's own net on the account. One statement: the
        correlated sum runs per touched account inside SQLite, not per
        account in a Python loop.
        """
        sql = """
            WITH v AS (
                SELECT rowid AS rid, id, fiscal_year_id, posted_at
                FROM vouchers WHERE id = ?
            ),
            touched AS (
                SELECT account_code,
                       MIN(rowid) AS first_row,
                       SUM(debit - credit) AS own
                FROM voucher_rows
                WHERE voucher_id = (SELECT id FROM v)
                GROUP BY account_code
            )
            SELECT t.account_code AS account_code,
                   COALESCE((
                       SELECT SUM(r.debit - r.credit)
                       FROM voucher_rows AS r
                       JOIN vouchers AS o ON o.id = r.voucher_id
                       WHERE r.account_code = t.account_code
                         AND o.status = 'posted'
                         AND o.fiscal_year_id = v.fiscal_year_id
                         AND o.id != v.id
                         AND (COALESCE(o.posted_at, '') < v.posted_at
                              OR (COALESCE(o.posted_at, '') = v.posted_at
                                  AND o.rowid < v.rid))
                   ), 0) AS before_ore,
                   t.own AS own_ore
            FROM touched AS t CROSS JOIN v
            ORDER BY t.first_row
        """
        rows = db.execute(sql, (voucher_id,)).fetchall()
        return [
            (
                row["account_code"],
                row["before_ore"],
                row["before_ore"] + row["own_ore"],
            )
            for row in rows
        ]

    @staticmethod
    def get_next_number(series: str, fiscal_year_id: str) -> int:
        """Next voucher number for a series within a fiscal year.

        Counted over *posted* vouchers only — drafts have no number. Numbers
        restart from 1 each fiscal year (BFL requirement). Informational:
        `post` assigns the number itself, in the same statement as the
        status change.
        """
        sql = """
            SELECT MAX(number) as max_num
            FROM vouchers
            WHERE series = ? AND fiscal_year_id = ? AND status = 'posted'
        """
        cursor = db.execute(sql, (series, fiscal_year_id))
        row = cursor.fetchone()
        return (row["max_num"] or 0) + 1

    @staticmethod
    def post(
        voucher_id: str, number: Optional[int] = None, _commit: bool = True
    ) -> int:
        """Post a draft voucher (make immutable - BFL varaktighet requirement).

        The number is set in the same UPDATE as the status change (SPEC
        flode-verifikationer §4.3): *number* when given (SIE4 import keeps the
        file's numbers), otherwise MAX(number) + 1 over posted vouchers in the
        same series and fiscal year. One statement, so the read and the write
        cannot land in different transactions; UNIQUE(series, number,
        fiscal_year_id) is the backstop. Returns the number assigned.
        """
        sql = """
            UPDATE vouchers
            SET status = 'posted',
                posted_at = ?,
                number = COALESCE(?, (
                    SELECT COALESCE(MAX(p.number), 0) + 1
                    FROM vouchers AS p
                    WHERE p.series = vouchers.series
                      AND p.fiscal_year_id = vouchers.fiscal_year_id
                      AND p.status = 'posted'
                ))
            WHERE id = ? AND status = 'draft'
        """
        cursor = db.execute(sql, (datetime.now(), number, voucher_id))
        if cursor.rowcount != 1:
            raise ValueError(f"Voucher {voucher_id} is not a draft")
        assigned = db.execute(
            "SELECT number FROM vouchers WHERE id = ?", (voucher_id,)
        ).fetchone()["number"]
        if _commit:
            db.commit()
        return assigned

    @staticmethod
    def create_correction(
        original_voucher_id: str,
        series: str = "B",
        created_by: str = "system",
        period_id_override: str = None,
        _commit: bool = True,
        voucher_date: Optional[date] = None,
        description: Optional[str] = None,
    ) -> Voucher:
        """Create correction voucher (B-series) for an original voucher.

        If period_id_override is given, the correction is booked into that
        period instead of the original's (needed when the original period
        is locked). `voucher_date` and `description` default to the
        original's date and `Correction of voucher …`.
        """
        # Get original voucher
        original = VoucherRepository.get(original_voucher_id)
        if not original:
            raise ValueError("Original voucher not found")

        target_period_id = period_id_override or original.period_id

        # The fiscal year of the target period; the number is set at posting
        period_row = db.execute(
            "SELECT fiscal_year_id FROM periods WHERE id = ?", (target_period_id,)
        ).fetchone()
        fiscal_year_id = period_row["fiscal_year_id"] if period_row else ""

        # Create new B-series voucher referencing the original
        correction_id = str(uuid.uuid4())

        sql = """
        INSERT INTO vouchers (id, series, date, period_id, fiscal_year_id, description, status, correction_of, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)
        """
        now = datetime.now()
        if description is None:
            description = (
                f"Correction of voucher {original.series}{original.number:06d}"
            )
        if voucher_date is None:
            voucher_date = original.date

        db.execute(
            sql,
            (
                correction_id,
                series,
                voucher_date,
                target_period_id,
                fiscal_year_id,
                description,
                original_voucher_id,
                created_by,
                now,
            ),
        )
        if _commit:
            db.commit()

        return Voucher(
            id=correction_id,
            series=VoucherSeries(series),
            number=None,
            date=voucher_date,
            period_id=target_period_id,
            description=description,
            status=VoucherStatus.DRAFT,
            fiscal_year_id=fiscal_year_id,
            correction_of=original_voucher_id,
            created_at=now,
            created_by=created_by,
        )

    @staticmethod
    def delete_draft(voucher_id: str, _commit: bool = True) -> bool:
        """Delete draft voucher (before posting).

        `_commit=False` lets a caller replace a draft inside its own
        transaction (`DraftService.propose`, SPEC-flode-verifikationer §6.2).
        """
        voucher = VoucherRepository.get(voucher_id)
        if not voucher or voucher.is_posted():
            raise ValueError("Can only delete draft vouchers")

        # Delete rows
        db.execute("DELETE FROM voucher_rows WHERE voucher_id = ?", (voucher_id,))
        # Delete voucher
        db.execute("DELETE FROM vouchers WHERE id = ?", (voucher_id,))
        if _commit:
            db.commit()
        return True

    @staticmethod
    def clear_rows(voucher_id: str) -> bool:
        """Clear all rows from a draft voucher."""
        db.execute("DELETE FROM voucher_rows WHERE voucher_id = ?", (voucher_id,))
        db.commit()
        return True

    @staticmethod
    def update_description(
        voucher_id: str, description: str, _commit: bool = True
    ) -> None:
        """Update voucher description."""
        db.execute(
            "UPDATE vouchers SET description = ? WHERE id = ?",
            (description, voucher_id),
        )
        if _commit:
            db.commit()

    @staticmethod
    def replace_rows(
        voucher_id: str,
        rows_data: List[Dict],
        _commit: bool = True,
    ) -> List[VoucherRow]:
        """Replace all rows on a voucher (delete + re-insert)."""
        db.execute("DELETE FROM voucher_rows WHERE voucher_id = ?", (voucher_id,))
        new_rows = []
        now = datetime.now()
        for rd in rows_data:
            row_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO voucher_rows
                   (id, voucher_id, account_code, debit, credit, description, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    row_id,
                    voucher_id,
                    rd["account"],
                    rd.get("debit", 0),
                    rd.get("credit", 0),
                    rd.get("description"),
                    now,
                ),
            )
            new_rows.append(
                VoucherRow(
                    id=row_id,
                    voucher_id=voucher_id,
                    account_code=rd["account"],
                    debit=rd.get("debit", 0),
                    credit=rd.get("credit", 0),
                    description=rd.get("description"),
                    created_at=now,
                )
            )
        if _commit:
            db.commit()
        return new_rows
