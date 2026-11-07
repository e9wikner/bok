-- Migration 040: a statement link can be undone, and the undoing stays
--
-- The server links a statement transaction to a posted voucher on its own
-- when exactly one voucher has the same amount on the account the same day
-- (services/statement_match.py). Two unrelated events can meet that. 036
-- made the links append-only with no way back but reversing a voucher that
-- was right. This follows 035 (intake links): the link row stays, and a row
-- in `voucher_bank_transaction_unlinks` says it no longer holds -- who, why.
-- The *current* link of a transaction is the one without such a row;
-- `current_voucher_bank_transactions` is that set, and everything that asks
-- "is this linked?" reads it.
--
-- `voucher_bank_transactions` had `UNIQUE(bank_transaction_id)` and
-- `UNIQUE(voucher_id, bank_transaction_id)`. An unlinked transaction must be
-- able to carry a new link -- to another voucher or, after a mistaken
-- unlink, the same one -- while the old row stays, and SQLite cannot drop a
-- UNIQUE with ALTER, so the table is rebuilt (the order of 021, 027 and 035:
-- foreign keys OFF, create, copy, drop, rename). The guard moves to a
-- trigger: at most one current link per transaction. No other table's
-- foreign key names `voucher_bank_transactions`. Its triggers from 036 go
-- with the old table and are created again below.
--
-- `voucher_bank_inputs` (the statement file <-> voucher) is left as it is.
-- Its readers count a file link only while one of the file's transactions
-- has a current link to the voucher, or none of them ever had one.

PRAGMA foreign_keys = OFF;

BEGIN;

CREATE TABLE voucher_bank_transactions_new (
    id TEXT PRIMARY KEY,
    voucher_id TEXT NOT NULL,
    bank_transaction_id TEXT NOT NULL,
    linked_by TEXT NOT NULL,
    linked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id),
    FOREIGN KEY(bank_transaction_id) REFERENCES bank_transactions(id)
);

INSERT INTO voucher_bank_transactions_new
    (id, voucher_id, bank_transaction_id, linked_by, linked_at)
SELECT id, voucher_id, bank_transaction_id, linked_by, linked_at
FROM voucher_bank_transactions;

DROP TABLE voucher_bank_transactions;
ALTER TABLE voucher_bank_transactions_new RENAME TO voucher_bank_transactions;

CREATE INDEX idx_voucher_bank_tx_voucher ON voucher_bank_transactions(voucher_id);
CREATE INDEX idx_voucher_bank_tx_transaction ON voucher_bank_transactions(bank_transaction_id);

CREATE TABLE voucher_bank_transaction_unlinks (
    link_id              TEXT PRIMARY KEY NOT NULL REFERENCES voucher_bank_transactions(id),
    bank_transaction_id  TEXT NOT NULL REFERENCES bank_transactions(id),
    voucher_id           TEXT NOT NULL REFERENCES vouchers(id),
    reason               TEXT NOT NULL,
    actor                TEXT NOT NULL,
    thread_id            TEXT REFERENCES threads(id),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(reason)) > 0)
);

CREATE INDEX idx_voucher_bank_tx_unlinks_transaction
    ON voucher_bank_transaction_unlinks(bank_transaction_id);

CREATE VIEW current_voucher_bank_transactions AS
SELECT vbt.*
FROM voucher_bank_transactions vbt
WHERE NOT EXISTS (
    SELECT 1 FROM voucher_bank_transaction_unlinks u WHERE u.link_id = vbt.id
);

-- The old UNIQUE(bank_transaction_id), for current links.
CREATE TRIGGER one_current_link_per_bank_transaction
BEFORE INSERT ON voucher_bank_transactions
WHEN EXISTS (
    SELECT 1 FROM current_voucher_bank_transactions c
    WHERE c.bank_transaction_id = NEW.bank_transaction_id
)
BEGIN
    SELECT RAISE(ABORT, 'bank transaction is already linked');
END;

-- An unlink names the link it undoes, and that link's transaction and voucher.
CREATE TRIGGER bank_unlink_matches_link
BEFORE INSERT ON voucher_bank_transaction_unlinks
WHEN NOT EXISTS (
    SELECT 1 FROM voucher_bank_transactions vbt
    WHERE vbt.id = NEW.link_id
      AND vbt.bank_transaction_id = NEW.bank_transaction_id
      AND vbt.voucher_id = NEW.voucher_id
)
BEGIN
    SELECT RAISE(ABORT, 'unlink does not match its link');
END;

CREATE TRIGGER prevent_update_voucher_bank_transactions
BEFORE UPDATE ON voucher_bank_transactions
BEGIN SELECT RAISE(ABORT, 'voucher bank transaction links are append-only'); END;

CREATE TRIGGER prevent_delete_voucher_bank_transactions
BEFORE DELETE ON voucher_bank_transactions
BEGIN SELECT RAISE(ABORT, 'voucher bank transaction links are append-only'); END;

CREATE TRIGGER prevent_update_voucher_bank_transaction_unlinks
BEFORE UPDATE ON voucher_bank_transaction_unlinks
BEGIN SELECT RAISE(ABORT, 'voucher bank transaction unlinks are append-only'); END;

CREATE TRIGGER prevent_delete_voucher_bank_transaction_unlinks
BEFORE DELETE ON voucher_bank_transaction_unlinks
BEGIN SELECT RAISE(ABORT, 'voucher bank transaction unlinks are append-only'); END;

INSERT OR IGNORE INTO schema_version (version) VALUES (39);

COMMIT;

PRAGMA foreign_keys = ON;
