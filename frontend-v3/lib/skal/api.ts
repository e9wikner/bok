/**
 * Skalets läsvägar (modul `skal`).
 *
 * Två anrop, båda rena läsningar. Skalet skriver ingenting och räknar
 * ingenting — `waiting` och `meta` kommer färdigformulerade från servern
 * (datakontraktets regel 2).
 *
 * Återanvänder den befintliga axios-instansen i `lib/api.ts` med dess
 * token-interceptor. Den filen ändras inte.
 */

import apiClient from "@/lib/api";
import type { Sidnyckel, ViewKey, Vynyckel } from "@/lib/skal/vyer";

export interface OverviewCounters {
  open_decisions: number;
  overdue_invoices: number;
  payroll_waiting: number;
  missing_attachments: number;
  /** Bokslutets kontroller som återstår (fel och varningar). */
  closing_checks: number;
}

export interface OverviewPage {
  key: Sidnyckel;
  title: string;
  /** Serverns beslut, inte klientens. Driver pricken i väljaren. */
  waiting: boolean;
  /** Serverns formulering, på svenska. Klienten renderar den ordagrant. */
  meta: string;
  counters: OverviewCounters;
}

export interface OverviewFiscalYear {
  id: string;
  label: string;
  start: string;
  end: string;
}

export interface OverviewPeriodState {
  current_period_id: string;
  label: string;
  locked: boolean;
}

/** Hur mycket som väntar på människan i en vy (flik), i det räknade året. */
export interface OverviewVy {
  key: ViewKey;
  waiting: number;
}

/**
 * Bokslutets kontroller som är kvar att åtgärda i en vy (Uppgifter, INK2 …),
 * med serverns formulering. Visas under vyn, där det görs.
 */
export interface OverviewBokslutVy {
  key: Vynyckel;
  waiting: number;
  meta: string;
}

/** Ett annat räkenskapsår där något väntar på människan. */
export interface OverviewAnnatAr {
  id: string;
  label: string;
  waiting: number;
  /** Serverns formulering: "2 väntar på dig". */
  meta: string;
}

export interface Overview {
  /** Innevarande år, vilket år som än räknas. */
  fiscal_year: OverviewFiscalYear | null;
  period_state: OverviewPeriodState | null;
  /** Sidornas räknare gäller detta år (det valda, annars innevarande). */
  pages: OverviewPage[];
  counted_fiscal_year_id?: string | null;
  views?: OverviewVy[];
  other_years?: OverviewAnnatAr[];
  closing_views?: OverviewBokslutVy[];
}

/** Fyra lägen; `vilande` ritas som ingen indikator alls (api/schemas.py). */
export type AgentState = "arbetar" | "postar" | "pausad" | "vilande";

export interface AgentStatus {
  state: AgentState;
  since: string | null;
  current_task: string | null;
  paused_reason: string | null;
}

export const skalApi = {
  /** Räknarna för `fiscalYearId`; utan det för innevarande år. */
  getOverview: async (fiscalYearId?: string | null): Promise<Overview> => {
    const { data } = await apiClient.get<Overview>("/api/v1/overview", {
      params: fiscalYearId ? { fiscal_year_id: fiscalYearId } : undefined,
    });
    return data;
  },

  getAgentStatus: async (): Promise<AgentStatus> => {
    const { data } = await apiClient.get<AgentStatus>("/api/v1/agent/status");
    return data;
  },

  /** Serverns version och commit, till sidonavigeringens fot. */
  getVersion: async (): Promise<string | null> => {
    const { data } = await apiClient.get<{ version?: string; commit?: string }>("/api/v1/health");
    return [data?.version, data?.commit].filter(Boolean).join(" · ") || null;
  },
};
