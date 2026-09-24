/**
 * Headerns räkenskapsårsrad.
 *
 * Fälten är serverns (`GET /api/v1/overview`); sammansättningen är
 * klientens formatering, inte en uträkning. Skalet räknar ingenting —
 * det enda som händer här är att två färdiga fält sätts ihop med ` · `,
 * som i designen: "Räkenskapsår 2026 · juni öppen".
 */

import type { Overview } from "@/lib/skal/api";

const MANADER = [
  "januari", "februari", "mars", "april", "maj", "juni",
  "juli", "augusti", "september", "oktober", "november", "december",
];

/** "2026-06" → "juni". Okänt format lämnas som det är. */
export function manadsnamn(periodLabel: string): string {
  const m = /^\d{4}-(\d{2})$/.exec(periodLabel);
  if (!m) return periodLabel;
  return MANADER[Number(m[1]) - 1] ?? periodLabel;
}

export function arsrad(overview?: Overview): string {
  if (!overview?.fiscal_year) return "";
  const ar = `Räkenskapsår ${overview.fiscal_year.label}`;
  const p = overview.period_state;
  if (!p) return ar;
  return `${ar} · ${manadsnamn(p.label)} ${p.locked ? "låst" : "öppen"}`;
}
