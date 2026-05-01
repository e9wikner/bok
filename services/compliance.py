"""BFL Compliance checker - proactive warnings for regulatory violations.

Checks for:
1. Bokföringslagen (BFL) requirements
   - Bokföringsskyldighet (5 kap 1§): Transactions must be booked
   - Varaktighet (5 kap 6§): Posted vouchers must not be modified
   - Tidskrav: Transactions should be booked within reasonable time
   - Periodavslut: Periods should be closed after deadline
   
2. Mervärdesskattelag (ML) - VAT compliance
   - Momsdeklaration deadlines (monthly/quarterly)
   - VAT calculation accuracy
   
3. General best practices
   - Unbalanced trial balance
   - Missing voucher sequences
   - Large unbooked transaction backlogs
"""

import uuid
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass

from db.database import db


@dataclass
class ComplianceIssue:
    """A compliance issue/warning."""
    id: str
    check_type: str
    severity: str  # info, warning, error, critical
    status: str  # open, acknowledged, resolved, false_positive
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    title: str = ""
    description: str = ""
    recommendation: str = ""
    deadline: Optional[date] = None
    created_at: datetime = None


class ComplianceService:
    """Proactive BFL compliance checking."""

    def run_all_checks(self) -> Dict:
        """Run all compliance checks and return summary."""
        issues = []
        
        issues.extend(self._check_booking_timeliness())
        issues.extend(self._check_period_closing())
        issues.extend(self._check_voucher_sequence())
        issues.extend(self._check_trial_balance())
        issues.extend(self._check_vat_deadlines())
        issues.extend(self._check_unbooked_bank_transactions())
        issues.extend(self._check_missing_attachments())
        issues.extend(self._check_large_amounts())
        
        # Save new issues
        new_count = 0
        for issue in issues:
            if not self._issue_exists(issue.check_type, issue.entity_type, issue.entity_id):
                self._save_issue(issue)
                new_count += 1
        
        # Summary
        all_open = self.get_open_issues()
        return {
            "checks_run": 8,
            "new_issues": new_count,
            "total_open": len(all_open),
            "by_severity": {
                "critical": len([i for i in all_open if i.severity == "critical"]),
                "error": len([i for i in all_open if i.severity == "error"]),
                "warning": len([i for i in all_open if i.severity == "warning"]),
                "info": len([i for i in all_open if i.severity == "info"]),
            },
            "issues": [
                {
                    "id": i.id,
                    "type": i.check_type,
                    "severity": i.severity,
                    "title": i.title,
                    "description": i.description,
                    "recommendation": i.recommendation,
                    "deadline": i.deadline.isoformat() if i.deadline else None,
                }
                for i in all_open
            ],
        }

    def get_open_issues(self, severity: Optional[str] = None) -> List[ComplianceIssue]:
        """Get all open compliance issues."""
        sql = "SELECT * FROM compliance_checks WHERE status = 'open'"
        params = []
        if severity:
            sql += " AND severity = ?"
            params.append(severity)
        sql += " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END"
        
        rows = db.execute(sql, tuple(params)).fetchall()
        return [self._row_to_issue(r) for r in rows]

    def acknowledge_issue(self, issue_id: str) -> None:
        """Mark an issue as acknowledged."""
        db.execute(
            "UPDATE compliance_checks SET status = 'acknowledged' WHERE id = ?",
            (issue_id,)
        )
        db.commit()

    def resolve_issue(self, issue_id: str, resolved_by: str = "system") -> None:
        """Mark an issue as resolved."""
        db.execute(
            "UPDATE compliance_checks SET status = 'resolved', resolved_at = ?, resolved_by = ? WHERE id = ?",
            (datetime.now().isoformat(), resolved_by, issue_id)
        )
        db.commit()

    def mark_false_positive(self, issue_id: str) -> None:
        """Mark an issue as false positive."""
        db.execute(
            "UPDATE compliance_checks SET status = 'false_positive', resolved_at = ? WHERE id = ?",
            (datetime.now().isoformat(), issue_id)
        )
        db.commit()

    # --- Individual checks ---

    def _check_booking_timeliness(self) -> List[ComplianceIssue]:
        """BFL 5 kap 2§: Kontanta transaktioner ska bokföras senast påföljande arbetsdag.
        Övriga transaktioner ska bokföras så snart det kan ske.
        
        Check for bank transactions older than 5 business days that haven't been booked.
        """
        issues = []
        cutoff = (date.today() - timedelta(days=7)).isoformat()
        
        rows = db.execute("""
            SELECT COUNT(*) as cnt, MIN(transaction_date) as oldest
            FROM bank_transactions 
            WHERE status IN ('pending', 'categorized')
            AND transaction_date < ?
        """, (cutoff,)).fetchone()
        
        if rows and rows["cnt"] > 0:
            issues.append(ComplianceIssue(
                id=str(uuid.uuid4()),
                check_type="voucher_timeliness",
                severity="warning" if rows["cnt"] < 10 else "error",
                status="open",
                entity_type="transaction",
                title=f"📋 {rows['cnt']} transaktioner väntar på bokföring",
                description=(
                    f"Det finns {rows['cnt']} banktransaktioner som inte bokförts. "
                    f"Äldsta från {rows['oldest']}. "
                    f"Enligt BFL 5 kap 2§ ska transaktioner bokföras löpande."
                ),
                recommendation="Kör automatisk kategorisering och bokföring, eller granska manuellt.",
                deadline=date.today() + timedelta(days=3),
            ))
        
        return issues

    def _check_period_closing(self) -> List[ComplianceIssue]:
        """Check for periods that should have been closed.
        
        Best practice: Close periods within 45 days after period end.
        BFL requirement: Yearly report within 6 months after fiscal year end.
        """
        issues = []
        today = date.today()
        
        rows = db.execute("""
            SELECT id, year, month, end_date 
            FROM periods 
            WHERE locked = 0 
            AND end_date < ?
            ORDER BY end_date ASC
        """, ((today - timedelta(days=45)).isoformat(),)).fetchall()
        
        for row in rows:
            end_date = date.fromisoformat(row["end_date"])
            days_overdue = (today - end_date).days
            
            severity = "info"
            if days_overdue > 180:
                severity = "critical"
            elif days_overdue > 90:
                severity = "error"
            elif days_overdue > 45:
                severity = "warning"
            
            issues.append(ComplianceIssue(
                id=str(uuid.uuid4()),
                check_type="period_closing",
                severity=severity,
                status="open",
                entity_type="period",
                entity_id=row["id"],
                title=f"📅 Period {row['year']}-{row['month']:02d} ej stängd ({days_overdue} dagar)",
                description=(
                    f"Period {row['year']}-{row['month']:02d} (slutdatum {row['end_date']}) "
                    f"är fortfarande öppen, {days_overdue} dagar efter periodslut. "
                    f"Enligt god redovisningssed bör perioder stängas inom rimlig tid."
                ),
                recommendation=f"Stäng perioden via POST /api/v1/periods/{row['id']}/lock",
            ))
        
        return issues

    def _check_voucher_sequence(self) -> List[ComplianceIssue]:
        """BFL 5 kap 6§: Verifikationer ska numreras löpande.
        
        Check for gaps in voucher numbering.
        """
        issues = []
        
        rows = db.execute("""
            SELECT series, MIN(number) as min_num, MAX(number) as max_num, COUNT(*) as cnt
            FROM vouchers 
            WHERE status = 'posted'
            GROUP BY series
        """).fetchall()
        
        for row in rows:
            expected = row["max_num"] - row["min_num"] + 1
            actual = row["cnt"]
            if actual < expected:
                gaps = expected - actual
                issues.append(ComplianceIssue(
                    id=str(uuid.uuid4()),
                    check_type="voucher_sequence",
                    severity="warning",
                    status="open",
                    entity_type="voucher",
                    title=f"🔢 Luckor i verifikationsnumrering ({row['series']}-serien)",
                    description=(
                        f"Det finns {gaps} luckor i {row['series']}-serien "
                        f"(nummer {row['min_num']}-{row['max_num']}, {actual} verifikationer). "
                        f"Enligt BFL 5 kap 6§ ska verifikationer numreras löpande."
                    ),
                    recommendation="Kontrollera om verifikationer saknas eller om det finns raderingar.",
                ))
        
        return issues

    def _check_trial_balance(self) -> List[ComplianceIssue]:
        """Check that the trial balance is balanced (debit = credit)."""
        issues = []
        
        row = db.execute("""
            SELECT 
                SUM(debit) as total_debit, 
                SUM(credit) as total_credit
            FROM voucher_rows vr
            JOIN vouchers v ON v.id = vr.voucher_id
            WHERE v.status = 'posted'
        """).fetchone()
        
        if row and row["total_debit"] is not None:
            diff = abs((row["total_debit"] or 0) - (row["total_credit"] or 0))
            if diff > 0:
                issues.append(ComplianceIssue(
                    id=str(uuid.uuid4()),
                    check_type="balance_check",
                    severity="critical",
                    status="open",
                    title=f"⚖️ Råbalansen balanserar INTE! Differens: {diff/100:.2f} SEK",
                    description=(
                        f"Total debet: {(row['total_debit'] or 0)/100:.2f} SEK, "
                        f"Total kredit: {(row['total_credit'] or 0)/100:.2f} SEK. "
                        f"Differens: {diff/100:.2f} SEK. "
                        f"Detta bryter mot grundläggande bokföringsprinciper."
                    ),
                    recommendation="Undersök alla verifikationer och hitta den obalanserade posten.",
                ))
        
        return issues

    def _check_vat_deadlines(self) -> List[ComplianceIssue]:
        """Check VAT declaration deadlines.
        
        Swedish VAT deadlines:
        - Monthly: Due 26th of month+1 (or 12th for Dec → Feb 26)
        - Quarterly: Due 26th of month after quarter end
        - Yearly: Due with annual tax return
        """
        issues = []
        today = date.today()
        
        # Check if previous month's VAT should have been declared
        if today.day > 26:
            # Previous month's deadline has passed
            prev_month = today.month - 1 if today.month > 1 else 12
            prev_year = today.year if today.month > 1 else today.year - 1
            
            # Check if we have any VAT transactions for that period
            vat_row = db.execute("""
                SELECT COUNT(*) as cnt
                FROM voucher_rows vr
                JOIN vouchers v ON v.id = vr.voucher_id
                JOIN periods p ON p.id = v.period_id
                WHERE v.status = 'posted'
                AND p.year = ? AND p.month = ?
                AND vr.account_code IN ('2610', '2620', '2630', '2640')
            """, (prev_year, prev_month)).fetchone()
            
            if vat_row and vat_row["cnt"] > 0:
                # Check if a VAT report exists (simplified check)
                issues.append(ComplianceIssue(
                    id=str(uuid.uuid4()),
                    check_type="vat_deadline",
                    severity="warning",
                    status="open",
                    title=f"🧾 Momsdeklaration {prev_year}-{prev_month:02d} - kontrollera deadline",
                    description=(
                        f"Det finns momstransaktioner för {prev_year}-{prev_month:02d}. "
                        f"Momsdeklaration ska normalt lämnas senast den 26:e i månaden efter. "
                        f"Kontrollera att deklaration har lämnats till Skatteverket."
                    ),
                    recommendation="Generera momsrapport och lämna deklaration via Skatteverket.",
                    deadline=date(prev_year if prev_month < 12 else prev_year + 1,
                                  prev_month + 1 if prev_month < 12 else 1, 26),
                ))
        
        return issues

    def _check_unbooked_bank_transactions(self) -> List[ComplianceIssue]:
        """Check for large backlogs of unbooked bank transactions."""
        issues = []
        
        try:
            row = db.execute("""
                SELECT COUNT(*) as cnt
                FROM bank_transactions 
                WHERE status = 'pending'
            """).fetchone()
            
            if row and row["cnt"] > 20:
                issues.append(ComplianceIssue(
                    id=str(uuid.uuid4()),
                    check_type="unbooked_backlog",
                    severity="warning",
                    status="open",
                    title=f"📦 {row['cnt']} obokförda banktransaktioner",
                    description=(
                        f"Det finns {row['cnt']} banktransaktioner som väntar på bokföring. "
                        f"En stor backlog kan tyda på att bokföringen inte sköts löpande."
                    ),
                    recommendation="Granska och bokför importerade banktransaktioner innan backloggen växer.",
                ))
        except Exception:
            pass  # Table might not exist yet
        
        return issues

    def _check_missing_attachments(self) -> List[ComplianceIssue]:
        """BFL 5 kap 6-7§: Verifikationer bör ha underlag.
        
        Check for posted vouchers without attachments (not strictly required
        for all vouchers, but good practice).
        """
        issues = []
        
        # Count vouchers over a certain amount without attachments
        try:
            row = db.execute("""
                SELECT COUNT(DISTINCT v.id) as cnt
                FROM vouchers v
                LEFT JOIN voucher_attachments va ON va.voucher_id = v.id
                WHERE v.status = 'posted'
                AND va.id IS NULL
                AND EXISTS (
                    SELECT 1 FROM voucher_rows vr 
                    WHERE vr.voucher_id = v.id 
                    AND (vr.debit > 50000 OR vr.credit > 50000)
                )
            """).fetchone()
            
            if row and row["cnt"] > 0:
                issues.append(ComplianceIssue(
                    id=str(uuid.uuid4()),
                    check_type="missing_attachments",
                    severity="info",
                    status="open",
                    title=f"📎 {row['cnt']} verifikationer >500 SEK saknar underlag",
                    description=(
                        f"Det finns {row['cnt']} bokförda verifikationer med belopp över 500 SEK "
                        f"som saknar bifogat underlag (kvitto/faktura). "
                        f"Enligt BFL bör verifikationer styrkas med underlag."
                    ),
                    recommendation="Bifoga kvitton eller fakturor till relevanta verifikationer.",
                ))
        except Exception:
            pass  # attachments table might not exist
        
        return issues

    def _check_large_amounts(self) -> List[ComplianceIssue]:
        """Flag unusually large transactions for review."""
        issues = []
        
        # Find vouchers with amounts > 100,000 SEK in last 30 days
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        
        rows = db.execute("""
            SELECT v.id, v.number, v.series, v.date, v.description,
                   MAX(vr.debit, vr.credit) as max_amount
            FROM vouchers v
            JOIN voucher_rows vr ON vr.voucher_id = v.id
            WHERE v.status = 'posted'
            AND v.date >= ?
            AND (vr.debit > 10000000 OR vr.credit > 10000000)
            GROUP BY v.id
            ORDER BY max_amount DESC
            LIMIT 5
        """, (cutoff,)).fetchall()
        
        for row in rows:
            issues.append(ComplianceIssue(
                id=str(uuid.uuid4()),
                check_type="large_amount",
                severity="info",
                status="open",
                entity_type="voucher",
                entity_id=row["id"],
                title=f"💰 Stor transaktion: {row['series']}{row['number']} ({row['max_amount']/100:.0f} SEK)",
                description=(
                    f"Verifikation {row['series']}{row['number']} ({row['date']}) "
                    f"innehåller belopp på {row['max_amount']/100:.2f} SEK. "
                    f"Beskrivning: {row['description']}"
                ),
                recommendation="Kontrollera att beloppet och konteringen stämmer.",
            ))
        
        return issues

    # --- Helpers ---

    def _issue_exists(self, check_type: str, entity_type: Optional[str], entity_id: Optional[str]) -> bool:
        """Check if an open issue already exists for this check."""
        sql = "SELECT id FROM compliance_checks WHERE check_type = ? AND status IN ('open', 'acknowledged')"
        params = [check_type]
        
        if entity_id:
            sql += " AND entity_id = ?"
            params.append(entity_id)
        
        return db.execute(sql, tuple(params)).fetchone() is not None

    def _save_issue(self, issue: ComplianceIssue) -> None:
        """Save a compliance issue to the database."""
        db.execute(
            """INSERT INTO compliance_checks 
               (id, check_type, severity, status, entity_type, entity_id,
                title, description, recommendation, deadline)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (issue.id, issue.check_type, issue.severity, issue.status,
             issue.entity_type, issue.entity_id, issue.title, issue.description,
             issue.recommendation,
             issue.deadline.isoformat() if issue.deadline else None)
        )
        db.commit()

    def _row_to_issue(self, row) -> ComplianceIssue:
        return ComplianceIssue(
            id=row["id"],
            check_type=row["check_type"],
            severity=row["severity"],
            status=row["status"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            title=row["title"],
            description=row["description"],
            recommendation=row["recommendation"],
            deadline=date.fromisoformat(row["deadline"]) if row["deadline"] else None,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )
