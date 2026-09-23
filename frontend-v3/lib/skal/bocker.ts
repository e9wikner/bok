/**
 * Böckernas tre vyer ur riktiga data (modul `skal`).
 *
 * Ersätter BALANS, RESULTAT och VERIFIKATIONER i `mock.ts` med serverns
 * rapporter för det räkenskapsår översikten pekar ut. Funktionerna här är
 * rena avbildningar från API-svar till `VyData`; hämtningen ligger i
 * `bockerApi` och cachningen i `hooks/useBockerVyer.ts`.
 *
 * Beloppen kommer i öre och visas i hela kronor, som designen kräver.
 */

import apiClient from "@/lib/api";
import { formatBeloppHela } from "@/lib/skal/format";
import type { VyData, VyRadData, VySektionData } from "@/lib/skal/mock";
import type { OverviewFiscalYear } from "@/lib/skal/api";

// ─── API-svaren, bara de fält vyerna läser ────────────────────────────────

export interface BalansKonto {
  code: string;
  name: string;
  opening_balance: number;
  change: number;
  closing_balance: number;
}

export interface Balansrakning {
  closing_assets: number;
  closing_equity_liabilities: number;
  has_ib_vouchers: boolean;
  fixed_assets_details: BalansKonto[];
  receivables_details: BalansKonto[];
  bank_and_cash_details: BalansKonto[];
  current_assets_details: BalansKonto[];
  equity_details: BalansKonto[];
  long_term_liabilities_details: BalansKonto[];
  current_liabilities_details: BalansKonto[];
}

export interface ResultatKonto {
  code: string;
  name: string;
  amount: number;
}

export interface Resultatrakning {
  revenue: number;
  costs: number;
  financial: number;
  operating_profit: number;
  profit: number;
  revenue_details: ResultatKonto[];
  cost_details: ResultatKonto[];
  financial_details: ResultatKonto[];
  voucher_count: number;
}

export interface Verifikation {
  id: string;
  series: string;
  number: number;
  date: string;
  description: string;
  status: string;
  total_debit: number;
  missing_attachment?: boolean;
}

export interface Verifikationslista {
  total: number;
  vouchers: Verifikation[];
}

/** Så många postade verifikationer visas; resten finns i /vouchers. */
export const VERIFIKATIONER_ANTAL = 50;

export const bockerApi = {
  getBalansrakning: async (fiscalYearId: string): Promise<Balansrakning> => {
    const { data } = await apiClient.get<Balansrakning>("/api/v1/reports/balance-sheet", {
      params: { fiscal_year_id: fiscalYearId },
    });
    return data;
  },

  getResultatrakning: async (fiscalYearId: string): Promise<Resultatrakning> => {
    const { data } = await apiClient.get<Resultatrakning>("/api/v1/reports/income-statement", {
      params: { fiscal_year_id: fiscalYearId },
    });
    return data;
  },

  getVerifikationer: async (
    fiscalYearId: string,
    status: "posted" | "draft",
    limit?: number
  ): Promise<Verifikationslista> => {
    const { data } = await apiClient.get<Verifikationslista>("/api/v1/vouchers", {
      params: {
        fiscal_year_id: fiscalYearId,
        status,
        limit,
        sort_by: "date",
        sort_order: "desc",
        exclude_series: "IB",
      },
    });
    return data;
  },
};

// ─── Avbildningarna ───────────────────────────────────────────────────────

function arsrubrik(ar: OverviewFiscalYear): string {
  return `${ar.start} – ${ar.end}`;
}

function kontorad(k: { code: string; name: string }, belopp: number): VyRadData {
  return { id: k.code, titel: k.name, meta: k.code, hoger: formatBeloppHela(belopp) };
}

function summarad(id: string, titel: string, belopp: number): VyRadData {
  return { id, titel, hoger: formatBeloppHela(belopp), summa: true };
}

function sorterade(...listor: BalansKonto[][]): BalansKonto[] {
  return listor
    .flat()
    .filter((k) => k.closing_balance !== 0)
    .sort((a, b) => a.code.localeCompare(b.code));
}

/**
 * Balansräkningen per räkenskapsårets utgång, med årets resultat.
 *
 * Serverns summa för eget kapital och skulder omfattar bara klass 2. Förrän
 * årets resultat är bokat mot 2099 ligger det i resultatkontona, så det
 * läggs till som en egen rad ur resultaträkningen. Då ska summorna mötas;
 * gör de inte det är vyn i felläge.
 */
export function balansVy(
  ar: OverviewFiscalYear,
  b: Balansrakning,
  r: Resultatrakning
): VyData {
  const tillgangar = sorterade(
    b.fixed_assets_details,
    b.current_assets_details,
    b.receivables_details,
    b.bank_and_cash_details
  );
  const skulder = sorterade(
    b.equity_details,
    b.long_term_liabilities_details,
    b.current_liabilities_details
  );

  const summaSkulder = b.closing_equity_liabilities + r.profit;
  const differens = b.closing_assets - summaSkulder;

  const skuldrader = skulder.map((k) => kontorad(k, k.closing_balance));
  if (r.profit !== 0) {
    // Efter det sista eget kapital-kontot, före skulderna.
    const index = skulder.findIndex((k) => Number(k.code) >= 2100);
    const rad: VyRadData = {
      id: "arets-resultat",
      titel: "Årets resultat, ej bokfört",
      meta: "resultaträkningen",
      hoger: formatBeloppHela(r.profit),
    };
    skuldrader.splice(index === -1 ? skuldrader.length : index, 0, rad);
  }

  const vy: VyData = {
    lage: differens === 0 ? "normal" : "fel",
    status: differens === 0 ? "balanserar" : `differens ${formatBeloppHela(differens)}`,
    period: `${arsrubrik(ar)} · utgående balans`,
    sektioner: [
      {
        titel: "Tillgångar",
        rader: [
          ...tillgangar.map((k) => kontorad(k, k.closing_balance)),
          summarad("sum-t", "Summa tillgångar", b.closing_assets),
        ],
      },
      {
        titel: "Eget kapital och skulder",
        rader: [...skuldrader, summarad("sum-s", "Summa eget kapital och skulder", summaSkulder)],
      },
    ],
    fot: b.has_ib_vouchers
      ? "Ingående balanser från årets IB-verifikation."
      : "Ingående balanser räknade ur tidigare års verifikationer; året saknar IB-verifikation.",
  };

  if (differens !== 0) {
    vy.banner = {
      ton: "fel",
      text: `Tillgångarna och eget kapital och skulder skiljer sig med ${formatBeloppHela(differens)} kr.`,
    };
  }
  return vy;
}

/** Resultaträkningen för räkenskapsåret. Kostnader visas med minustecken. */
export function resultatVy(ar: OverviewFiscalYear, r: Resultatrakning): VyData {
  const sektioner: VySektionData[] = [];

  if (r.revenue_details.length > 0) {
    sektioner.push({
      titel: "Intäkter",
      rader: [
        ...r.revenue_details.map((k) => kontorad(k, k.amount)),
        summarad("sum-i", "Summa intäkter", r.revenue),
      ],
    });
  }
  if (r.cost_details.length > 0) {
    sektioner.push({
      titel: "Kostnader",
      rader: [
        ...r.cost_details.map((k) => kontorad(k, -k.amount)),
        summarad("sum-k", "Summa kostnader", -r.costs),
        summarad("rorelse", "Rörelseresultat", r.operating_profit),
      ],
    });
  }
  if (r.financial_details.length > 0) {
    sektioner.push({
      titel: "Finansiella poster",
      rader: [
        ...r.financial_details.map((k) => kontorad(k, -k.amount)),
        summarad("sum-f", "Summa finansiella poster", -r.financial),
      ],
    });
  }
  if (sektioner.length > 0) {
    sektioner.push({
      titel: "Resultat",
      rader: [summarad("res", "Årets resultat", r.profit)],
    });
  }

  const tomt = sektioner.length === 0;
  return {
    lage: tomt ? "tomt" : "normal",
    status: tomt
      ? "inget bokfört"
      : r.profit >= 0
        ? `vinst ${formatBeloppHela(r.profit)}`
        : `förlust ${formatBeloppHela(-r.profit)}`,
    period: `${arsrubrik(ar)} · ${r.voucher_count} verifikationer`,
    sektioner,
    fot: "Intäkter och kostnader bokförda under räkenskapsåret, klass 3–8.",
  };
}

function verifikationsrad(v: Verifikation): VyRadData {
  const nummer = `${v.series}-${v.number}`;
  const saknar = v.status === "posted" && v.missing_attachment === true;
  return {
    id: v.id,
    titel: v.description,
    meta: `${nummer} · ${v.date}${saknar ? " · saknar underlag" : ""}`,
    hoger: formatBeloppHela(v.total_debit),
    variant: v.status === "draft" ? "vantar" : saknar ? "saknar" : undefined,
  };
}

/** Utkasten överst, sedan de senast daterade postade verifikationerna. */
export function verifikationerVy(
  ar: OverviewFiscalYear,
  postade: Verifikationslista,
  utkast: Verifikationslista
): VyData {
  const sektioner: VySektionData[] = [];
  if (utkast.vouchers.length > 0) {
    sektioner.push({ titel: "Utkast", rader: utkast.vouchers.map(verifikationsrad) });
  }
  if (postade.vouchers.length > 0) {
    sektioner.push({
      titel: "Senast postade",
      rader: postade.vouchers.map(verifikationsrad),
    });
  }

  const tomt = sektioner.length === 0;
  const visade = postade.vouchers.length;
  return {
    lage: tomt ? "tomt" : utkast.total > 0 ? "vantar" : "normal",
    status: tomt
      ? "inga verifikationer"
      : utkast.total > 0
        ? `${utkast.total} utkast`
        : `${postade.total} postade`,
    period: `${arsrubrik(ar)} · ${postade.total} postade verifikationer`,
    sektioner,
    fot:
      visade < postade.total
        ? `Visar de ${visade} senaste. Alla finns i verifikationslistan.`
        : "Alla årets verifikationer visas.",
  };
}

// ─── Lägen medan data hämtas ──────────────────────────────────────────────

export const LADDAR_VY: VyData = {
  lage: "pagaende",
  status: "hämtar",
  period: "",
  sektioner: [],
  fot: "",
};

export const FEL_VY: VyData = {
  lage: "fel",
  status: "kunde inte läsas",
  period: "",
  banner: { ton: "fel", text: "Uppgifterna kunde inte hämtas från servern. Ladda om sidan." },
  sektioner: [],
  fot: "",
};

export const INGET_AR_VY: VyData = {
  lage: "tomt",
  status: "inget räkenskapsår",
  period: "",
  sektioner: [],
  fot: "Det finns inget räkenskapsår för dagens datum.",
};
