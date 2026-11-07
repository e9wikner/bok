"""Bankavstämning: kontoutdragets saldo mot bokföringens samma dag.

domain/statement_balance.py läser saldot ur de två exportformat som stöds,
services/bank_reconciliation.py jämför det med huvudboken.
"""

from datetime import date

import pytest

from domain.statement_balance import StatementBalance, statement_balance
from tests.test_statement_match import (  # noqa: F401  (fixtures)
    _import,
    _post,
    bank_input_dir,
    books,
)

LF = (
    '"Kontonummer";"Kontonamn";"";"Saldo";"Tillgängligt belopp"\n'
    '"90225892210";"1930";"";"180 097,14";"180 097,14"\n'
    "\n"
    '"Bokföringsdatum";"Transaktionsdatum";"Transaktionstyp";"Meddelande";"Belopp"\n'
    '"2026-11-03";"2026-11-03";"Autogiro";"Lysa Spar";"-53,00"\n'
    '"2026-10-29";"2026-10-29";"Autogiro";"Lysa Spar";"-10 000,00"\n'
)

SKV = (
    '"Testbolaget AB";"556677-8899";"";""\n'
    '"";"";"";""\n'
    '"";"Ingående saldo 2026-01-01";"";"39 039"\n'
    '"2026-01-03";"Intäktsränta";"15";"39 054"\n'
    '"";"Utgående saldo 2026-11-05";"";"71 111"\n'
)


class TestSaldot:
    def test_lansforsakringar_saldo_galler_senaste_bokforingsdagen(self):
        assert statement_balance(LF) == StatementBalance(date(2026, 11, 3), 18_009_714)

    def test_skattekontots_utgaende_saldo(self):
        assert statement_balance(SKV) == StatementBalance(date(2026, 11, 5), 7_111_100)

    def test_utan_saldo_inget_saldo(self):
        assert statement_balance("Datum;Belopp;Text\n2026-01-15;-300000,00;X\n") is None


@pytest.fixture
def opening(books, fiscal_year):  # noqa: F811
    """1930 börjar året på 10 000 kr."""
    from db.database import db

    db.execute(
        "INSERT INTO opening_balances (fiscal_year_id, account_code, amount, updated_by) "
        "VALUES (?, '1930', 1000000, 'test')",
        (fiscal_year.id,),
    )
    db.commit()
    return books


def _avstamning():
    from services.bank_reconciliation import BankReconciliationService

    return BankReconciliationService().latest()


def test_differensen_ar_det_som_inte_ar_bokfort(opening):
    _import(
        "1930",
        '"Kontonummer";"Kontonamn";"";"Saldo"\n"1";"1930";"";"9 500,00"\n\n'
        '"Bokföringsdatum";"Transaktionsdatum";"Transaktionstyp";"Meddelande";"Belopp"\n'
        '"2026-03-10";"2026-03-10";"Betalning";"Avgift";"-500,00"\n',
    )
    [r] = _avstamning()
    assert (r.account_code, r.day) == ("1930", date(2026, 3, 10))
    assert (r.statement_balance_ore, r.ledger_balance_ore) == (950_000, 1_000_000)
    assert r.difference_ore == -50_000

    _post(
        opening,
        date(2026, 3, 10),
        "Avgift",
        [
            {"account": "6570", "debit": 50_000, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 50_000},
        ],
    )
    [r] = _avstamning()
    assert r.difference_ore == 0


def test_bokslutet_varnar_for_differensen(opening, fiscal_year):
    from services.bokslut import BokslutService

    _import(
        "1930",
        '"Kontonummer";"Kontonamn";"";"Saldo"\n"1";"1930";"";"9 500,00"\n\n'
        '"Bokföringsdatum";"Transaktionsdatum";"Transaktionstyp";"Meddelande";"Belopp"\n'
        '"2026-03-10";"2026-03-10";"Betalning";"Avgift";"-500,00"\n',
    )
    service = BokslutService()
    [k] = [k for k in service._bank_checks(service._fiscal_year(fiscal_year.id))]
    assert k["niva"] == "varning"
    assert "differens -500 kr" in k["text"]
