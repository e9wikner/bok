-- Migration 050: lönebeskedet lagras som underlag.
--
-- A payslip's PDF is stored when the payslip is generated: rendered once,
-- written under the intake directory and kept byte for byte (BFL 7 kap.:
-- räkenskapsinformation is kept as it was drawn up, never re-rendered).
-- When the salary is booked, or afterwards against a voucher that already
-- books it, the stored file becomes an intake source linked to the voucher
-- as underlag, next to the bank transaction.
--
--   pdf_path         the file, relative to the intake directory
--   pdf_sha256       its hash
--   intake_source_id the intake source the file became when it was linked
--
-- Each is written once. The triggers refuse to change or clear a value that
-- is set; a wrong link is undone by an unlink row, as for any underlag
-- (migration 035), never by editing the payslip.

ALTER TABLE payslips ADD COLUMN pdf_path TEXT;
ALTER TABLE payslips ADD COLUMN pdf_sha256 TEXT;
ALTER TABLE payslips ADD COLUMN intake_source_id TEXT REFERENCES intake_sources(id);

CREATE TRIGGER IF NOT EXISTS payslips_pdf_written_once
BEFORE UPDATE OF pdf_path, pdf_sha256 ON payslips
WHEN OLD.pdf_sha256 IS NOT NULL
 AND (NEW.pdf_sha256 IS NOT OLD.pdf_sha256 OR NEW.pdf_path IS NOT OLD.pdf_path)
BEGIN
    SELECT RAISE(ABORT, 'payslip_pdf_immutable');
END;

CREATE TRIGGER IF NOT EXISTS payslips_intake_source_written_once
BEFORE UPDATE OF intake_source_id ON payslips
WHEN OLD.intake_source_id IS NOT NULL
 AND NEW.intake_source_id IS NOT OLD.intake_source_id
BEGIN
    SELECT RAISE(ABORT, 'payslip_intake_source_immutable');
END;
