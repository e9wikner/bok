# Bokföringssystem Frontend v2

Modern Next.js frontend för bokföringssystemet.

## Features

- ✅ **Kopplad lista-detalj-vy**: Klicka på verifikation → detaljsida
- ✅ **AI-lärande integration**: Korrigera AI-bokförda transaktioner + lär AI:n
- ✅ **React Query caching**: 5 minuters cache för snabbare navigering
- ✅ **Responsive design**: Tailwind CSS
- ✅ **TypeScript**: Type-safe kod

## Sidor

- `/` - Dashboard/Översikt
- `/vouchers` - Verifikationslista (paginerad, 15 items/sida)
- `/vouchers/[id]` - Verifikationsdetalj + korrigering
- `/accounts` - Kontoplan
- `/reports` - Rapporter (stub)
- `/learning` - AI-lärande regler + statistik

## Kom igång

```bash
npm install
npm run dev
```

Öppna http://localhost:3000

## API Integration

Frontend använder dessa endpoints från backend:

```
GET  /api/v1/vouchers                    # Lista verifikationer
GET  /api/v1/vouchers/{id}               # Detalj
PUT  /api/v1/vouchers/{id}               # Uppdatera
POST /api/v1/learning/corrections        # Spara korrigering
GET  /api/v1/learning/rules              # Hämta inlärda regler
GET  /api/v1/accounts                    # Kontoplan
GET  /health                             # Health check
```

## Miljövariabler

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_API_KEY=dev-key-change-in-production
```

## Arkitektur

```
app/                    # Next.js App Router
├── (dashboard)/        # Grouped routes med Header
├── vouchers/           # Verifikations-sidor
├── accounts/           # Kontoplan
├── learning/           # AI-lärande
└── reports/            # Rapporter

components/            # React-komponenter
├── Header.tsx         # Top navigation
└── VoucherList.tsx    # Verifikations-tabell

hooks/                 # Custom React hooks
├── useVouchers.ts     # API hooks med caching
└── useLearning.ts     # Learning hooks

lib/
├── api.ts            # API-klient + typer
└── utils.ts          # Hjälpfunktioner
```

## Styling

- **Tailwind CSS** för utility-based styling
- **Responsive design** med grid/flex
- **Dark mode** ready (kan aktiveras senare)

## State Management

- **React Query** för server state + caching
- **React hooks** för lokal state

## Nästa steg

- [ ] Implementera rapporter (resultaträkning, balansräkning)
- [ ] Lägg till dark mode
- [ ] Implementera offline-läge (PWA)
- [ ] Drag-and-drop filuppladdning
- [ ] Global sökfunktion
- [ ] Keyboard shortcuts
