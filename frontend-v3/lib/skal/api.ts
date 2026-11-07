/**
 * Skalets läsvägar (modul `skal`).
 *
 * Två anrop, båda rena läsningar. Skalet skriver ingenting och räknar
 * ingenting — `waiting` och `meta` kommer färdigformulerade från servern
 * (datakontraktets regel 2, SPEC-oversikt.md §5).
 *
 * Återanvänder den befintliga axios-instansen i `lib/api.ts` med dess
 * token-interceptor. Den filen ändras inte.
 */

import apiClient from "@/lib/api";
import type { Sidnyckel } from "@/lib/skal/vyer";

export interface OverviewCounters {
  open_decisions: number;
  overdue_invoices: number;
  payroll_waiting: number;
  missing_attachments: number;
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

export interface Overview {
  fiscal_year: OverviewFiscalYear | null;
  period_state: OverviewPeriodState | null;
  pages: OverviewPage[];
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
  getOverview: async (): Promise<Overview> => {
    const { data } = await apiClient.get<Overview>("/api/v1/overview");
    return data;
  },

  getAgentStatus: async (): Promise<AgentStatus> => {
    const { data } = await apiClient.get<AgentStatus>("/api/v1/agent/status");
    return data;
  },
};
