# Bokföringssystem Frontend v2

Modern Next.js frontend för bokföringssystemet. AI-nativ design för enkelt bokföringssamarbete med artificell intelligens.

## ✨ Features

### Core Features
- ✅ **Kopplad lista-detalj-vy**: Klicka på verifikation → detaljsida med direktlänkar
- ✅ **AI-lärande integration**: Korrigera AI-bokförda transaktioner → AI lär sig mönster
- ✅ **React Query caching**: 5 minuters cache för snabb navigering
- ✅ **Responsive design**: Mobile-first Tailwind CSS
- ✅ **Dark mode**: Toggle light/dark theme med systemövervakning
- ✅ **TypeScript**: Fullständig type-safety

### Funktionalitet
- 📊 **Dashboard**: KPI-kort, AI-statistik, inlärda regler
- 📝 **Verifikationslista**: Paginerad (15/sida), sortering, status
- ✏️ **Korrigeringsvyn**: Inline-redigering, "Lär AI:n"-checkbox, feedback
- 📈 **Rapporter**: Resultaträkning, balansräkning, råbalans
- 🤖 **AI-regler**: Visa inlärda bokföringsmönster + confidence
- 📥 **Import**: Drag-drop SIE4/CSV filuppladdning
- ⚙️ **Inställningar**: API-info, filuppladdning, version

## 🚀 Sidor (Routes)

| Sida | URL | Funktion |
|------|-----|----------|
| Dashboard | `/` | KPI-kort, statistik, welcome |
| Verifikationslista | `/vouchers` | Tabell (15/sida), sortering, paginering |
| Verifikationsdetalj | `/vouchers/[id]` | Full info + ändringshistorik + korrigering |
| Kontoplan | `/accounts` | Grupperad lista per kontotyp + saldo |
| Rapporter | `/reports` | Resultaträkning, balansräkning, råbalans |
| AI-Lärande | `/learning` | Inlärda regler, confidence %, historik |
| Inställningar | `/settings` | Import, API-info, system config |

## 🛠 Installation & Startup

### Lokalt (development)
```bash
npm install
npm run dev
# Öppna http://localhost:3000
```

### Docker (production)
```bash
docker-compose up -d frontend-v2
# Öppna http://localhost:3000
```

## 📡 API Integration

Frontend kommunicerar med Python FastAPI-backend på `/api/v1/`:

```
# Verifikationer
GET    /api/v1/vouchers                  # Lista (paginerad)
GET    /api/v1/vouchers/{id}             # Detalj
PUT    /api/v1/vouchers/{id}             # Uppdatera
GET    /api/v1/vouchers/{id}/audit-trail # Ändringshistorik

# AI-Lärande
POST   /api/v1/learning/corrections      # Spara korrigering
GET    /api/v1/learning/rules            # Inlärda regler
GET    /api/v1/learning/stats            # Statistik

# Rapporter
GET    /api/v1/reports/income-statement  # Resultaträkning
GET    /api/v1/reports/balance-sheet     # Balansräkning
GET    /api/v1/reports/trial-balance     # Råbalans

# Konton & Kontoplan
GET    /api/v1/accounts                  # Kontoplan
GET    /api/v1/accounts/{code}           # Kontodetalj

# Import/Export
POST   /api/v1/import/sie4               # SIE4 filuppladdning
POST   /api/v1/import/csv                # CSV bankexport
GET    /api/v1/export/sie4               # SIE4 nedladdning
GET    /api/v1/export/pdf                # PDF rapporter

# Health
GET    /health                           # API-status
```

## 🔐 Miljövariabler

Ställ dessa i `.env.local` eller Docker environment:

```bash
# API-anslutning (production: http://api:8000)
NEXT_PUBLIC_API_URL=http://localhost:8000

# API-nyckel
NEXT_PUBLIC_API_KEY=dev-key-change-in-production

# Next.js
NODE_ENV=production
```

## 📁 Projektstruktur

```
frontend-v2/
├── app/                          # Next.js App Router
│   ├── (dashboard)/              # Root layout med Header
│   │   └── page.tsx              # Dashboard
│   ├── vouchers/
│   │   ├── page.tsx              # Lista (15/sida)
│   │   └── [id]/page.tsx         # Detalj + korrigering
│   ├── accounts/page.tsx         # Kontoplan
│   ├── reports/page.tsx          # Resultaträkning, balans, råbalans
│   ├── learning/page.tsx         # AI-regler + statistik
│   ├── settings/page.tsx         # Import + system info
│   ├── layout.tsx                # Root HTML
│   ├── globals.css               # Global styles
│   └── providers.tsx             # React Query provider
│
├── components/
│   ├── Header.tsx                # Navigation + dark mode toggle
│   ├── VoucherList.tsx           # Verifikations-tabell
│   ├── CorrectionForm.tsx        # Korrigeringformulär
│   └── FileUpload.tsx            # Drag-drop filuppladdning
│
├── hooks/
│   ├── useVouchers.ts            # Verifikations-hooks
│   ├── useReports.ts             # Rapporter-hooks
│   ├── useLearning.ts            # AI-lärande hooks
│   └── useDarkMode.ts            # Dark mode toggle
│
├── lib/
│   └── api.ts                    # API-klient + TypeScript-typer
│
├── public/                       # Static assets
├── Dockerfile                    # Production build
├── docker-compose.yml            # Services orchestration
├── package.json                  # Dependencies
├── tsconfig.json                 # TypeScript config
├── jsconfig.json                 # JS import aliases
├── tailwind.config.js            # Tailwind theming
└── next.config.js                # Next.js config
```

## 🎨 Design & Styling

- **Tailwind CSS**: Utility-first styling
- **Dark mode**: Class-based (`dark:`) med localStorage
- **Responsive**: Mobile-first breakpoints
- **Accessibility**: WCAG 2.1 AA (labels, ARIA, keyboard nav)
- **Performance**: Image optimization, lazy loading, code splitting

## 🔄 State Management

| Teknik | Användning |
|--------|-----------|
| React Query | Server state (API data) + caching |
| React hooks | Lokal state (UI toggles, forms) |
| localStorage | Persistence (dark mode, preferences) |

## 🚄 Prestanda

- **Cache-TTL**: 5 minuter (configurabel per hook)
- **Paginering**: 15 items/sida (minskar DOM-noder)
- **Lazy loading**: Dynamic imports för routes
- **Image optimization**: Next.js Image component
- **Code splitting**: Automatisk per route

## 🤖 AI-Lärande Workflow

```
1. AI bokför transaktion X
2. Användare ser verifikation i lista
3. Klickar → detaljvy
4. Klickar "Korrigera"
5. Ändrar konto (t.ex. 5410 → 5610)
6. Kryssar i "Lär AI:n av detta"
7. Sparar → API lagrar korrigering
8. Backend analyserar mönster
9. Nästa liknnande tx → AI använder 5610
```

## 🔌 Utveckling

### Lägga till ny sida
```bash
# Skapa route-mapp
mkdir -p app/new-feature

# Skapa page.tsx
echo "'use client'

import { Header } from '@/components/Header'

export default function NewFeaturePage() {
  return (
    <>
      <Header />
      <div className=\"max-w-7xl mx-auto px-4 py-8\">
        <!-- Din innehål här -->
      </div>
    </>
  )
}
" > app/new-feature/page.tsx
```

### Lägga till ny hook
```bash
# Skapa hook
echo "'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useNewData() {
  return useQuery({
    queryKey: ['new-data'],
    queryFn: () => api.getNewData(),
    staleTime: 5 * 60 * 1000,
  })
}
" > hooks/useNewData.ts
```

### API-integration
```typescript
// lib/api.ts
export const api = {
  getNewData: async () => {
    const { data } = await apiClient.get('/api/v1/new-endpoint')
    return data
  },
}
```

## 📦 Dependencies

| Package | Version | Användning |
|---------|---------|-----------|
| next | 14.x | Framework |
| react | 18.x | UI library |
| @tanstack/react-query | 5.x | Server state + caching |
| tailwindcss | 3.x | Styling |
| typescript | 5.x | Type safety |
| axios | 1.x | HTTP client |

## 🐛 Debugging

Enable dev tools:
```bash
npm run dev -- --debug
```

Check React DevTools Chrome extension for component profiling.

## 🚀 Deployment

### Vercel (recommended for Next.js)
```bash
vercel deploy
```

### Docker Hub
```bash
docker build -t bokfoering-frontend-v2 .
docker tag bokfoering-frontend-v2 YOUR_REGISTRY/bokfoering-frontend-v2
docker push YOUR_REGISTRY/bokfoering-frontend-v2
```

### Environment vars (production)
```
NEXT_PUBLIC_API_URL=https://api.bokfoering.mycompany.com
NEXT_PUBLIC_API_KEY=your-production-key
```

## 📊 Monitoering

- Health check: `GET /` (returns 200 if healthy)
- API status: Check `/health` endpoint in backend

## 📝 License

Se ROOTprojektet för license.
