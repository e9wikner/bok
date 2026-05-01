"""Test för att verifiera SIE4 import med multipla perioder.

Detta test verifierar att fixen för auto-skapande av perioder fungerar,
så att verifikat från flera månader importeras korrekt.
"""

import pytest
from datetime import date
from services.sie4_import import SIE4Parser


def test_multi_period_voucher_import():
    """Testa import av verifikat över flera perioder utan att perioder finns."""
    
    # SIE4-fil med verifikat från 3 olika månader
    sie4_content = """#FLAGGA 0
#FORMAT PC8
#GEN "Test" 20260115
#PROGRAM "Test" 1.0
#FNAMN "Test AB"
#FORGN 5591234567
#RAR 0 20260101 20261231
#KPTYP EUBAS97

#KONTO 1930 "Företagskonto"
#KONTO 3010 "Försäljning"
#KONTO 5010 "Hyra"

#VER A 1 20260115 "Försäljning jan"
{
#TRANS 1930 {} 10000 20260115
#TRANS 3010 {} -10000 20260115
}

#VER A 2 20260220 "Försäljning feb" 
{
#TRANS 1930 {} 15000 20260220
#TRANS 3010 {} -15000 20260220
}

#VER A 3 20260310 "Försäljning mar"
{
#TRANS 1930 {} 20000 20260310
#TRANS 3010 {} -20000 20260310
}
"""

    parser = SIE4Parser()
    data = parser.parse_content(sie4_content)
    
    # Verifiera att alla 3 verifikat parsades
    assert len(data.vouchers) == 3, f"Expected 3 vouchers, got {len(data.vouchers)}"
    
    # Verifiera att verifikaten har olika datum (olika perioder)
    dates = [v.date for v in data.vouchers]
    assert len(set(dates)) == 3, "Vouchers should have 3 different dates"
    
    print(f"✅ Successfully parsed {len(data.vouchers)} vouchers across {len(set(dates))} different months")


def test_pc8_import_preserves_swedish_characters(tmp_path):
    """Testa att CP437/PC8-kodade SIE-filer inte får mojibake i svensk text."""
    expected = "Återföring Småföretagsförsäkring Länsförsäkringar"
    sie4_content = f"""#FLAGGA 0
#FORMAT PC8
#GEN "Test" 20260129
#PROGRAM "Test" 1.0
#FNAMN "Test AB"
#FORGN 5591234567
#RAR 0 20260101 20261231
#KPTYP EUBAS97
#KONTO 1700 "Förutbetalda kostnader och upplupna intäkter"
#KONTO 6300 "Företagsförsäkringar"
#VER A 165 20260129 "{expected}"
{{
#TRANS 1700 {{}} -8013 20260129
#TRANS 6300 {{}} 8013 20260129
}}
"""
    file_path = tmp_path / "pc8.se"
    file_path.write_bytes(sie4_content.encode("cp437"))

    parser = SIE4Parser()
    data = parser.parse_file(str(file_path))

    assert data.accounts[0].name == "Förutbetalda kostnader och upplupna intäkter"
    assert data.vouchers[0].description == expected
    assert not any(0x80 <= ord(char) <= 0x9F for char in data.vouchers[0].description)


def test_encoding_sanity_check_finds_c1_mojibake():
    """Testa att importvalideringen hittar text som redan är feldekodad."""
    sie4_content = """#FLAGGA 0
#FORMAT PC8
#GEN "Test" 20260129
#PROGRAM "Test" 1.0
#FNAMN "Test AB"
#FORGN 5591234567
#RAR 0 20260101 20261231
#KPTYP EUBAS97
#KONTO 1700 "Förutbetalda kostnader"
#KONTO 6300 "Företagsförsäkringar"
#VER A 165 20260129 "\x8fterf\x94ring Sm\x86f\x94retagsf\x94rs\x84kring"
{
#TRANS 1700 {} -8013 20260129
#TRANS 6300 {} 8013 20260129
}
"""
    parser = SIE4Parser()
    data = parser.parse_content(sie4_content)
    issues = SIE4Parser.find_encoding_issues(data)

    assert len(issues) == 1
    assert "voucher A165" in issues[0]


if __name__ == "__main__":
    test_multi_period_voucher_import()
    print("Test passed!")
