"""Presentation model for INK2 declarations.

This module converts calculated SRU fields into the web-facing INK2/INK2R/INK2S
structure. The frontend should render this data, not recreate tax declaration
logic locally.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from services.sru_export import SRUDeclaration, SRUExportService, SRUFieldValue


@dataclass(frozen=True)
class DeclarationRowDefinition:
    code: str
    label: str
    sru_fields: tuple[str, ...] = ()
    sign: Optional[str] = None
    value_key: Optional[str] = None
    note: Optional[str] = None


@dataclass(frozen=True)
class DeclarationSectionDefinition:
    title: str
    rows: tuple[DeclarationRowDefinition, ...]


TABS = [
    {"id": "ink2", "label": "INK2", "description": "Huvudblankett"},
    {"id": "ink2r", "label": "INK2R", "description": "Räkenskapsschema"},
    {"id": "ink2s", "label": "INK2S", "description": "Skattemässiga justeringar"},
]


INK2_SECTIONS = (
    DeclarationSectionDefinition(
        "Underlag för inkomstskatt",
        (
            DeclarationRowDefinition("1.1", "Överskott av näringsverksamhet", value_key="taxable_result_positive"),
            DeclarationRowDefinition("1.2", "Underskott av näringsverksamhet", value_key="taxable_result_negative"),
            DeclarationRowDefinition("1.3", "Underskott som inte redovisas i p. 1.2, koncernbidrags- och fusionsspärrat underskott"),
        ),
    ),
    DeclarationSectionDefinition(
        "Underlag för särskild löneskatt",
        (
            DeclarationRowDefinition("1.4", "Underlag för särskild löneskatt på pensionskostnader"),
            DeclarationRowDefinition("1.5", "Negativt underlag för särskild löneskatt på pensionskostnader"),
        ),
    ),
    DeclarationSectionDefinition(
        "Underlag för avkastningsskatt",
        (
            DeclarationRowDefinition("1.6", "Underlag för avkastningsskatt 15 %. Försäkringsföretag m.fl. Avsatt till pensioner"),
            DeclarationRowDefinition("1.7", "Underlag för avkastningsskatt 30 %. Försäkringsföretag m.fl. Utländska kapitalförsäkringar"),
        ),
    ),
    DeclarationSectionDefinition(
        "Underlag för fastighetsavgift",
        (
            DeclarationRowDefinition("1.8", "Småhus, hel avgift"),
            DeclarationRowDefinition("1.8", "Småhus, halv avgift"),
            DeclarationRowDefinition("1.9", "Hyreshus, bostäder, hel avgift"),
            DeclarationRowDefinition("1.9", "Hyreshus, bostäder, halv avgift"),
        ),
    ),
    DeclarationSectionDefinition(
        "Underlag för fastighetsskatt",
        (
            DeclarationRowDefinition("1.10", "Småhus/ägarlägenhet: tomtmark, byggnad under uppförande"),
            DeclarationRowDefinition("1.11", "Hyreshus: tomtmark, bostäder under uppförande"),
            DeclarationRowDefinition("1.12", "Hyreshus: lokaler"),
            DeclarationRowDefinition("1.13", "Industri/elproduktionsenhet, värmekraftverk (utom vindkraftverk)"),
            DeclarationRowDefinition("1.14", "Elproduktionsenhet, vattenkraftverk"),
            DeclarationRowDefinition("1.15", "Elproduktionsenhet, vindkraftverk"),
        ),
    ),
)


INK2R_SECTIONS = (
    DeclarationSectionDefinition(
        "Tillgångar / Anläggningstillgångar",
        (
            DeclarationRowDefinition("2.1", "Koncessioner, patent, licenser, varumärken, hyresrätter, goodwill och liknande rättigheter", ("7201",)),
            DeclarationRowDefinition("2.2", "Förskott avseende immateriella anläggningstillgångar", ("7202",)),
            DeclarationRowDefinition("2.3", "Byggnader och mark", ("7214",)),
            DeclarationRowDefinition("2.4", "Maskiner, inventarier och övriga materiella anläggningstillgångar", ("7215",)),
            DeclarationRowDefinition("2.5", "Förbättringsutgifter på annans fastighet", ("7216",)),
            DeclarationRowDefinition("2.6", "Pågående nyanläggningar och förskott avseende materiella anläggningstillgångar", ("7217",)),
            DeclarationRowDefinition("2.7", "Andelar i koncernföretag", ("7230",)),
            DeclarationRowDefinition("2.8", "Andelar i intresseföretag och gemensamt styrda företag", ("7231",)),
            DeclarationRowDefinition("2.9", "Ägarintresse i övriga företag och andra långfristiga värdepappersinnehav", ("7233",)),
            DeclarationRowDefinition("2.10", "Fordringar hos koncern-, intresse- och gemensamt styrda företag", ("7232",)),
            DeclarationRowDefinition("2.11", "Lån till delägare eller närstående", ("7234",)),
            DeclarationRowDefinition("2.12", "Fordringar hos övriga företag som det finns ett ägarintresse i och andra långfristiga fordringar", ("7235",)),
        ),
    ),
    DeclarationSectionDefinition(
        "Omsättningstillgångar",
        (
            DeclarationRowDefinition("2.13", "Råvaror och förnödenheter", ("7241",)),
            DeclarationRowDefinition("2.14", "Varor under tillverkning", ("7242",)),
            DeclarationRowDefinition("2.15", "Färdiga varor och handelsvaror", ("7243",)),
            DeclarationRowDefinition("2.16", "Övriga lagertillgångar", ("7244",)),
            DeclarationRowDefinition("2.17", "Pågående arbeten för annans räkning", ("7245",)),
            DeclarationRowDefinition("2.18", "Förskott till leverantörer", ("7246",)),
            DeclarationRowDefinition("2.19", "Kundfordringar", ("7251",)),
            DeclarationRowDefinition("2.20", "Fordringar hos koncern-, intresse- och gemensamt styrda företag", ("7252",)),
            DeclarationRowDefinition("2.21", "Fordringar hos övriga företag som det finns ett ägarintresse i och övriga fordringar", ("7261",)),
            DeclarationRowDefinition("2.22", "Upparbetad men ej fakturerad intäkt", ("7262",)),
            DeclarationRowDefinition("2.23", "Förutbetalda kostnader och upplupna intäkter", ("7263",)),
            DeclarationRowDefinition("2.24", "Andelar i koncernföretag", ("7270",)),
            DeclarationRowDefinition("2.25", "Övriga kortfristiga placeringar", ("7271",)),
            DeclarationRowDefinition("2.26", "Kassa, bank och redovisningsmedel", ("7281",)),
        ),
    ),
    DeclarationSectionDefinition("Eget kapital", (DeclarationRowDefinition("2.27", "Bundet eget kapital", ("7301",)), DeclarationRowDefinition("2.28", "Fritt eget kapital", ("7302",)))),
    DeclarationSectionDefinition(
        "Obeskattade reserver och avsättningar",
        (
            DeclarationRowDefinition("2.29", "Periodiseringsfonder", ("7321",)),
            DeclarationRowDefinition("2.30", "Ackumulerade överavskrivningar", ("7322",)),
            DeclarationRowDefinition("2.31", "Övriga obeskattade reserver", ("7323",)),
            DeclarationRowDefinition("2.32", "Avsättningar för pensioner och liknande förpliktelser enligt lagen (1967:531) om tryggande av pensionsutfästelser m.m.", ("7331",)),
            DeclarationRowDefinition("2.33", "Övriga avsättningar för pensioner och liknande förpliktelser", ("7332",)),
            DeclarationRowDefinition("2.34", "Övriga avsättningar", ("7333",)),
        ),
    ),
    DeclarationSectionDefinition(
        "Skulder",
        (
            DeclarationRowDefinition("2.35", "Obligationslån", ("7350",)),
            DeclarationRowDefinition("2.36", "Checkräkningskredit", ("7351",)),
            DeclarationRowDefinition("2.37", "Övriga skulder till kreditinstitut", ("7352",)),
            DeclarationRowDefinition("2.38", "Skulder till koncern-, intresse- och gemensamt styrda företag", ("7353",)),
            DeclarationRowDefinition("2.39", "Skulder till övriga företag som det finns ett ägarintresse i och övriga skulder", ("7354",)),
            DeclarationRowDefinition("2.40", "Checkräkningskredit", ("7360",)),
            DeclarationRowDefinition("2.41", "Övriga skulder till kreditinstitut", ("7361",)),
            DeclarationRowDefinition("2.42", "Förskott från kunder", ("7362",)),
            DeclarationRowDefinition("2.43", "Pågående arbeten för annans räkning", ("7363",)),
            DeclarationRowDefinition("2.44", "Fakturerad men ej upparbetad intäkt", ("7364",)),
            DeclarationRowDefinition("2.45", "Leverantörsskulder", ("7365",)),
            DeclarationRowDefinition("2.46", "Växelskulder", ("7366",)),
            DeclarationRowDefinition("2.47", "Skulder till koncern-, intresse- och gemensamt styrda företag", ("7367",)),
            DeclarationRowDefinition("2.48", "Skulder till övriga företag som det finns ett ägarintresse i och övriga skulder", ("7369",)),
            DeclarationRowDefinition("2.49", "Skatteskulder", ("7368",)),
            DeclarationRowDefinition("2.50", "Upplupna kostnader och förutbetalda intäkter", ("7370",)),
        ),
    ),
    DeclarationSectionDefinition(
        "Resultaträkning",
        (
            DeclarationRowDefinition("3.1", "Nettoomsättning", ("7410",), "+"),
            DeclarationRowDefinition("3.2", "Förändring av lager av produkter i arbete, färdiga varor och pågående arbete för annans räkning", ("7411", "7510"), "+"),
            DeclarationRowDefinition("3.3", "Aktiverat arbete för egen räkning", ("7412",), "+"),
            DeclarationRowDefinition("3.4", "Övriga rörelseintäkter", ("7413",), "+"),
            DeclarationRowDefinition("3.5", "Råvaror och förnödenheter", ("7511",), "-"),
            DeclarationRowDefinition("3.6", "Handelsvaror", ("7512",), "-"),
            DeclarationRowDefinition("3.7", "Övriga externa kostnader", ("7513",), "-"),
            DeclarationRowDefinition("3.8", "Personalkostnader", ("7514",), "-"),
            DeclarationRowDefinition("3.9", "Av- och nedskrivningar av materiella och immateriella anläggningstillgångar", ("7515",), "-"),
            DeclarationRowDefinition("3.10", "Nedskrivningar av omsättningstillgångar utöver normala nedskrivningar", ("7516",), "-"),
            DeclarationRowDefinition("3.11", "Övriga rörelsekostnader", ("7517",), "-"),
            DeclarationRowDefinition("3.12", "Resultat från andelar i koncernföretag", ("7414", "7518"), "+"),
            DeclarationRowDefinition("3.13", "Resultat från andelar i intresseföretag och gemensamt styrda företag", ("7415", "7519"), "+"),
            DeclarationRowDefinition("3.14", "Resultat från övriga företag som det finns ett ägarintresse i", ("7423", "7530"), "+"),
            DeclarationRowDefinition("3.15", "Resultat från övriga finansiella anläggningstillgångar", ("7416", "7520"), "+"),
            DeclarationRowDefinition("3.16", "Övriga ränteintäkter och liknande resultatposter", ("7417",), "+"),
            DeclarationRowDefinition("3.17", "Nedskrivningar av finansiella anläggningstillgångar och kortfristiga placeringar", ("7521",), "-"),
            DeclarationRowDefinition("3.18", "Räntekostnader och liknande resultatposter", ("7522",), "-"),
            DeclarationRowDefinition("3.19", "Lämnade koncernbidrag", ("7524",), "-"),
            DeclarationRowDefinition("3.20", "Mottagna koncernbidrag", ("7419",), "+"),
            DeclarationRowDefinition("3.21", "Återföring av periodiseringsfond", ("7420",), "+"),
            DeclarationRowDefinition("3.22", "Avsättning till periodiseringsfond", ("7525",), "-"),
            DeclarationRowDefinition("3.23", "Förändring av överavskrivningar", ("7421", "7526"), "+"),
            DeclarationRowDefinition("3.24", "Övriga bokslutsdispositioner", ("7422", "7527"), "+"),
            DeclarationRowDefinition("3.25", "Skatt på årets resultat", ("7528",), "-"),
            DeclarationRowDefinition("3.26", "Årets resultat, vinst (flyttas till p. 4.1)", ("7450",), "(+) ="),
            DeclarationRowDefinition("3.27", "Årets resultat, förlust (flyttas till p. 4.2)", ("7550",), "(-) ="),
        ),
    ),
)


INK2S_SECTIONS = (
    DeclarationSectionDefinition(
        "Årets resultat",
        (
            DeclarationRowDefinition("4.1", "Årets resultat, vinst", ("7650",), "+"),
            DeclarationRowDefinition("4.2", "Årets resultat, förlust", sign="-", value_key="accounting_result_negative"),
        ),
    ),
    DeclarationSectionDefinition(
        "Bokförda kostnader och intäkter",
        (
            DeclarationRowDefinition("4.3a", "Bokförda kostnader som inte ska dras av: skatt på årets resultat", ("7651",), "+"),
            DeclarationRowDefinition("4.3b", "Bokförda kostnader som inte ska dras av: nedskrivning av finansiella tillgångar", sign="+"),
            DeclarationRowDefinition("4.3c", "Bokförda kostnader som inte ska dras av: andra bokförda kostnader", ("7653",), "+"),
            DeclarationRowDefinition("4.4a", "Kostnader som ska dras av men som inte ingår i det redovisade resultatet: lämnade koncernbidrag", sign="-"),
            DeclarationRowDefinition("4.4b", "Kostnader som ska dras av men som inte ingår i det redovisade resultatet: andra ej bokförda kostnader", sign="-"),
            DeclarationRowDefinition("4.5a", "Bokförda intäkter som inte ska tas upp: ackordsvinster", sign="-"),
            DeclarationRowDefinition("4.5b", "Bokförda intäkter som inte ska tas upp: utdelning", sign="-"),
            DeclarationRowDefinition("4.5c", "Bokförda intäkter som inte ska tas upp: andra bokförda intäkter", ("7754",), "-"),
            DeclarationRowDefinition("4.6a", "Intäkter som ska tas upp men som inte ingår i det redovisade resultatet: schablonintäkt på kvarvarande periodiseringsfonder", ("7654",), "+"),
            DeclarationRowDefinition("4.6b", "Intäkter som ska tas upp men som inte ingår i det redovisade resultatet: schablonintäkt på investeringsfonder", sign="+"),
            DeclarationRowDefinition("4.6c", "Intäkter som ska tas upp men som inte ingår i det redovisade resultatet: mottagna koncernbidrag", sign="+"),
            DeclarationRowDefinition("4.6d", "Intäkter som ska tas upp men som inte ingår i det redovisade resultatet: intäkt negativ justerad anskaffningsutgift", sign="+"),
            DeclarationRowDefinition("4.6e", "Intäkter som ska tas upp men som inte ingår i det redovisade resultatet: andra ej bokförda intäkter", sign="+"),
        ),
    ),
    DeclarationSectionDefinition(
        "Övriga skattemässiga justeringar",
        (
            DeclarationRowDefinition("4.7a", "Avyttring av delägarrätter: bokförd vinst", sign="-"),
            DeclarationRowDefinition("4.7b", "Avyttring av delägarrätter: bokförd förlust", sign="+"),
            DeclarationRowDefinition("4.7c", "Avyttring av delägarrätter: uppskov med kapitalvinst enligt blankett N4", sign="-"),
            DeclarationRowDefinition("4.7d", "Avyttring av delägarrätter: återfört uppskov av kapitalvinst enligt blankett N4", sign="+"),
            DeclarationRowDefinition("4.7e", "Avyttring av delägarrätter: kapitalvinst för beskattningsåret", sign="+"),
            DeclarationRowDefinition("4.7f", "Avyttring av delägarrätter: kapitalförlust som ska dras av", sign="-"),
            DeclarationRowDefinition("4.8a", "Andel i handelsbolag: bokförd intäkt/vinst", sign="-"),
            DeclarationRowDefinition("4.8b", "Andel i handelsbolag: skattemässigt överskott enligt N3B", sign="+"),
            DeclarationRowDefinition("4.8c", "Andel i handelsbolag: bokförd kostnad/förlust", sign="+"),
            DeclarationRowDefinition("4.8d", "Andel i handelsbolag: skattemässigt underskott enligt N3B", sign="-"),
            DeclarationRowDefinition("4.9", "Skattemässig justering av bokfört resultat för avskrivning på byggnader och annan fast egendom samt vid restvärdesavskrivning", sign="+"),
            DeclarationRowDefinition("4.10", "Skattemässig korrigering av bokfört resultat vid avyttring av näringsfastighet och näringsbostadsrätt", sign="+"),
            DeclarationRowDefinition("4.11", "Skogs-/substansminskningsavdrag", sign="-"),
            DeclarationRowDefinition("4.12", "Återföringar vid avyttring av fastighet", sign="+"),
            DeclarationRowDefinition("4.13", "Andra skattemässiga justeringar av resultatet", sign="+"),
            DeclarationRowDefinition("4.14a", "Underskott: outnyttjat underskott från föregående år", sign="-"),
            DeclarationRowDefinition("4.14b", "Underskott: reduktion av underskott med hänsyn till exempelvis ägarförändring eller ackord", sign="+"),
            DeclarationRowDefinition("4.15", "Överskott (flyttas till p. 1.1)", ("7670",), "(+) ="),
            DeclarationRowDefinition("4.16", "Underskott (flyttas till p. 1.2)", sign="(-) =", value_key="taxable_result_negative"),
        ),
    ),
    DeclarationSectionDefinition(
        "Övriga uppgifter",
        (
            DeclarationRowDefinition("4.17", "Årets begärda och tidigare års medgivna värdeminskningsavdrag på byggnader som finns kvar vid beskattningsårets utgång"),
            DeclarationRowDefinition("4.18", "Årets begärda och tidigare års medgivna värdeminskningsavdrag på markanläggningar som finns kvar vid beskattningsårets utgång"),
            DeclarationRowDefinition("4.19", "Vid restvärdesavskrivning: återförda belopp för av- och nedskrivning, försäljning, utrangering"),
            DeclarationRowDefinition("4.20", "Lån från aktieägare (fysisk person) vid beskattningsårets utgång"),
            DeclarationRowDefinition("4.21", "Pensionskostnader (som ingår i p. 3.8)"),
        ),
    ),
    DeclarationSectionDefinition(
        "Upplysningar om årsredovisningen",
        (
            DeclarationRowDefinition("JA/NEJ", "Uppdragstagare, t.ex. redovisningskonsult, har biträtt vid upprättandet av årsredovisningen"),
            DeclarationRowDefinition("JA/NEJ", "Årsredovisningen har varit föremål för revision"),
        ),
    ),
)


SECTIONS_BY_TAB = {
    "ink2": INK2_SECTIONS,
    "ink2r": INK2R_SECTIONS,
    "ink2s": INK2S_SECTIONS,
}

INCOME_RESULT_FIELDS = ("7410", "7411", "7412", "7413", "7414", "7415", "7423", "7416", "7417", "7419", "7420", "7421", "7422")
EXPENSE_RESULT_FIELDS = ("7510", "7511", "7512", "7513", "7514", "7515", "7516", "7517", "7518", "7519", "7530", "7520", "7521", "7522", "7524", "7525", "7526", "7527", "7528")


class INK2DeclarationService:
    """Build a human-facing INK2 declaration from backend SRU calculations."""

    def build(self, fiscal_year_id: str) -> Dict:
        sru_service = SRUExportService()
        declaration = sru_service.calculate_sru_fields(fiscal_year_id)
        accounting_result = self._accounting_result(declaration)
        taxable_result = declaration.get_field_value("7670") or accounting_result

        return {
            "fiscal_year_id": declaration.fiscal_year_id,
            "company": {
                "org_number": declaration.company_org_number,
                "name": declaration.company_name,
            },
            "fiscal_year": {
                "start": declaration.fiscal_year_start,
                "end": declaration.fiscal_year_end,
            },
            "tabs": TABS,
            "summary": {
                "accounting_result": accounting_result,
                "taxable_result": taxable_result,
                "blankettstruktur": "SKV 2002, INK2/INK2R/INK2S",
            },
            "sections": {
                tab_id: [
                    self._build_section(section, declaration, accounting_result, taxable_result)
                    for section in sections
                ]
                for tab_id, sections in SECTIONS_BY_TAB.items()
            },
            "validation": {
                "errors": sru_service.errors,
                "warnings": sru_service.warnings,
                "is_valid": len(sru_service.errors) == 0,
            },
        }

    def _accounting_result(self, declaration: SRUDeclaration) -> int:
        ink2r_result = declaration.get_field_value("7450") - declaration.get_field_value("7550")
        computed_result = sum(declaration.get_field_value(field) for field in INCOME_RESULT_FIELDS) - sum(
            declaration.get_field_value(field) for field in EXPENSE_RESULT_FIELDS
        )
        return declaration.get_field_value("7650") or ink2r_result or computed_result

    def _build_section(
        self,
        section: DeclarationSectionDefinition,
        declaration: SRUDeclaration,
        accounting_result: int,
        taxable_result: int,
    ) -> Dict:
        return {
            "title": section.title,
            "rows": [
                self._build_row(row, declaration, accounting_result, taxable_result)
                for row in section.rows
            ],
        }

    def _build_row(
        self,
        row: DeclarationRowDefinition,
        declaration: SRUDeclaration,
        accounting_result: int,
        taxable_result: int,
    ) -> Dict:
        value = self._row_value(row, declaration, accounting_result, taxable_result)
        source_accounts = self._source_accounts(row.sru_fields, declaration.fields)

        return {
            "code": row.code,
            "label": row.label,
            "sru_fields": list(row.sru_fields),
            "sign": row.sign,
            "note": row.note,
            "value": value,
            "source_accounts": source_accounts,
        }

    def _row_value(
        self,
        row: DeclarationRowDefinition,
        declaration: SRUDeclaration,
        accounting_result: int,
        taxable_result: int,
    ) -> Optional[int]:
        if row.value_key == "taxable_result_positive":
            return max(taxable_result, 0)
        if row.value_key == "taxable_result_negative":
            return min(taxable_result, 0)
        if row.value_key == "accounting_result_negative":
            return min(accounting_result, 0)
        if row.sru_fields:
            return sum(declaration.get_field_value(field) for field in row.sru_fields)
        return None

    def _source_accounts(
        self,
        sru_fields: tuple[str, ...],
        fields: Dict[str, SRUFieldValue],
    ) -> List[Dict]:
        accounts: List[Dict] = []
        for field_number in sru_fields:
            field = fields.get(field_number)
            if not field:
                continue
            for account in field.source_account_values or []:
                if int(account.get("value", 0)) == 0:
                    continue
                accounts.append(
                    {
                        "account": account["account"],
                        "name": account.get("name", ""),
                        "value": int(account["value"]),
                    }
                )
        return accounts


def build_ink2_declaration(fiscal_year_id: str) -> Dict:
    """Build INK2 declaration data for API routes."""
    return INK2DeclarationService().build(fiscal_year_id)
