from services.ink2_declaration import INK2DeclarationService, INK2R_SECTIONS
from services.sru_export import SRUDeclaration, SRUFieldValue


def test_declaration_row_sums_sru_fields_and_filters_zero_source_accounts():
    declaration = SRUDeclaration(
        fiscal_year_id="fy-1",
        company_org_number="5566778899",
        company_name="Test AB",
        fiscal_year_start="20250101",
        fiscal_year_end="20251231",
        fields={
            "7416": SRUFieldValue(
                field_number="7416",
                description="Intäkt",
                value=100,
                source_accounts=["8310"],
                source_account_values=[
                    {"account": "8310", "name": "Ränta", "value": 100},
                    {"account": "8311", "name": "Tom ränta", "value": 0},
                ],
            ),
            "7520": SRUFieldValue(
                field_number="7520",
                description="Kostnad",
                value=40,
                source_accounts=["8220"],
                source_account_values=[
                    {"account": "8220", "name": "Avgift", "value": 40},
                ],
            ),
        },
    )

    service = INK2DeclarationService()
    definition = next(section for section in INK2R_SECTIONS if section.title == "Resultaträkning")
    section = service._build_section(definition, declaration, accounting_result=0, taxable_result=0)
    row = next(row for row in section["rows"] if row["code"] == "3.15")

    assert row["value"] == 140
    assert row["source_accounts"] == [
        {"account": "8310", "name": "Ränta", "value": 100},
        {"account": "8220", "name": "Avgift", "value": 40},
    ]
