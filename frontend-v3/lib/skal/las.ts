/**
 * Lås och lås upp räkenskapsår och perioder (modul `skal`).
 *
 * En period är en månad. Låst betyder att inget nytt kan bokföras i den;
 * postade verifikationer är oföränderliga oavsett. Agenten kan låsa men inte
 * låsa upp — upplåsningen kräver inloggad användare, och servern vägrar
 * agentens nyckel (`403 human_only`).
 */

import apiClient from "@/lib/api";

export interface Period {
  id: string;
  fiscal_year_id: string;
  year: number;
  month: number;
  start_date: string;
  end_date: string;
  locked: boolean;
  locked_at: string | null;
  locked_by: string | null;
}

export interface Periodlista {
  periods: Period[];
}

/** Det en låsknapp behöver: läget, vad den gäller och vad ett tryck gör. */
export interface LasData {
  last: boolean;
  /** "september 2026", "räkenskapsår 2025" — till knappens etikett. */
  vad: string;
  vaxla: () => Promise<void>;
}

export const lasApi = {
  getPerioder: async (fiscalYearId: string): Promise<Periodlista> => {
    const { data } = await apiClient.get<Periodlista>("/api/v1/periods", {
      params: { fiscal_year_id: fiscalYearId },
    });
    return data;
  },

  rakenskapsar: async (id: string, last: boolean): Promise<void> => {
    await apiClient.post(`/api/v1/fiscal-years/${encodeURIComponent(id)}/${last ? "lock" : "unlock"}`);
  },

  period: async (id: string, last: boolean): Promise<void> => {
    await apiClient.post(`/api/v1/periods/${encodeURIComponent(id)}/${last ? "lock" : "unlock"}`);
  },
};

const MANADER = [
  "januari", "februari", "mars", "april", "maj", "juni",
  "juli", "augusti", "september", "oktober", "november", "december",
];

/** `{year: 2026, month: 9}` → "september 2026". */
export function periodnamn(p: Pick<Period, "year" | "month">): string {
  return `${MANADER[p.month - 1] ?? p.month} ${p.year}`;
}

/** Serverns felkod som en kort mening bredvid knappen. */
export function lasfel(fel: unknown): string {
  const kod = (fel as { response?: { data?: { detail?: { code?: string } } } })?.response?.data?.detail?.code;
  switch (kod) {
    case "draft_vouchers_exist":
      return "utkast i perioden";
    case "fiscal_year_locked":
      return "året är låst";
    case "human_only":
      return "kräver inloggning";
    default:
      return "gick inte";
  }
}
