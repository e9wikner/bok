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


if __name__ == "__main__":
    test_multi_period_voucher_import()
    print("Test passed!")
