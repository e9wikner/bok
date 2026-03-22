# Bokföringssystem Frontend v2

Modern Next.js-frontend för bokföringssystem med kopplad lista-detalj-vy och AI-lärande.

## Features

✅ **Kopplad Lista-Detalj-vy** - Klicka på verifikation i lista → gå till detaljsida  
✅ **AI-Lärande Integration** - Korrigera AI-bokförda verifikationer och låt AI lära sig  
✅ **Modern Design** - Tailwind CSS, responsivt, clean UI  
✅ **Caching** - React Query för 5 min cachning av data  
✅ **Paginering** - 15 verifikationer per sida  
✅ **Direktlänkar** - URL-baserad navigation

## Skärmar

- **Översikt** `/` - Dashboard med snabb åtkomst
- **Verifikationer** `/vouchers` - Lista med paginering
- **Verifikationsdetalj** `/vouchers/[id]` - Detaljer + korrigeringsformulär
- **Konton** `/accounts` - Kontoplan
- **AI-Lärande** `/learning` - Se inlärda regler
- **Rapporter** `/reports` - Finansiella rapporter

## Installation

```bash
npm install
npm run dev
```

Öppna http://localhost:3000

## API Integration

Frontend förväntar API på `http://localhost:8000` med Bearer-token autentisering.

Miljövariabler:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_API_KEY=dev-key-change-in-production
```

## Arkitektur

```
app/                    # Next.js 13+ App Router
├── page.tsx           # Dashboard
├── vouchers/
│   ├── page.tsx       # Lista
│   └── [id]/page.tsx  # Detalj + korrigering
├── accounts/
├── reports/
└── learning/

components/
├── Header.tsx         # Navigation
└── VoucherList.tsx    # Tabell med paginering

hooks/
└── useVouchers.ts     # React Query hooks

lib/
└── api.ts            # API-klient
```

## Kopplad Lista-Detalj Design

1. **Lista** (`/vouchers`)
   - Tabell med 15 verifikationer
   - Klick på rad → navigera till `/vouchers/[id]`
   - Paginering för att ladda fler

2. **Detalj** (`/vouchers/[id]`)
   - Visa alla bokföringsrader
   - "Korrigera"-knapp för AI-bokförda verifikationer
   - Checkbox: "Lär AI:n av detta"
   - Spara korrigering → AI-backend tränas

## AI-Lärande Flow

```
1. AI bokför transaktion X på konto 5410 (fel)
2. Användare ser i lista → klickar för detalj
3. Verifikationssida visar kontona
4. Klickar "Korrigera" → inline-formulär
5. Ändrar till 5610 (rätt konto)
6. Kryssar "Lär AI:n"
7. Spara → POST /api/v1/learning/corrections
8. Backend sparar regel: "5410 → 5610 när typ=resa"
9. Nästa gång använder AI 5610 automatiskt
```

## Styling

Tailwind CSS med custom theme. Responsive design (mobile-first).

## Performance

- React Query för caching (5 min TTL)
- Paginering (15 items/sida)
- Suspense boundaries för optimering

## Kommande Features

- [ ] Dark mode
- [ ] Real-time updates via WebSocket
- [ ] Offline-läge (PWA)
- [ ] Drag-and-drop filuppladdning
- [ ] Globala sökfunktion
- [ ] Mobile app version

## Status

✅ Grundstruktur  
✅ Komponenter  
✅ API-integration  
✅ Kopplad navigation  
⏳ Testing  
⏳ Deployment  
