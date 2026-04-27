# Testplan: INK2 SRU Export

## Mål
Verifiera att SRU-exporten producerar korrekta INK2-filer som matchar Skatteverkets format och referensfilerna.

## Testmiljö
- **Lokal utvecklingsmiljö:** Docker Compose
- **Testdata:** SIE4-filer från 2025 och 2026
- **Referensfiler:** INFO.SRU och BLANKETTER.SRU från arkiv

## Testfall

### 1. Integrationstest - SIE4 Import med SRU-mappningar
**Syfte:** Verifiera att #SRU-taggar parsas korrekt vid import  
**Steg:**
1. Importera `stefanwiknerconsultingab-2025.se`
2. Verifiera att SRU-mappningar sparas i databasen
3. Kontrollera att mappningarna stämmer överens med filens #SRU-taggar

**Förväntat resultat:**
- Konto 1920 → SRU-fält 7281
- Konto 3010 → SRU-fält 7410
- Konto 5010 → SRU-fält 7513
- etc.

### 2. Enhetstest - SRU Export Service
**Syfte:** Verifiera beräkningslogiken  
**Steg:**
1. Beräkna SRU-fält för 2025
2. Jämför med referensvärden från arkivet

**Förväntat resultat:**
- Fält 7251 (Rörelsens intäkter): 320000
- Fält 7281 (Övriga externa kostnader): ~585956
- Fält 7450 (Summa tillgångar): ~561232
- etc.

### 3. Filformat-test - INFO.SRU
**Syfte:** Verifiera att INFO.SRU följer specifikationen  
**Steg:**
1. Generera INFO.SRU
2. Verifiera struktur och innehåll

**Förväntat resultat:**
```
#DATABESKRIVNING_START
#PRODUKT SRU
#SKAPAD 20260202 152419
#PROGRAM BOKAI 1.0
#FILNAMN BLANKETTER.SRU
#DATABESKRIVNING_SLUT
#MEDIELEV_START
#ORGNR 5568194731
#NAMN Stefan Wikner Consulting AB
...
```

### 4. Filformat-test - BLANKETTER.SRU
**Syfte:** Verifiera att BLANKETTER.SRU följer specifikationen  
**Steg:**
1. Generera BLANKETTER.SRU
2. Verifiera struktur och innehåll

**Förväntat resultat:**
```
#BLANKETT INK2R-2025P4
#IDENTITET 5568194731 20260202 152419
#SYSTEMINFO BOKAI 1.0
#UPPGIFT 7011 20250101
#UPPGIFT 7012 20251231
#UPPGIFT 7251 320000
...
#BLANKETTSLUT
#BLANKETT INK2S-2025P4
...
#FIL_SLUT
```

### 5. Validering mot referensfiler
**Syfte:** Jämför genererade filer med referens  
**Steg:**
1. Exportera SRU för 2025
2. Jämför fält-värden med referens-BLANKETTER.SRU
3. Kontrollera att alla fält finns med

**Acceptanskriterier:**
- Alla numeriska värden ska matcha referensfilen (±1 SEK avrundning)
- Samma fältnummer ska finnas med
- Filstruktur ska identisk (förutom timestamps)

### 6. Balansräkningsvalidering
**Syfte:** Verifiera att tillgångar = skulder + EK  
**Steg:**
1. Exportera SRU för 2025
2. Kontrollera fält 7670 (skillnad)

**Förväntat resultat:**
- Fält 7670 ska vara 0 (eller nära 0 pga avrundning)

## Testkörning

### Förberedelser
```bash
# Starta systemet
docker-compose up -d

# Verifiera att API är igång
curl http://localhost:8000/health

# Importera SIE4-data
curl -X POST http://localhost:8000/api/v1/import/sie4 \
  -H "Authorization: Bearer dev-key-change-in-production" \
  -F "file=@stefanwiknerconsultingab-2025.se"
```

### Test 1: Lista SRU-mappningar
```bash
curl http://localhost:8000/api/v1/fiscal-years/{fiscal_year_id}/sru-mappings \
  -H "Authorization: Bearer dev-key-change-in-production"
```

### Test 2: Förhandsgranska INK2-data
```bash
curl http://localhost:8000/api/v1/export/sru/{fiscal_year_id}/preview \
  -H "Authorization: Bearer dev-key-change-in-production"
```

### Test 3: Exportera SRU-filer
```bash
curl -o ink2_2025_test.zip \
  http://localhost:8000/api/v1/export/sru/{fiscal_year_id} \
  -H "Authorization: Bearer dev-key-change-in-production"

# Packa upp
unzip ink2_2025_test.zip

# Visa innehåll
cat INFO.SRU
cat BLANKETTER.SRU
```

### Test 4: Jämför med referens
```bash
# Jämför fält-värden
diff <(grep "^#UPPGIFT" BLANKETTER.SRU | sort) \
     <(grep "^#UPPGIFT" referens_BLANKETTER.SRU | sort)
```

## Dokumentation av resultat

### Testlogg
| Test | Datum | Resultat | Kommentar |
|------|-------|----------|-----------|
| 1. SIE4 Import | 2026-04-08 | [ ] | |
| 2. SRU Export Service | 2026-04-08 | [ ] | |
| 3. INFO.SRU format | 2026-04-08 | [ ] | |
| 4. BLANKETTER.SRU format | 2026-04-08 | [ ] | |
| 5. Jämförelse med referens | 2026-04-08 | [ ] | |
| 6. Balansvalidering | 2026-04-08 | [ ] | |

### Bilagor
- [ ] Genererad INFO.SRU
- [ ] Genererad BLANKETTER.SRU  
- [ ] Jämförelsediff
- [ ] Skärmdumpar (om UI-test)
