"""Which accounts an account statement (kontoutdrag) is underlag for.

A voucher whose event is a movement on a bank account or the tax account
-- a transfer between own accounts, a tax-account debit or interest, a bank
fee, a customer payment -- has the statement as its underlag: the
statement row *is* the external document. A transfer 1930 -> 1630 touches
two such accounts and needs a transaction on each statement.

Purchases do not: a voucher with input VAT (2640-2649) needs its invoice or
receipt, whatever the bank says, so a statement never covers it.

The repository turns these into SQL (`repositories/voucher_repo.py`); the
matching service uses the Python helpers.
"""

#: Skattekonto (BAS 1630) and the cash and bank accounts (1900-1989).
STATEMENT_ACCOUNT_SINGLES = ("1630",)
STATEMENT_ACCOUNT_RANGE = ("1900", "1989")

#: Ingående moms. A voucher with a row here is a purchase.
INPUT_VAT_RANGE = ("2640", "2649")


def _in_range(code: str, bounds: tuple[str, str]) -> bool:
    return len(code) == 4 and bounds[0] <= code <= bounds[1]


def is_statement_account(code: str) -> bool:
    """Whether a statement for *code* can be a voucher's underlag."""
    return code in STATEMENT_ACCOUNT_SINGLES or _in_range(code, STATEMENT_ACCOUNT_RANGE)


def is_input_vat_account(code: str) -> bool:
    return _in_range(code, INPUT_VAT_RANGE)
