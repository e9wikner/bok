/**
 * Rapporter och Åtgärder ur riktiga data (modul `skal`).
 *
 * Rapporter listar räkenskapsåren och om de är låsta; själva rapporterna
 * tas fram per år i den gamla bokslutsvyn. Åtgärder är de öppna
 * avvikelserna från BFL-kontrollerna (`/api/v1/compliance/issues`).
 */

import apiClient from "@/lib/api";
import type { RadVariant, VyData, VyRadData } from "@/lib/skal/vydata";

// ─── API-svaren ───────────────────────────────────────────────────────────

export interface Rakenskapsar {
  id: string;
  start_date: string;
  end_date: string;
  locked: boolean;
  locked_at: string | null;
}

export interface Rakenskapsarslista {
  fiscal_years: Rakenskapsar[];
}

export interface Avvikelse {
  id: string;
  severity: string;
  title: string;
  description: string | null;
  recommendation: string | null;
  deadline: string | null;
}

export interface Avvikelselista {
  count: number;
  issues: Avvikelse[];
}

export const bokslutApi = {
  getRakenskapsar: async (): Promise<Rakenskapsarslista> => {
    const { data } = await apiClient.get<Rakenskapsarslista>("/api/v1/fiscal-years");
    return data;
  },

  getAvvikelser: async (): Promise<Avvikelselista> => {
    const { data } = await apiClient.get<Avvikelselista>("/api/v1/compliance/issues");
    return data;
  },
};

// ─── Rapporter ────────────────────────────────────────────────────────────

/** "2025" för ett kalenderår, annars "2015/16". */
export function arsnamn(ar: { start_date: string; end_date: string }): string {
  const fran = ar.start_date.slice(0, 4);
  const till = ar.end_date.slice(0, 4);
  return fran === till ? fran : `${fran}/${till.slice(2)}`;
}

export function rapporterVy(lista: Rakenskapsarslista): VyData {
  const ar = [...lista.fiscal_years].sort((a, b) => b.start_date.localeCompare(a.start_date));
  const lasta = ar.filter((a) => a.locked).length;

  const rader: VyRadData[] = ar.map((a) => ({
    id: a.id,
    titel: `Räkenskapsår ${arsnamn(a)}`,
    meta: `${a.start_date} – ${a.end_date}${a.locked && a.locked_at ? ` · låst ${a.locked_at.slice(0, 10)}` : ""}`,
    hoger: a.locked ? "låst" : "öppet",
  }));

  const tomt = rader.length === 0;
  return {
    lage: tomt ? "tomt" : "normal",
    status: tomt ? "inga räkenskapsår" : `${lasta} av ${ar.length} låsta`,
    period: tomt ? "" : `${arsnamn(ar[ar.length - 1])} – ${arsnamn(ar[0])}`,
    sektioner: tomt ? [] : [{ titel: "Räkenskapsår", rader }],
    fot: "Årsredovisning, deklaration och SIE-export tas tills vidare fram i den gamla bokslutsvyn.",
  };
}

// ─── Åtgärder ─────────────────────────────────────────────────────────────

const ALLVAR: Record<string, { text: string; variant?: RadVariant; ordning: number }> = {
  critical: { text: "kritisk", variant: "fel", ordning: 0 },
  error: { text: "fel", variant: "fel", ordning: 1 },
  warning: { text: "varning", variant: "vantar", ordning: 2 },
  info: { text: "info", ordning: 3 },
};

export function atgarderVy(lista: Avvikelselista): VyData {
  const allvar = (s: string) => ALLVAR[s] ?? { text: s, ordning: 4 };
  const issues = [...lista.issues].sort((a, b) => allvar(a.severity).ordning - allvar(b.severity).ordning);

  const rader: VyRadData[] = issues.map((i) => ({
    id: i.id,
    titel: i.title,
    meta: [i.recommendation ?? i.description, i.deadline ? `senast ${i.deadline.slice(0, 10)}` : null]
      .filter(Boolean)
      .join(" · "),
    hoger: allvar(i.severity).text,
    variant: allvar(i.severity).variant,
  }));

  const tomt = rader.length === 0;
  const allvarliga = issues.filter((i) => allvar(i.severity).variant === "fel").length;
  return {
    lage: tomt ? "tomt" : allvarliga > 0 ? "fel" : "vantar",
    status: tomt ? "inga registrerade" : `${rader.length} öppna`,
    period: "Öppna avvikelser från BFL-kontrollerna",
    sektioner: tomt ? [] : [{ titel: "Öppna", rader }],
    fot: "BFL-kontrollerna körs inte automatiskt. Listan visar det den senaste körningen sparade.",
  };
}
