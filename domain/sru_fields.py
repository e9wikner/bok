"""Canonical INK2R field table: SRU field code, form row, label and BAS accounts.

This module is the *single* source for how BAS accounts map onto Skatteverket's
SRU field codes. Both ``services/sru_export.py`` (which writes BLANKETTER.SRU)
and ``services/ink2_declaration.py`` (which renders the on-screen declaration)
derive from it, so the two can no longer drift apart and disagree about what a
field code means — the defect reported in GitHub issues #25, #30 and #44.

Source: BAS "Kopplingstabell Inkomstdeklaration 2", BAS 2023 accounts, published
by BAS-intressenternas Förening:

    https://www.bas.se/wp-content/uploads/2024/11/INK2_P1-231002_241119.xlsx

Account ranges below are inclusive and transcribed from that table row by row.
Accounts outside every range are deliberately left unmapped: BAS has no INK2R
row for them, and ``SRUExportService`` warns about any unmapped account that
actually carries a balance rather than dropping it silently.

Sign convention
---------------
``credit`` marks a row whose balance is a credit in the ledger (equity,
liabilities, income). Internal balances are debit-positive öre, so those rows
are negated to become the positive figure the form asks for. ``cost`` rows are
reported as positive amounts as well, by taking the absolute value.

Rows the BAS table splits by the sign of the net balance ("Om netto +/-") carry
both codes in ``field`` and ``negative_field``; the export resolves which of the
two applies from the net balance of the row's accounts.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

AccountRange = Tuple[int, int]


@dataclass(frozen=True)
class INK2RRow:
    """One row of the INK2R form (räkenskapsschema)."""

    row: str  # Form row number, e.g. "2.45"
    field: str  # SRU field code used when the net balance has the normal sign
    label: str
    section: str
    accounts: Tuple[AccountRange, ...] = ()
    kind: str = "asset"  # asset | credit | cost
    negative_field: Optional[str] = None  # code used when the net sign flips
    sign: Optional[str] = None  # display sign on the form ("+", "-", "(+) =")

    @property
    def field_codes(self) -> Tuple[str, ...]:
        """Every SRU code this row can produce."""
        if self.negative_field:
            return (self.field, self.negative_field)
        return (self.field,)

    @property
    def mapping_key(self) -> str:
        """Key used in the account mapping; ``a/b`` for sign-split rows."""
        if self.negative_field:
            return f"{self.field}/{self.negative_field}"
        return self.field

    def account_numbers(self) -> List[int]:
        """Expand the row's ranges into individual BAS account numbers."""
        numbers: List[int] = []
        for start, end in self.accounts:
            numbers.extend(range(start, end + 1))
        return numbers


_ASSETS = "Tillgångar / Anläggningstillgångar"
_CURRENT_ASSETS = "Omsättningstillgångar"
_EQUITY = "Eget kapital"
_UNTAXED = "Obeskattade reserver och avsättningar"
_LIABILITIES = "Skulder"
_INCOME_STATEMENT = "Resultaträkning"


INK2R_ROWS: Tuple[INK2RRow, ...] = (
    # --- Balansräkning: anläggningstillgångar -------------------------------
    INK2RRow("2.1", "7201", "Koncessioner, patent, licenser, varumärken, hyresrätter, goodwill och liknande rättigheter", _ASSETS, ((1000, 1087), (1089, 1099))),
    INK2RRow("2.2", "7202", "Förskott avseende immateriella anläggningstillgångar", _ASSETS, ((1088, 1088),)),
    INK2RRow("2.3", "7214", "Byggnader och mark", _ASSETS, ((1100, 1119), (1130, 1179), (1190, 1199))),
    INK2RRow("2.4", "7215", "Maskiner, inventarier och övriga materiella anläggningstillgångar", _ASSETS, ((1200, 1279), (1290, 1299))),
    INK2RRow("2.5", "7216", "Förbättringsutgifter på annans fastighet", _ASSETS, ((1120, 1129),)),
    INK2RRow("2.6", "7217", "Pågående nyanläggningar och förskott avseende materiella anläggningstillgångar", _ASSETS, ((1180, 1189), (1280, 1289))),
    INK2RRow("2.7", "7230", "Andelar i koncernföretag", _ASSETS, ((1310, 1319),)),
    INK2RRow("2.8", "7231", "Andelar i intresseföretag och gemensamt styrda företag", _ASSETS, ((1330, 1335), (1338, 1339))),
    INK2RRow("2.9", "7233", "Ägarintresse i övriga företag och andra långfristiga värdepappersinnehav", _ASSETS, ((1336, 1337), (1350, 1359))),
    INK2RRow("2.10", "7232", "Fordringar hos koncern-, intresse- och gemensamt styrda företag", _ASSETS, ((1320, 1329), (1340, 1345), (1348, 1349))),
    INK2RRow("2.11", "7234", "Lån till delägare eller närstående", _ASSETS, ((1360, 1369),)),
    INK2RRow("2.12", "7235", "Fordringar hos övriga företag som det finns ett ägarintresse i och andra långfristiga fordringar", _ASSETS, ((1346, 1347), (1370, 1389))),

    # --- Balansräkning: omsättningstillgångar -------------------------------
    INK2RRow("2.13", "7241", "Råvaror och förnödenheter", _CURRENT_ASSETS, ((1410, 1429),)),
    INK2RRow("2.14", "7242", "Varor under tillverkning", _CURRENT_ASSETS, ((1440, 1449),)),
    INK2RRow("2.15", "7243", "Färdiga varor och handelsvaror", _CURRENT_ASSETS, ((1450, 1469),)),
    INK2RRow("2.16", "7244", "Övriga lagertillgångar", _CURRENT_ASSETS, ((1490, 1499),)),
    INK2RRow("2.17", "7245", "Pågående arbeten för annans räkning", _CURRENT_ASSETS, ((1470, 1479),)),
    INK2RRow("2.18", "7246", "Förskott till leverantörer", _CURRENT_ASSETS, ((1480, 1489),)),
    INK2RRow("2.19", "7251", "Kundfordringar", _CURRENT_ASSETS, ((1510, 1559), (1580, 1589))),
    INK2RRow("2.20", "7252", "Fordringar hos koncern-, intresse- och gemensamt styrda företag", _CURRENT_ASSETS, ((1560, 1572), (1574, 1579), (1660, 1672), (1674, 1679))),
    INK2RRow("2.21", "7261", "Fordringar hos övriga företag som det finns ett ägarintresse i och övriga fordringar", _CURRENT_ASSETS, ((1573, 1573), (1610, 1619), (1630, 1659), (1673, 1673), (1680, 1699))),
    INK2RRow("2.22", "7262", "Upparbetad men ej fakturerad intäkt", _CURRENT_ASSETS, ((1620, 1629),)),
    INK2RRow("2.23", "7263", "Förutbetalda kostnader och upplupna intäkter", _CURRENT_ASSETS, ((1700, 1799),)),
    INK2RRow("2.24", "7270", "Andelar i koncernföretag", _CURRENT_ASSETS, ((1860, 1869),)),
    INK2RRow("2.25", "7271", "Övriga kortfristiga placeringar", _CURRENT_ASSETS, ((1800, 1859), (1870, 1899))),
    INK2RRow("2.26", "7281", "Kassa, bank och redovisningsmedel", _CURRENT_ASSETS, ((1900, 1999),)),

    # --- Eget kapital -------------------------------------------------------
    INK2RRow("2.27", "7301", "Bundet eget kapital", _EQUITY, ((2080, 2089),), "credit"),
    INK2RRow("2.28", "7302", "Fritt eget kapital", _EQUITY, ((2090, 2099),), "credit"),

    # --- Obeskattade reserver och avsättningar ------------------------------
    INK2RRow("2.29", "7321", "Periodiseringsfonder", _UNTAXED, ((2110, 2139),), "credit"),
    INK2RRow("2.30", "7322", "Ackumulerade överavskrivningar", _UNTAXED, ((2150, 2159),), "credit"),
    INK2RRow("2.31", "7323", "Övriga obeskattade reserver", _UNTAXED, ((2160, 2199),), "credit"),
    INK2RRow("2.32", "7331", "Avsättningar för pensioner och liknande förpliktelser enligt lagen (1967:531) om tryggande av pensionsutfästelser m.m.", _UNTAXED, ((2210, 2219),), "credit"),
    INK2RRow("2.33", "7332", "Övriga avsättningar för pensioner och liknande förpliktelser", _UNTAXED, ((2230, 2239),), "credit"),
    INK2RRow("2.34", "7333", "Övriga avsättningar", _UNTAXED, ((2220, 2229), (2240, 2299)), "credit"),

    # --- Långfristiga skulder ----------------------------------------------
    INK2RRow("2.35", "7350", "Obligationslån", _LIABILITIES, ((2310, 2329),), "credit"),
    INK2RRow("2.36", "7351", "Checkräkningskredit", _LIABILITIES, ((2330, 2339),), "credit"),
    INK2RRow("2.37", "7352", "Övriga skulder till kreditinstitut", _LIABILITIES, ((2340, 2359),), "credit"),
    INK2RRow("2.38", "7353", "Skulder till koncern-, intresse- och gemensamt styrda företag", _LIABILITIES, ((2360, 2372), (2374, 2379)), "credit"),
    INK2RRow("2.39", "7354", "Skulder till övriga företag som det finns ett ägarintresse i och övriga skulder", _LIABILITIES, ((2373, 2373), (2380, 2399)), "credit"),

    # --- Kortfristiga skulder ----------------------------------------------
    # 7365 is Leverantörsskulder and 7368 is Skatteskulder. Getting these two
    # the wrong way round is what issue #44 was about; the codes below are the
    # BAS/Skatteverket ones, not a plausible-looking sequence.
    INK2RRow("2.40", "7360", "Checkräkningskredit", _LIABILITIES, ((2480, 2489),), "credit"),
    INK2RRow("2.41", "7361", "Övriga skulder till kreditinstitut", _LIABILITIES, ((2410, 2419),), "credit"),
    INK2RRow("2.42", "7362", "Förskott från kunder", _LIABILITIES, ((2420, 2429),), "credit"),
    INK2RRow("2.43", "7363", "Pågående arbeten för annans räkning", _LIABILITIES, ((2430, 2439),), "credit"),
    INK2RRow("2.44", "7364", "Fakturerad men ej upparbetad intäkt", _LIABILITIES, ((2450, 2459),), "credit"),
    INK2RRow("2.45", "7365", "Leverantörsskulder", _LIABILITIES, ((2440, 2449),), "credit"),
    INK2RRow("2.46", "7366", "Växelskulder", _LIABILITIES, ((2492, 2492),), "credit"),
    INK2RRow("2.47", "7367", "Skulder till koncern-, intresse- och gemensamt styrda företag", _LIABILITIES, ((2460, 2472), (2474, 2479), (2860, 2872), (2874, 2879)), "credit"),
    INK2RRow("2.48", "7369", "Skulder till övriga företag som det finns ett ägarintresse i och övriga skulder", _LIABILITIES, ((2473, 2473), (2490, 2491), (2493, 2499), (2600, 2859), (2873, 2873), (2880, 2899)), "credit"),
    INK2RRow("2.49", "7368", "Skatteskulder", _LIABILITIES, ((2500, 2599),), "credit"),
    INK2RRow("2.50", "7370", "Upplupna kostnader och förutbetalda intäkter", _LIABILITIES, ((2900, 2999),), "credit"),

    # --- Resultaträkning ----------------------------------------------------
    INK2RRow("3.1", "7410", "Nettoomsättning", _INCOME_STATEMENT, ((3000, 3799),), "credit", sign="+"),
    INK2RRow("3.2", "7411", "Förändring av lager av produkter i arbete, färdiga varor och pågående arbete för annans räkning", _INCOME_STATEMENT, ((4900, 4909), (4930, 4959), (4970, 4979), (4990, 4999)), "credit", negative_field="7510", sign="+"),
    INK2RRow("3.3", "7412", "Aktiverat arbete för egen räkning", _INCOME_STATEMENT, ((3800, 3899),), "credit", sign="+"),
    INK2RRow("3.4", "7413", "Övriga rörelseintäkter", _INCOME_STATEMENT, ((3900, 3999),), "credit", sign="+"),
    # BAS lists 4000-4799 under both 3.5 and 3.6 — a company keeps its purchases
    # in one or the other. 3.5 takes the shared range by default; a business that
    # reports them as Handelsvaror remaps those accounts to 7512 per fiscal year.
    INK2RRow("3.5", "7511", "Råvaror och förnödenheter", _INCOME_STATEMENT, ((4000, 4799), (4910, 4929)), "cost", sign="-"),
    INK2RRow("3.6", "7512", "Handelsvaror", _INCOME_STATEMENT, ((4960, 4969), (4980, 4989)), "cost", sign="-"),
    INK2RRow("3.7", "7513", "Övriga externa kostnader", _INCOME_STATEMENT, ((5000, 6999),), "cost", sign="-"),
    INK2RRow("3.8", "7514", "Personalkostnader", _INCOME_STATEMENT, ((7000, 7699),), "cost", sign="-"),
    INK2RRow("3.9", "7515", "Av- och nedskrivningar av materiella och immateriella anläggningstillgångar", _INCOME_STATEMENT, ((7700, 7739), (7750, 7789), (7800, 7899)), "cost", sign="-"),
    INK2RRow("3.10", "7516", "Nedskrivningar av omsättningstillgångar utöver normala nedskrivningar", _INCOME_STATEMENT, ((7740, 7749), (7790, 7799)), "cost", sign="-"),
    INK2RRow("3.11", "7517", "Övriga rörelsekostnader", _INCOME_STATEMENT, ((7900, 7999),), "cost", sign="-"),
    INK2RRow("3.12", "7414", "Resultat från andelar i koncernföretag", _INCOME_STATEMENT, ((8000, 8069), (8090, 8099)), "credit", negative_field="7518", sign="+"),
    INK2RRow("3.13", "7415", "Resultat från andelar i intresseföretag och gemensamt styrda företag", _INCOME_STATEMENT, ((8100, 8112), (8114, 8117), (8119, 8122), (8124, 8132), (8134, 8169), (8190, 8199)), "credit", negative_field="7519", sign="+"),
    INK2RRow("3.14", "7423", "Resultat från övriga företag som det finns ett ägarintresse i", _INCOME_STATEMENT, ((8113, 8113), (8118, 8118), (8123, 8123), (8133, 8133)), "credit", negative_field="7530", sign="+"),
    INK2RRow("3.15", "7416", "Resultat från övriga finansiella anläggningstillgångar", _INCOME_STATEMENT, ((8200, 8269), (8290, 8299)), "credit", negative_field="7520", sign="+"),
    INK2RRow("3.16", "7417", "Övriga ränteintäkter och liknande resultatposter", _INCOME_STATEMENT, ((8300, 8369), (8390, 8399)), "credit", sign="+"),
    INK2RRow("3.17", "7521", "Nedskrivningar av finansiella anläggningstillgångar och kortfristiga placeringar", _INCOME_STATEMENT, ((8070, 8089), (8170, 8189), (8270, 8289), (8370, 8389)), "cost", sign="-"),
    INK2RRow("3.18", "7522", "Räntekostnader och liknande resultatposter", _INCOME_STATEMENT, ((8400, 8499),), "cost", sign="-"),
    INK2RRow("3.19", "7524", "Lämnade koncernbidrag", _INCOME_STATEMENT, ((8830, 8839),), "cost", sign="-"),
    INK2RRow("3.20", "7419", "Mottagna koncernbidrag", _INCOME_STATEMENT, ((8820, 8829),), "credit", sign="+"),
    # 8810 is a net account: a credit balance is a reversal (3.21), a debit
    # balance an allocation (3.22). 8819 and 8811 are always one or the other,
    # so they are mapped outright below instead of through the sign split.
    INK2RRow("3.21", "7420", "Återföring av periodiseringsfond", _INCOME_STATEMENT, ((8810, 8810),), "credit", negative_field="7525", sign="+"),
    INK2RRow("3.22", "7525", "Avsättning till periodiseringsfond", _INCOME_STATEMENT, ((8811, 8811),), "cost", sign="-"),
    INK2RRow("3.23", "7421", "Förändring av överavskrivningar", _INCOME_STATEMENT, ((8850, 8859),), "credit", negative_field="7526", sign="+"),
    INK2RRow("3.24", "7422", "Övriga bokslutsdispositioner", _INCOME_STATEMENT, ((8860, 8899),), "credit", negative_field="7527", sign="+"),
    INK2RRow("3.25", "7528", "Skatt på årets resultat", _INCOME_STATEMENT, ((8900, 8989),), "cost", sign="-"),
)

# Accounts BAS pins to one side of a sign-split row, so they cannot share that
# row's net-balance mapping: 8819 is always a reversal (3.21) and 8840-8849 is
# always reported on the cost side of 3.24.
_EXTRA_ACCOUNTS: Dict[str, Tuple[AccountRange, ...]] = {
    "7420": ((8819, 8819),),
    "7527": ((8840, 8849),),
}

# Årets resultat (8990-8999) is derived from the result rows above rather than
# mapped, so it is not part of INK2R_ROWS and carries no default mapping. An
# imported SIE4 file may still map it as "7450/7550", which resolves on the sign
# of the balance: BAS books a profit as a debit on 899x, so a debit balance is
# 3.26 (vinst) and a credit balance 3.27 (förlust).
DERIVED_RESULT_ACCOUNTS = frozenset(range(8990, 9000))

RESULT_FIELD_LABELS = {
    "7450": "Årets resultat, vinst",
    "7550": "Årets resultat, förlust",
}

# INK2S (skattemässiga justeringar) codes the export derives from INK2R.
INK2S_FIELD_LABELS = {
    "7650": "Årets resultat, vinst",
    "7651": "Skatt på årets resultat",
    "7653": "Andra bokförda kostnader som inte ska dras av",
    "7754": "Andra bokförda intäkter som inte ska tas upp",
    "7654": "Schablonintäkt på kvarvarande periodiseringsfonder",
    "7670": "Överskott av näringsverksamhet",
}

# A code that is one row's primary field and another row's negative half — 7525
# is row 3.22 and the negative side of 3.21 — belongs to the row that owns it.
ROWS_BY_FIELD: Dict[str, INK2RRow] = {
    **{row.negative_field: row for row in INK2R_ROWS if row.negative_field},
    **{row.field: row for row in INK2R_ROWS},
}

# 7450 is deliberately absent: a profit is a debit balance on 899x, so it is
# already positive without a flip.
CREDIT_FIELDS = frozenset(
    row.field for row in INK2R_ROWS if row.kind == "credit"
)

COST_FIELDS = frozenset(
    [row.field for row in INK2R_ROWS if row.kind == "cost"]
    + [row.negative_field for row in INK2R_ROWS if row.negative_field]
) | {"7550"}

# Result rows only (3.x). Årets resultat is the sum of the income codes less the
# cost codes, so both the export and the declaration page derive it from these.
INCOME_FIELDS: Tuple[str, ...] = tuple(
    row.field
    for row in INK2R_ROWS
    if row.section == _INCOME_STATEMENT and row.kind == "credit"
)

EXPENSE_FIELDS: Tuple[str, ...] = tuple(
    dict.fromkeys(
        [row.field for row in INK2R_ROWS if row.section == _INCOME_STATEMENT and row.kind == "cost"]
        + [
            row.negative_field
            for row in INK2R_ROWS
            if row.section == _INCOME_STATEMENT and row.negative_field
        ]
    )
)


# The two halves of the balance sheet, for checking that it balances.
BALANCE_ASSET_FIELDS: Tuple[str, ...] = tuple(
    row.field for row in INK2R_ROWS if row.section in (_ASSETS, _CURRENT_ASSETS)
)

BALANCE_EQUITY_LIABILITY_FIELDS: Tuple[str, ...] = tuple(
    row.field
    for row in INK2R_ROWS
    if row.section in (_EQUITY, _UNTAXED, _LIABILITIES)
)


def default_account_mappings() -> Dict[str, List[int]]:
    """BAS account numbers per mapping key, for the fallback SRU mapping."""
    mappings: Dict[str, List[int]] = {}
    for row in INK2R_ROWS:
        mappings.setdefault(row.mapping_key, []).extend(row.account_numbers())
    for field_code, ranges in _EXTRA_ACCOUNTS.items():
        numbers = mappings.setdefault(field_code, [])
        for start, end in ranges:
            numbers.extend(range(start, end + 1))
    return mappings


def field_labels() -> Dict[str, str]:
    """Human-readable label per SRU field code."""
    labels: Dict[str, str] = {
        code: row.label for code, row in ROWS_BY_FIELD.items()
    }
    labels.update(RESULT_FIELD_LABELS)
    labels.update(INK2S_FIELD_LABELS)
    return labels


def account_ranges_label(row: INK2RRow) -> str:
    """Render a row's BAS ranges the way the coupling table prints them."""
    parts = [
        str(start) if start == end else f"{start}-{end}"
        for start, end in row.accounts
    ]
    return ", ".join(parts)
