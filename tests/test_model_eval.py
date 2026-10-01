"""The scoring in `scripts/model_eval.py`: what counts as the same booking."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "model_eval", Path(__file__).resolve().parent.parent / "scripts" / "model_eval.py"
)
model_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(model_eval)


def _rows(*triples):
    return [{"account": a, "debit": d, "credit": c} for a, d, c in triples]


EXPECTED = {
    "date": "2026-02-03",
    "rows": _rows(("6212", 22000, 0), ("2640", 5500, 0), ("1930", 0, 27500)),
}


def test_same_net_per_account_and_date_is_correct_whatever_the_row_split():
    booked = {
        "date": "2026-02-03",
        "rows": _rows(
            ("2640", 5500, 0),
            ("6212", 12000, 0),
            ("6212", 10000, 0),
            ("1930", 0, 27500),
        ),
    }
    assert model_eval._score(EXPECTED, booked) == "correct"


def test_right_rows_on_another_date():
    booked = {"date": "2026-02-04", "rows": EXPECTED["rows"]}
    assert model_eval._score(EXPECTED, booked) == "right_rows_wrong_date"


def test_a_missing_expected_date_is_not_scored():
    booked = {"date": "2026-02-04", "rows": EXPECTED["rows"]}
    assert model_eval._score({**EXPECTED, "date": None}, booked) == "correct"


def test_same_accounts_other_amounts():
    booked = {
        "date": "2026-02-03",
        "rows": _rows(("6212", 27500, 0), ("2640", 0, 0), ("1930", 0, 27500)),
    }
    # 2640 nets to zero, so it is not among the accounts at all: wrong.
    assert model_eval._score(EXPECTED, booked) == "wrong"
    booked["rows"] = _rows(("6212", 21000, 0), ("2640", 6500, 0), ("1930", 0, 27500))
    assert model_eval._score(EXPECTED, booked) == "right_accounts_wrong_amounts"


def test_no_booking():
    assert model_eval._score(EXPECTED, None) == "no_booking"


def test_group_key_keeps_the_kind_and_drops_months_and_amounts():
    assert model_eval._group_key("Lön till tjänsteman maj 52000kr.pdf") == "lön till"
    assert (
        model_eval._group_key("Telefonutgift Fello 275SEK.pdf") == "telefonutgift fello"
    )


def test_amount_tolerance_for_a_receipt_in_foreign_currency():
    expected = {
        "date": "2026-09-04",
        "rows": _rows(("6500", 19800, 0), ("1920", 0, 19800)),
        "amount_tolerance": 0.05,
    }
    near = {"date": "2026-09-04", "rows": _rows(("6500", 20000, 0), ("1920", 0, 20000))}
    far = {"date": "2026-09-04", "rows": _rows(("6500", 22000, 0), ("1920", 0, 22000))}
    assert model_eval._score(expected, near) == "correct"
    assert model_eval._score(expected, far) == "right_accounts_wrong_amounts"
    assert model_eval._score({**expected, "amount_tolerance": 0}, near) == (
        "right_accounts_wrong_amounts"
    )
