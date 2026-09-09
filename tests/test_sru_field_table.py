"""Guards on the canonical INK2R field table (domain/sru_fields.py).

Issues #25, #30 and #44 were all the same defect: the SRU export and the
on-screen declaration each kept their own idea of which BAS accounts belong to
which SRU field code, and the two drifted apart — in #44 by a whole row, so
Leverantörsskulder was filed under the code for Skatteskulder. The table is now
a single source; these tests make a future drift fail here instead of in a tax
return.

The expected values below are transcribed from BAS "Kopplingstabell
Inkomstdeklaration 2" (BAS 2023 accounts):
https://www.bas.se/wp-content/uploads/2024/11/INK2_P1-231002_241119.xlsx
"""

import pytest

from domain.sru_fields import (
    COST_FIELDS,
    CREDIT_FIELDS,
    INK2R_ROWS,
    ROWS_BY_FIELD,
    default_account_mappings,
    field_labels,
)
from services.ink2_declaration import INK2R_SECTIONS
from services.sru_export import DEFAULT_SRU_MAPPINGS


# The four codes issue #44 found shifted by one row, plus their neighbours.
SKATTEVERKET_LIABILITY_CODES = {
    "7365": "Leverantörsskulder",
    "7366": "Växelskulder",
    "7367": "Skulder till koncern-, intresse- och gemensamt styrda företag",
    "7368": "Skatteskulder",
    "7369": "Skulder till övriga företag som det finns ett ägarintresse i och övriga skulder",
    "7370": "Upplupna kostnader och förutbetalda intäkter",
}


class TestFieldCodeMeanings:
    """Field codes must mean what Skatteverket says they mean."""

    @pytest.mark.parametrize("code,label", sorted(SKATTEVERKET_LIABILITY_CODES.items()))
    def test_liability_codes_match_skatteverket(self, code, label):
        assert field_labels()[code] == label

    def test_supplier_debt_accounts_map_to_7365(self):
        """2440 Leverantörsskulder is 7365, not 7368 (issue #44)."""
        assert DEFAULT_SRU_MAPPINGS["7365"] == list(range(2440, 2450))

    def test_tax_debt_accounts_map_to_7368(self):
        """The whole 25xx group is Skatteskulder, code 7368."""
        assert DEFAULT_SRU_MAPPINGS["7368"] == list(range(2500, 2600))

    def test_accrued_costs_map_to_7370(self):
        assert DEFAULT_SRU_MAPPINGS["7370"] == list(range(2900, 3000))

    def test_common_accounts_land_on_their_bas_row(self):
        account_to_field = {
            "1510": "7251",  # Kundfordringar
            "1930": "7281",  # Företagskonto
            "2081": "7301",  # Aktiekapital -> bundet eget kapital
            "2099": "7302",  # Årets resultat -> fritt eget kapital
            "2440": "7365",  # Leverantörsskulder
            # BAS keeps 25xx alone under Skatteskulder; moms and personalskatt
            # are Övriga skulder on the form, however tax-like they read.
            "2610": "7369",  # Utgående moms
            "2710": "7369",  # Personalskatt
            "2910": "7370",  # Upplupna löner
            "3011": "7410",  # Nettoomsättning
            "6540": "7513",  # Övriga externa kostnader
            "7010": "7514",  # Personalkostnader
            "8410": "7522",  # Räntekostnader
            "8910": "7528",  # Skatt på årets resultat
        }
        for account, expected_field in account_to_field.items():
            found = [
                key
                for key, numbers in DEFAULT_SRU_MAPPINGS.items()
                if int(account) in numbers
            ]
            assert found == [expected_field], f"{account} mapped to {found}"


class TestTableConsistency:
    """The two modules that consume the table must agree on every code."""

    def test_declaration_rows_use_the_exported_field_codes(self):
        """Every INK2R row on screen names codes the export can produce."""
        declared = {
            row.code: row.sru_fields
            for section in INK2R_SECTIONS
            for row in section.rows
        }
        for row in INK2R_ROWS:
            assert declared[row.row] == row.field_codes

    def test_declaration_labels_match_field_labels(self):
        """A row's label on screen is the label the export writes for its code."""
        labels = field_labels()
        for section in INK2R_SECTIONS:
            for row in section.rows:
                if not row.sru_fields:
                    continue
                primary = row.sru_fields[0]
                if primary in ROWS_BY_FIELD:
                    assert row.label == labels[primary]

    def test_no_account_is_claimed_by_two_fields(self):
        """Overlapping ranges would silently drop one field's accounts."""
        seen: dict[int, str] = {}
        for key, numbers in default_account_mappings().items():
            for number in numbers:
                assert number not in seen, f"{number}: {seen.get(number)} and {key}"
                seen[number] = key

    def test_every_field_has_a_label(self):
        labels = field_labels()
        for row in INK2R_ROWS:
            for code in row.field_codes:
                assert labels.get(code), f"{code} has no label"

    def test_credit_and_cost_fields_are_disjoint(self):
        """A field is negated or made absolute, never both."""
        assert not (CREDIT_FIELDS & COST_FIELDS)

    def test_row_numbers_are_unique(self):
        rows = [row.row for row in INK2R_ROWS]
        assert len(rows) == len(set(rows))
