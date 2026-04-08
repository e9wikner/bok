# Plan: INK2 Inkomstdeklaration för Aktiebolag (SRU-format)

## Bakgrund
INK2 är inkomstdeklarationen som alla aktiebolag i Sverige måste lämna till Skatteverket årligen. Skatteverket accepterar elektronisk inlämning via **SRU-formatet** (Skatteverkets Rapporterings-Utbyte).

## SRU-filformatet (verifierat mot exempelfiler)

Varje deklaration består av två filer:

### 1. INFO.SRU - Metadatafil
```
#DATABESKRIVNING_START
#PRODUKT  SRU
#SKAPAD 20260202 152419
#PROGRAM BOKAI 1.0
#FILNAMN BLANKETTER.SRU
#DATABESKRIVNING_SLUT
#MEDIELEV_START
#ORGNR 5568194731
#NAMN Stefan Wikner Consulting AB
#ADRESS Plansvägen 7
#POSTNR 41749
#POSTORT Göteborg
#EMAIL info@stefanwikner.se
#TELEFON 070-2233674
#MEDIELEV_SLUT
```

### 2. BLANKETTER.SRU - Datafil
```
#BLANKETT INK2R-2025P4
#IDENTITET 5568194731 20260202 152419
#SYSTEMINFO BOKAI 1.0 stefanwiknerconsultingab.bok
#UPPGIFT 7011 20250101
#UPPGIFT 7012 20251231
#UPPGIFT 7251 320000
#UPPGIFT 7261 39039
# ... fler fält
#BLANKETTSLUT
#BLANKETT INK2S-2025P4
#IDENTITET 5568194731 20260202 152419
#SYSTEMINFO BOKAI 1.0 stefanwiknerconsultingab.bok
#UPPGIFT 7650 561232
# ... fler fält
#BLANKETTSLUT
#FIL_SLUT
```

**Format-specifikation:**
- Filencoding: UTF-8 (med BOM) eller ISO-8859-1
- Radslut: CRLF (Windows-format)
- Fältseparator: Mellanslag
- Kommentarer/headers: # prefix

---

## 🎯 NYCKELUPPTÄCKT: #SRU-taggar i SIE4

SIE4-filer kan innehålla **#SRU-taggar** som explicit mappar konton till INK2-fält:

```sie4
#SRU 1920 7281    (Konto 1920 → SRU-fält 7281)
#SRU 2081 7301    (Konto 2081 → SRU-fält 7301)
#SRU 3010 7410    (Konto 3010 → SRU-fält 7410)
#SRU 6992 7513    (Konto 6992 → SRU-fält 7513)
```

### Komplett SRU-mappning från exempelfilen

| Konto | Kontonamn | SRU-fält | Fältbeskrivning |
|-------|-----------|----------|-----------------|
| 1385-1387 | Värde av kapitalförsäkring | 7235 | Finansiella anläggningstillgångar |
| 1500 | Kundfordringar | 7251 | Omsättningstillgångar |
| 1600-1650 | Fordringar | 7261 | Omsättningstillgångar |
| 1700-1790 | Förutbetalda kostnader | 7263 | Omsättningstillgångar |
| 1880 | Andra kortfristiga placeringar | 7271 | Omsättningstillgångar |
| 1920-1950 | Bankkonton | 7281 | Likvida medel |
| 2080-2081 | Eget kapital | 7301 | Eget kapital |
| 2091, 2099 | Balanserad vinst/Årets resultat | 7302 | Eget kapital |
| 2121-2129 | Periodiseringsfonder | 7321 | Obeskattade reserver |
| 2300 | Långfristiga skulder | 7350 | Långfristiga skulder |
| 2440 | Leverantörsskulder | 7365 | Kortfristiga skulder |
| 2490-2730 | Skatter och avgifter | 7368-7370 | Kortfristiga skulder |
| 2820, 2920-2990 | Skulder till anställda | 7370 | Kortfristiga skulder |
| 3010-3500 | Intäkter | 7410 | Nettoomsättning |
| 3740, 3960, 3980 | Övriga intäkter | 7413 | Övriga rörelseintäkter |
| 4000-6992 | Kostnader | 7513 | Övriga externa kostnader |
| 7000-7600 | Personalkostnader | 7514 | Personalkostnader |
| 7810-7830 | Avskrivningar | 7515 | Av- och nedskrivningar |
| 8410-8423 | Finansiella tillgångar | 7522 | Finansiella anläggningstillgångar |
| 8910-8920 | Övriga tillgångar | 7528 | Övriga tillgångar |

### Viktiga summeringsfält (beräknas)

| Fältnr | Beskrivning | Beräknas som |
|--------|-------------|--------------|
| 7420 | Summa anläggningstillgångar | 7235 + 7416 + 7417 + 7522 |
| 7450 | Summa tillgångar | 7420 + 7251 + 7261 + 7263 + 7271 + 7281 |
| 7550 | Summa eget kapital och skulder | 7301 + 7302 + 7321 + 7350 + 7365 + 7368-7370 |
| 7670 | Skillnad | 7450 - 7550 (ska vara 0) |

---

## Arkitektur: Flexibel SRU-hantering

### Strategi för olika kontoplaner

1. **Primär källa:** Använd #SRU-taggar från SIE4-filen (om de finns)
2. **Fallback:** Standard BAS2026-mappning för kända kontonummer
3. **Manuell justering:** Användaren kan redigera mappningar i inställningar

### Databasschema

```sql
-- Ny tabell för SRU-mappningar
CREATE TABLE account_sru_mappings (
    id UUID PRIMARY KEY,
    fiscal_year_id UUID NOT NULL REFERENCES fiscal_years(id),
    account_id UUID NOT NULL REFERENCES accounts(id),
    sru_field VARCHAR(10) NOT NULL,  -- t.ex. "7410", "7513"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fiscal_year_id, account_id)
);

-- Index för snabb lookup
CREATE INDEX idx_account_sru_mappings_fiscal_year 
    ON account_sru_mappings(fiscal_year_id);
```

### Standard BAS2026-mappning (fallback)

```python
DEFAULT_SRU_MAPPINGS = {
    # Anläggningstillgångar
    "7416": list(range(1000, 1100)),  # Immateriella anläggningstillgångar
    "7417": list(range(1100, 1300)),  # Materiella anläggningstillgångar
    "7522": list(range(1300, 1400)),  # Finansiella anläggningstillgångar
    
    # Omsättningstillgångar
    "7251": list(range(1400, 1500)),  # Varulager
    "7261": list(range(1500, 1600)),  # Kundfordringar
    "7263": list(range(1600, 1700)),  # Övriga fordringar
    "7271": list(range(1700, 1800)),  # Förutbetalda kostnader
    "7281": list(range(1900, 2000)),  # Likvida medel
    
    # Eget kapital
    "7301": list(range(2000, 2100)),  # Eget kapital
    "7302": [2091, 2099],             # Resultat
    "7321": list(range(2100, 2200)),  # Obeskattade reserver
    
    # Skulder
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
    "7522": list(range(8000, 8200)),  # Övriga rörelsekostnader
    "7525": list(range(8200, 8400)),  # Resultat från övriga värdepapper
    "7528": list(range(8400, 8500)),  # Övriga finansiella intäkter
}
```

---

## Implementeringsplan

### Fas 1: SIE4-import med SRU-stöd (2-3 dagar)

1. **Uppdatera SIE4-parser**
   - Extrahera #SRU-taggar vid import
   - Spara mappningar i `account_sru_mappings`

2. **Databasmigrering**
   - Skapa `account_sru_mappings` tabell
   - Lägg till metod i `AccountRepository` för SRU-hantering

3. **API för SRU-mappningar**
   - `GET /api/v1/fiscal-years/{id}/sru-mappings` - Lista mappningar
   - `PUT /api/v1/fiscal-years/{id}/sru-mappings/{account_id}` - Uppdatera mappning

### Fas 2: SRU-export service (3-4 dagar)

1. **Skapa `services/sru_export.py`**
   - `get_sru_mappings(fiscal_year_id)` - Hämta mappningar (med fallback)
   - `calculate_sru_fields(fiscal_year_id)` - Beräkna alla fältvärden
   - `generate_info_sru(company_data)` - Generera INFO.SRU
   - `generate_blanketter_sru(fiscal_year_id)` - Generera BLANKETTER.SRU
   - `export_sru_zip(fiscal_year_id)` - Paketera i ZIP

2. **Export API-endpoint**
   - `GET /api/v1/fiscal-years/{id}/export/sru` - Ladda ner ZIP
   - Content-Type: application/zip
   - Filnamn: `{company_name}_{year}_INK2_SRU.zip`

3. **Felhantering och validering**
   - Kontrollera att alla obligatoriska fält har värden
   - Validera att tillgångar = skulder + EK
   - Logga varningar för saknade mappningar

### Fas 3: Frontend för SRU-mappningar (2-3 dagar)

1. **Inställningssida: `/settings/sru-mappings`**
   - Tabell över konton med SRU-fält-dropdown
   - Visa vilka mappningar som kom från SIE4 vs standard
   - Spara-knapp för ändringar

2. **Export-knapp i rapporter**
   - "Exportera INK2 (SRU)"-knapp i resultat-/balansräkningsvyn
   - Ladda ner ZIP-fil direkt

3. **Valideringsvisning**
   - Visa varning om obalanserad balansräkning
   - Lista saknade SRU-mappningar
   - Förhandsgranska INK2-värden innan export

### Fas 4: Testning och dokumentation (1-2 dagar)

1. **Enhetstester**
   - Testa SRU-parsing från SIE4
   - Testa beräkningar med kända värden
   - Testa fallback-mappning

2. **Integrationstest**
   - Jämför export med bifogad exempelfil
   - Testa med verklig data från 2025

3. **Användardokumentation**
   - Beskriv hur SRU-mappningar fungerar
   - Instruktioner för manuell justering
   - Felsökningsguide

---

## Dataflöde

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  SIE4-fil       │────▶│  SIE4 Parser     │────▶│  #SRU-taggar    │
│  med #SRU       │     │  (uppdaterad)    │     │  sparas i DB    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                           │
                                                           ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  ZIP med        │◀────│  SRU Export      │◀────│  Mappningar +   │
│  INFO.SRU +     │     │  Service         │     │  Kontosaldon    │
│  BLANKETTER.SRU │     └──────────────────┘     └─────────────────┘
└─────────────────┘                                    │
                                                       ▼
                                              ┌──────────────────┐
                                              │  Standard BAS    │
                                              │  (fallback)      │
                                              └──────────────────┘
```

---

## Filstruktur

```
bok/
├── backend/
│   ├── app/
│   │   ├── models/
│   │   │   └── account_sru_mapping.py      # Ny modell
│   │   ├── repositories/
│   │   │   └── account_repository.py       # Uppdatera med SRU-metoder
│   │   ├── services/
│   │   │   ├── sru_export.py              # NY: SRU-export logik
│   │   │   └── sie_importer.py            # UPPDATERA: spara #SRU
│   │   └── api/routes/
│   │       ├── sru_mappings.py            # NY: API för mappningar
│   │       └── export.py                  # UPPDATERA: lägg till SRU
│   └── tests/
│       ├── test_sru_export.py
│       └── test_sie_import_sru.py
├── frontend-v3/
│   └── app/
│       ├── settings/
│       │   └── sru-mappings/
│       │       └── page.tsx               # NY: Inställningssida
│       └── reports/
│           └── components/
│               └── SruExportButton.tsx    # NY: Export-knapp
```

---

## Nästa steg

1. ✅ Plan godkänd
2. Skapa feature branch `feature/ink2-sru-export`
3. Implementera Fas 1: SIE4-import med SRU-stöd
4. Testa att #SRU-taggar extraheras korrekt
5. Fortsätt med Fas 2-4
6. Merge till main

**Total beräknad tid:** 8-12 dagar
