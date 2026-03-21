# Frontend

Streamlit-baserad webbgränssnitt för Bokföringssystemet.

## Funktioner

- 📊 **Dashboard** - Översikt över nyckeltal och aktivitet
- 📒 **Kontoplan** - BAS 2026 konton i trädstruktur
- 📝 **Verifikationer** - Skapa och hantera verifikationer
- 📄 **Fakturor** - Fakturering och betalningsregistrering
- 📈 **Rapporter** - Saldobalans och huvudbok
- 🎯 **Demo Data** - Generera testdata för presentationer

## Starta

### Med Docker Compose (rekommenderas)

```bash
docker-compose up -d
```

Frontend blir tillgänglig på http://localhost:8501

### Lokalt

```bash
# Installera beroenden
pip install streamlit pandas

# Starta API:t först (i annan terminal)
python main.py --init-db --seed

# Starta frontend
streamlit run frontend/app.py
```

## Konfiguration

Frontend kopplar automatiskt till API:et. Ändra inställningar i sidopanelen:

- **API URL**: Standard är `http://localhost:8000`
- **API Key**: Standard är `dev-key-change-in-production`

## Skärmdumpar

### Dashboard
Visar nyckeltal, senaste verifikationer och fakturor samt omsättningsgraf.

### Kontoplan
Bläddra och sök i BAS 2026 kontoplanen. Filtrera efter kontotyp.

### Verifikationer
Skapa nya verifikationer med dubbel bokföring. Bokför utkast direkt i gränssnittet.

### Fakturor
Skapa fakturor med momsberäkning. Skicka och registrera betalningar.

### Rapporter
Visa saldobalans och huvudbok per period.

## Demo

Använd "Demo Data"-sidan för att generera testdata:

1. Klicka "Generera all demo-data"
2. Fyller automatiskt databasen med:
   - Räkenskapsår 2026 med 12 månader
   - 4 verifikationer (startkapital, hyra, försäljning, lön)
   - 4 fakturor (draft, sent, partially_paid, paid)

Perfekt för presentationer och användartester!
