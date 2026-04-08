# Plan: INK2 Inkomstdeklaration för Aktiebolag

## Bakgrund
INK2 är inkomstdeklarationen som alla aktiebolag i Sverige måste lämna till Skatteverket årligen. Den innehåller information om företagets resultat, skatt och andra uppgifter.

## Nuvarande situation
Skatteverket erbjuder följande sätt att lämna INK2:

1. **Mina sidor** - Digital inloggning och ifyllnad direkt på skatteverket.se
2. **E-faktura/EDI** - För större företag med systemintegration
3. **PDF-blankett** - Manuell ifyllnad och inlämning

## Tekniska möjligheter

### Alternativ 1: Manuell export från frontend (Rekommenderad kortsiktig lösning)
**Beskrivning:** Skapa en förifylld INK2-blankett i frontend som användaren kan:
- Se och granska alla värden
- Kopiera värden manuellt till Skatteverkets Mina sidor
- Exportera som PDF för egen dokumentation

**Fördelar:**
- Snabb att implementera
- Ingen integration mot Skatteverket krävs
- Användaren behåller kontrollen

**Nackdelar:**
- Manuell överföring till Skatteverket

### Alternativ 2: XML/JSON-export för framtida automation
**Beskrivning:** Skapa en strukturerad export av INK2-data som kan användas för:
- Framtida direktintegration om Skatteverket öppnar API
- Import i andra deklarationsprogram (Fortnox, Visma, etc.)

**INK2-fält som behöver mappas från bokföring:**

| INK2-fält | Källa i bokföring | Konto/Beräkning |
|-----------|-------------------|-----------------|
| 2.1 Rörelsens intäkter | Resultaträkning | 3000-3999 (kredit) |
| 2.2 Rörelsens kostnader | Resultaträkning | 4000-6999 (debet) |
| 2.3 Rörelseresultat | Beräknat | Intäkter - Kostnader |
| 3.1 Finansiella intäkter | Resultaträkning | 8000-8299 |
| 3.2 Finansiella kostnader | Resultaträkning | 8300-8899 |
| 4.1 Resultat efter finansiella poster | Beräknat | 2.3 + 3.1 - 3.2 |
| 5.1 Skatt på årets resultat | Beräknat | 22% av vinst (om ej räntefördelning) |
| 5.2 Årets resultat | Beräknat | 4.1 - 5.1 |

**Tillgångar och skulder (från balansräkning):**
| INK2-fält | Källa | Konton |
|-----------|-------|--------|
| 1.1 Tillgångar | Balansräkning | 1000-1999 |
| 1.2 Eget kapital | Balansräkning | 2000-2099 |
| 1.3 Avsättningar | Balansräkning | 2100-2199 |
| 1.4 Långfristiga skulder | Balansräkning | 2200-2299 |
| 1.5 Kortfristiga skulder | Balansräkning | 2300-2999 |

### Alternativ 3: Direktintegration med Skatteverket (Långsiktig vision)
**Beskrivning:** Om Skatteverket i framtiden erbjuder:
- API för inlämning av INK2
- EDI-integration för mindre företag

**Status:** För närvarande inte tillgängligt för små företag utan avancerade system.

## Rekommenderad implementering

### Fas 1: Frontend-visning (2-3 dagar)
1. Skapa ny sida `/tax-declaration` eller `/ink2`
2. Hämta data från befintliga rapporter (resultaträkning, balansräkning)
3. Mappa konton till INK2-fält enligt tabellen ovan
4. Visa alla fält i en strukturerad vy inspirerad av Skatteverkets blankett
5. Lägg till "Kopiera till urklipp"-knappar per fält

### Fas 2: PDF-export (1-2 dagar)
1. Skapa PDF-mall för INK2 (baserad på Skatteverkets blankett)
2. Fyll i alla beräknade värden
3. Lägg till export-knapp i frontend

### Fas 3: XML-export för framtida integration (2-3 dagar)
1. Skapa XML-format som följer Skatteverkets specifikation (om tillgänglig)
2. Alternativt: Skapa JSON-export för import i andra system
3. Dokumentera formatet för framtida utveckling

## Data som behövs från systemet

### Resultaträkning (P&L)
- Nettoomsättning (3000-3799)
- Övriga rörelseintäkter (3900-3999)
- Material och varor (4000-4999)
- Lokalhyra (5000-5099)
- Övriga externa kostnader (5100-6999)
- Personalkostnader (7000-7699)
- Avskrivningar (8000-8099)
- Övriga rörelsekostnader (8100-8299)
- Finansiella intäkter (8300-8399)
- Finansiella kostnader (8400-8499)

### Balansräkning
- Tillgångar (1000-1999)
- Eget kapital (2000-2099)
- Avsättningar (2100-2199)
- Skulder (2200-2999)

### Övriga uppgifter
- Företagsnamn
- Organisationsnummer
- Redovisningsperiod (räkenskapsår)
- Bokslutsdatum
- Antal anställda

## Nästa steg
1. Bekräfta plan med användare
2. Implementera Fas 1 (frontend-visning)
3. Testa med verklig data
4. Implementera Fas 2 (PDF-export)
5. Dokumentera för användare
