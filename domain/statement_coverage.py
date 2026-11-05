"""Which accounts an account statement (kontoutdrag) is underlag for.

A voucher whose event is a movement on a bank account or the tax account
-- a transfer between own accounts, a tax-account debit or interest, a bank
fee, a customer payment -- has the statement as its underlag: the
statement row *is* the external document. A transfer 1930 -> 1630 touches
two such accounts and needs a transaction on each statement.

An account is covered when the linked transactions on it add up to the
voucher's net on it. Usually that is one transaction. A voucher with several
rows on the account can be covered by one transaction per row: a month's
arbetsgivardeklaration is one voucher, and the tax account debits the
withheld tax and the employer fees as two transactions (`covers`).

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


def is_bank_account(code: str) -> bool:
    """Whether *code* is a cash or bank account (not the tax account)."""
    return _in_range(code, STATEMENT_ACCOUNT_RANGE)


def is_input_vat_account(code: str) -> bool:
    return _in_range(code, INPUT_VAT_RANGE)


def covers(amount_ore: int, remaining_ore: int, row_amounts: list[int]) -> bool:
    """Whether a transaction of *amount_ore* can be underlag for a voucher
    on an account where *remaining_ore* of the voucher's net is not covered
    by a linked transaction yet, *row_amounts* being the voucher's rows on
    that account (debit positive, like money in).

    Either the transaction is all that is left, or it is one of several rows
    and leaves some of the account still to cover -- never more than is
    left, and never the other way."""
    if amount_ore == 0 or remaining_ore == 0:
        return False
    if amount_ore == remaining_ore:
        return True
    return (
        len(row_amounts) > 1
        and amount_ore in row_amounts
        and (amount_ore > 0) == (remaining_ore > 0)
        and abs(amount_ore) < abs(remaining_ore)
    )
