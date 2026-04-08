"""SRU Export Service for Swedish INK2 Tax Declaration.

SRU = Skatteverkets Rapporterings-Utbyte
Generates INFO.SRU and BLANKETTER.SRU files for electronic tax filing.
"""

import io
import zipfile
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from db.database import get_db


# Default BAS2026 account to SRU field mappings (fallback when no SIE4 SRU data)
DEFAULT_SRU_MAPPINGS = {
    # Anläggningstillgångar (Balance Sheet - Assets)
    "7416": list(range(1000, 1100)),  # Immateriella anläggningstillgångar
    "7417": list(range(1100, 1300)),  # Materiella anläggningstillgångar
    "7522": list(range(1300, 1400)),  # Finansiella anläggningstillgångar
    
    # Omsättningstillgångar
    "7251": list(range(1400, 1500)),  # Varulager
    "7261": list(range(1500, 1600)),  # Kundfordringar
    "7263": list(range(1600, 1700)),  # Övriga fordringar
    "7271": list(range(1700, 1800)),  # Förutbetalda kostnader
    "7281": list(range(1900, 2000)),  # Likvida medel
    
    # Eget kapital och skulder
    "7301": list(range(2000, 2100)),  # Eget kapital
    "7302": [2091, 2099],             # Resultat
    "7321": list(range(2100, 2200)),  # Obeskattade reserver
    "7350": list(range(2200, 2300)),  # Avsättningar
    "7365": list(range(2300, 2400)),  # Långfristiga skulder
    "7368": list(range(2400, 2500)),  # Leverantörsskulder
    "7369": list(range(2500, 2600)),  # Skatteskulder
    "7370": list(range(2600, 3000)),  # Övriga kortfristiga skulder
    
    # Resultaträkning
    "7410": list(range(3000, 3800)),  # Nettoomsättning
    "7413": list(range(3900, 4000)),  # Övriga rörelseintäkter
    "7511": list(range(4000, 5000)),  # Material och varor
    "7513": list(range(5000, 7000)),  # Övriga externa kostnader
    "7514": list(range(7000, 7700)),  # Personalkostnader
    "7515": list(range(7800, 8000)),  # Avskrivningar
    "7520": list(range(8000, 8200)),  # Övriga rörelsekostnader
    "7525": list(range(8200, 8400)),  # Resultat från övriga värdepapper
    "7528": list(range(8400, 8500)),  # Övriga finansiella intäkter
}


@dataclass
class SRUFieldValue:
    """Value for a single SRU field."""
    field_number: str
    description: str
    value: int  # In SEK (not öre)
    source_accounts: List[str]  # Which accounts contributed


@dataclass
class SRUDeclaration:
    """Complete SRU declaration data."""
    fiscal_year_id: str
    company_org_number: str
    company_name: str
    fiscal_year_start: str  # YYYYMMDD
    fiscal_year_end: str    # YYYYMMDD
    fields: Dict[str, SRUFieldValue]
    
    def get_field(self, field_number: str) -> Optional[SRUFieldValue]:
        """Get value for a specific field."""
        return self.fields.get(field_number)
    
    def get_field_value(self, field_number: str) -> int:
        """Get numeric value for a field (0 if not found)."""
        field = self.fields.get(field_number)
        return field.value if field else 0


class SRUExportService:
    """Service for generating SRU export files."""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def get_sru_mappings(self, fiscal_year_id: str) -> Dict[str, str]:
        """
        Get SRU mappings for a fiscal year.
        
        Returns {account_code: sru_field} dictionary.
        First checks database for imported SIE4 mappings,
        then falls back to default BAS2026 mappings.
        """
        db = get_db()
        mappings = {}
        
        # First, get mappings from database (imported from SIE4)
        cursor = db.execute(
            """
            SELECT a.code, m.sru_field
            FROM account_sru_mappings m
            JOIN accounts a ON m.account_id = a.id
            WHERE m.fiscal_year_id = ?
            """,
            (fiscal_year_id,)
        )
        
        db_mappings = {row["code"]: row["sru_field"] for row in cursor.fetchall()}
        
        if db_mappings:
            mappings.update(db_mappings)
            self.warnings.append(
                f"Using {len(db_mappings)} SRU mappings from imported SIE4 file"
            )
        
        # Fill gaps with default BAS2026 mappings
        default_count = 0
        for sru_field, account_ranges in DEFAULT_SRU_MAPPINGS.items():
            for account_num in account_ranges:
                account_code = str(account_num)
                if account_code not in mappings:
                    mappings[account_code] = sru_field
                    default_count += 1
        
        if default_count > 0:
            self.warnings.append(
                f"Using {default_count} default BAS2026 SRU mappings"
            )
        
        return mappings
    
    def calculate_account_balances(
        self, fiscal_year_id: str
    ) -> Dict[str, Dict]:
        """
        Calculate closing balances for all accounts in fiscal year.
        
        Returns {account_code: {id, name, balance, account_type}}.
        Balance is in öre (positive = debit, negative = credit).
        """
        db = get_db()
        
        # Get all accounts with their voucher row totals
        cursor = db.execute(
            """
            SELECT 
                a.id,
                a.code,
                a.name,
                a.account_type,
                COALESCE(SUM(CASE 
                    WHEN vr.debit > 0 THEN vr.debit
                    WHEN vr.credit > 0 THEN -vr.credit
                    ELSE 0
                END), 0) as balance
            FROM accounts a
            LEFT JOIN voucher_rows vr ON a.id = vr.account_id
            LEFT JOIN vouchers v ON vr.voucher_id = v.id
            LEFT JOIN periods p ON v.period_id = p.id
            WHERE p.fiscal_year_id = ? OR p.fiscal_year_id IS NULL
            GROUP BY a.id, a.code, a.name, a.account_type
            ORDER BY a.code
            """,
            (fiscal_year_id,)
        )
        
        accounts = {}
        for row in cursor.fetchall():
            accounts[row["code"]] = {
                "id": row["id"],
                "name": row["name"],
                "balance": row["balance"],  # In öre
                "account_type": row["account_type"],
            }
        
        return accounts
    
    def calculate_sru_fields(self, fiscal_year_id: str) -> SRUDeclaration:
        """
        Calculate all SRU field values for a fiscal year.
        
        This is the main calculation method that aggregates account balances
        into the SRU fields needed for INK2 declaration.
        """
        self.errors = []
        self.warnings = []
        
        db = get_db()
        
        # Get fiscal year info
        fiscal_year = db.execute(
            "SELECT * FROM fiscal_years WHERE id = ?",
            (fiscal_year_id,)
        ).fetchone()
        
        if not fiscal_year:
            raise ValueError(f"Fiscal year {fiscal_year_id} not found")
        
        # Get company info
        company = db.execute(
            "SELECT * FROM company_info ORDER BY id LIMIT 1"
        ).fetchone()
        
        if not company:
            raise ValueError("Company info not found")
        
        # Get SRU mappings
        sru_mappings = self.get_sru_mappings(fiscal_year_id)
        
        # Get account balances
        account_balances = self.calculate_account_balances(fiscal_year_id)
        
        # Calculate SRU fields
        fields = {}
        
        # Group accounts by SRU field and sum balances
        field_balances: Dict[str, List[Dict]] = {}
        for account_code, account_data in account_balances.items():
            sru_field = sru_mappings.get(account_code)
            if sru_field:
                if sru_field not in field_balances:
                    field_balances[sru_field] = []
                field_balances[sru_field].append({
                    "code": account_code,
                    "name": account_data["name"],
                    "balance": account_data["balance"],
                })
        
        # Create SRU field values
        field_descriptions = self._get_field_descriptions()
        
        for sru_field, accounts in field_balances.items():
            total_balance = sum(a["balance"] for a in accounts)
            # Convert from öre to SEK (round to nearest)
            value_sek = round(total_balance / 100)
            
            fields[sru_field] = SRUFieldValue(
                field_number=sru_field,
                description=field_descriptions.get(sru_field, "Okänd fältkod"),
                value=value_sek,
                source_accounts=[a["code"] for a in accounts],
            )
        
        # Calculate derived fields
        self._calculate_derived_fields(fields)
        
        # Validate balance sheet
        self._validate_balance_sheet(fields)
        
        return SRUDeclaration(
            fiscal_year_id=fiscal_year_id,
            company_org_number=company["org_number"].replace("-", ""),
            company_name=company["name"],
            fiscal_year_start=fiscal_year["start_date"].replace("-", ""),
            fiscal_year_end=fiscal_year["end_date"].replace("-", ""),
            fields=fields,
        )
    
    def _calculate_derived_fields(self, fields: Dict[str, SRUFieldValue]):
        """Calculate derived/summary fields from base fields."""
        # Summa anläggningstillgångar (7420)
        anlaggning = sum(
            fields[f].value for f in ["7416", "7417", "7522"]
            if f in fields
        )
        if anlaggning != 0:
            fields["7420"] = SRUFieldValue(
                field_number="7420",
                description="Summa anläggningstillgångar",
                value=anlaggning,
                source_accounts=["7416", "7417", "7522"],
            )
        
        # Summa omsättningstillgångar (räkna samman 7251, 7261, 7263, 7271, 7281)
        omsattning = sum(
            fields[f].value for f in ["7251", "7261", "7263", "7271", "7281"]
            if f in fields
        )
        
        # Summa tillgångar (7450)
        tillgangar = anlaggning + omsattning
        if tillgangar != 0:
            fields["7450"] = SRUFieldValue(
                field_number="7450",
                description="Summa tillgångar",
                value=tillgangar,
                source_accounts=["7420", "7251", "7261", "7263", "7271", "7281"],
            )
        
        # Summa eget kapital (7301 + 7302)
        eget_kapital = sum(
            fields[f].value for f in ["7301", "7302"]
            if f in fields
        )
        
        # Summa obeskattade reserver (7321)
        obeskattade = fields.get("7321", SRUFieldValue("7321", "", 0, [])).value
        
        # Summa avsättningar (7350)
        avsattningar = fields.get("7350", SRUFieldValue("7350", "", 0, [])).value
        
        # Summa skulder (7365 + 7368 + 7369 + 7370)
        skulder = sum(
            fields[f].value for f in ["7365", "7368", "7369", "7370"]
            if f in fields
        )
        
        # Summa eget kapital och skulder (7550)
        ek_skulder = eget_kapital + obeskattade + avsattningar + skulder
        if ek_skulder != 0:
            fields["7550"] = SRUFieldValue(
                field_number="7550",
                description="Summa eget kapital och skulder",
                value=ek_skulder,
                source_accounts=["7301", "7302", "7321", "7350", "7365", "7368", "7369", "7370"],
            )
        
        # Skillnad mellan tillgångar och skulder/EK (7670) - ska vara 0
        skillnad = tillgangar - ek_skulder
        fields["7670"] = SRUFieldValue(
            field_number="7670",
            description="Skillnad mellan tillgångar och skulder/EK",
            value=skillnad,
            source_accounts=["7450", "7550"],
        )
        
        # Resultaträkning - beräknade fält
        intakter = fields.get("7410", SRUFieldValue("7410", "", 0, [])).value
        ovriga_intakter = fields.get("7413", SRUFieldValue("7413", "", 0, [])).value
        material = fields.get("7511", SRUFieldValue("7511", "", 0, [])).value
        externa = fields.get("7513", SRUFieldValue("7513", "", 0, [])).value
        personal = fields.get("7514", SRUFieldValue("7514", "", 0, [])).value
        avskrivningar = fields.get("7515", SRUFieldValue("7515", "", 0, [])).value
        ovriga_kostnader = fields.get("7520", SRUFieldValue("7520", "", 0, [])).value
        finansiella_intakter = fields.get("7528", SRUFieldValue("7528", "", 0, [])).value
        
        # Rörelseresultat (approximation)
        rorelseresultat = intakter + ovriga_intakter - material - externa - personal - avskrivningar - ovriga_kostnader
        if rorelseresultat != 0:
            fields["7368"] = SRUFieldValue(
                field_number="7368",
                description="Rörelseresultat",
                value=rorelseresultat,
                source_accounts=["7410", "7413", "7511", "7513", "7514", "7515", "7520"],
            )
        
        # Resultat efter finansiella poster
        resultat_efter_finansiella = rorelseresultat + finansiella_intakter
        if resultat_efter_finansiella != 0:
            fields["7410"] = SRUFieldValue(
                field_number="7410",
                description="Resultat efter finansiella poster",
                value=resultat_efter_finansiella,
                source_accounts=["7368", "7528"],
            )
        
        # Skatt på årets resultat (22% om vinst)
        if resultat_efter_finansiella > 0:
            skatt = round(resultat_efter_finansiella * 0.22)
            fields["7513"] = SRUFieldValue(
                field_number="7513",
                description="Skatt på årets resultat",
                value=skatt,
                source_accounts=["7410"],
            )
            
            # Årets resultat
            arets_resultat = resultat_efter_finansiella - skatt
            fields["7514"] = SRUFieldValue(
                field_number="7514",
                description="Årets resultat",
                value=arets_resultat,
                source_accounts=["7410", "7513"],
            )
    
    def _validate_balance_sheet(self, fields: Dict[str, SRUFieldValue]):
        """Validate that balance sheet balances (assets = liabilities + equity)."""
        tillgangar = fields.get("7450", SRUFieldValue("7450", "", 0, [])).value
        ek_skulder = fields.get("7550", SRUFieldValue("7550", "", 0, [])).value
        skillnad = fields.get("7670", SRUFieldValue("7670", "", 0, [])).value
        
        if skillnad != 0:
            self.warnings.append(
                f"BALANSPOSTER STÄMMER INTE: Tillgångar ({tillgangar}) ≠ EK+Skulder ({ek_skulder}). "
                f"Skillnad: {skillnad} SEK"
            )
        else:
            self.warnings.append(
                f"Balansräkning OK: Tillgångar = EK+Skulder = {tillgangar} SEK"
            )
    
    def _get_field_descriptions(self) -> Dict[str, str]:
        """Get human-readable descriptions for SRU fields."""
        return {
            # Balansräkning - Tillgångar
            "7416": "Immateriella anläggningstillgångar",
            "7417": "Materiella anläggningstillgångar",
            "7522": "Finansiella anläggningstillgångar",
            "7420": "Summa anläggningstillgångar",
            "7251": "Varulager",
            "7261": "Kundfordringar",
            "7263": "Övriga fordringar",
            "7271": "Förutbetalda kostnader",
            "7281": "Likvida medel",
            "7450": "Summa tillgångar",
            
            # Balansräkning - Eget kapital och skulder
            "7301": "Eget kapital",
            "7302": "Balanserat resultat/Årets resultat",
            "7321": "Obeskattade reserver",
            "7350": "Avsättningar",
            "7365": "Långfristiga skulder",
            "7368": "Leverantörsskulder",
            "7369": "Skatteskulder",
            "7370": "Övriga kortfristiga skulder",
            "7550": "Summa eget kapital och skulder",
            "7670": "Skillnad mellan tillgångar och skulder/EK",
            
            # Resultaträkning
            "7410": "Nettoomsättning",
            "7413": "Övriga rörelseintäkter",
            "7511": "Material och varor",
            "7513": "Övriga externa kostnader",
            "7514": "Personalkostnader",
            "7515": "Av- och nedskrivningar",
            "7520": "Övriga rörelsekostnader",
            "7528": "Övriga finansiella intäkter",
            "7368": "Rörelseresultat",
            "7514_duplicate": "Årets resultat",
        }
    
    def generate_info_sru(self, declaration: SRUDeclaration) -> str:
        """
        Generate INFO.SRU file content.
        
        This file contains metadata about the declaration.
        """
        lines = [
            "#DATABESKRIVNING_START",
            "#PRODUKT SRU",
            f"#SKAPAD {datetime.now().strftime('%Y%m%d %H%M%S')}",
            "#PROGRAM BOKAI 1.0",
            "#FILNAMN BLANKETTER.SRU",
            "#DATABESKRIVNING_SLUT",
            "#MEDIELEV_START",
            f"#ORGNR {declaration.company_org_number}",
            f"#NAMN {declaration.company_name}",
            "#MEDIELEV_SLUT",
        ]
        
        return "\r\n".join(lines) + "\r\n"
    
    def generate_blanketter_sru(self, declaration: SRUDeclaration) -> str:
        """
        Generate BLANKETTER.SRU file content.
        
        This file contains the actual declaration data.
        """
        lines = []
        timestamp = datetime.now().strftime("%Y%m%d %H%M%S")
        
        # INK2R - Huvudblankett (Resultaträkning)
        lines.extend([
            "#BLANKETT INK2R-2025P4",
            f"#IDENTITET {declaration.company_org_number} {timestamp}",
            "#SYSTEMINFO BOKAI 1.0",
        ])
        
        # Add fiscal year dates
        lines.append(f"#UPPGIFT 7011 {declaration.fiscal_year_start}")
        lines.append(f"#UPPGIFT 7012 {declaration.fiscal_year_end}")
        
        # Add all field values (sorted by field number)
        for field_number in sorted(declaration.fields.keys()):
            field = declaration.fields[field_number]
            if field.value != 0:  # Only include non-zero values
                lines.append(f"#UPPGIFT {field_number} {field.value}")
        
        lines.append("#BLANKETTSLUT")
        
        # INK2S - Särskild blankett (Balansräkning)
        lines.extend([
            "#BLANKETT INK2S-2025P4",
            f"#IDENTITET {declaration.company_org_number} {timestamp}",
            "#SYSTEMINFO BOKAI 1.0",
        ])
        
        # Add balance sheet fields to INK2S
        balance_fields = ["7650", "7651", "7653", "7754", "7654", "7670"]
        for field_number in balance_fields:
            if field_number in declaration.fields:
                field = declaration.fields[field_number]
                if field.value != 0:
                    lines.append(f"#UPPGIFT {field_number} {field.value}")
        
        lines.append("#BLANKETTSLUT")
        lines.append("#FIL_SLUT")
        
        return "\r\n".join(lines) + "\r\n"
    
    def export_sru_zip(
        self, fiscal_year_id: str
    ) -> Tuple[bytes, str, List[str], List[str]]:
        """
        Generate complete SRU export as ZIP file.
        
        Returns: (zip_bytes, filename, errors, warnings)
        """
        self.errors = []
        self.warnings = []
        
        try:
            # Calculate declaration data
            declaration = self.calculate_sru_fields(fiscal_year_id)
            
            # Generate files
            info_sru = self.generate_info_sru(declaration)
            blanketter_sru = self.generate_blanketter_sru(declaration)
            
            # Create ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.writestr("INFO.SRU", info_sru.encode('utf-8-sig'))  # UTF-8 with BOM
                zip_file.writestr("BLANKETTER.SRU", blanketter_sru.encode('utf-8-sig'))
            
            zip_bytes = zip_buffer.getvalue()
            
            # Generate filename
            safe_company_name = "".join(
                c for c in declaration.company_name 
                if c.isalnum() or c in (' ', '-', '_')
            ).strip().replace(' ', '_')
            year = declaration.fiscal_year_end[:4]
            filename = f"{safe_company_name}_{year}_INK2_SRU.zip"
            
            return zip_bytes, filename, self.errors, self.warnings
            
        except Exception as e:
            self.errors.append(f"Export failed: {str(e)}")
            return b"", "", self.errors, self.warnings


# Convenience function for API usage
def export_sru_for_fiscal_year(fiscal_year_id: str) -> Tuple[bytes, str, List[str], List[str]]:
    """
    Export SRU files for a fiscal year.
    
    Returns: (zip_bytes, filename, errors, warnings)
    """
    service = SRUExportService()
    return service.export_sru_zip(fiscal_year_id)
