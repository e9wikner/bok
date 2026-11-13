/**
 * Revisionsloggen (modul `skal`, vyn `bocker.revisionslogg`).
 *
 * Behandlingshistoriken: varje skapad, bokförd, låst, kopplad eller ändrad
 * sak, vem som gjorde det och när. Nyast först, hundra åt gången, och hela
 * vägen bakåt (`GET /api/v1/audit/log` med `offset`). Bara läsning: loggen
 * skrivs av servern och kan inte ändras.
 */

import apiClient from "@/lib/api";
import { formatBeloppHela } from "@/lib/skal/format";
import type { VyLage } from "@/lib/skal/vydata";

export const REVISIONSLOGG_NYCKEL = ["skal", "revisionslogg"] as const;
export const SIDSTORLEK = 100;

export interface Logghandelse {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  actor: string;
  payload: Record<string, unknown> | null;
  timestamp: string;
}

export interface Loggsida {
  entries: Logghandelse[];
  offset: number;
  has_more: boolean;
}

/** Ett urval i filterraden och de entitetstyper det omfattar (tomt = alla). */
export interface Urval {
  key: string;
  titel: string;
  typer: readonly string[];
}

export const URVAL: readonly Urval[] = [
  { key: "alla", titel: "Allt", typer: [] },
  { key: "ver", titel: "Verifikationer", typer: ["voucher", "voucher_series", "transaction", "thread_draft"] },
  { key: "ar", titel: "Perioder och år", typer: ["period", "fiscal_year", "opening_balance", "bokslut_inputs"] },
  {
    key: "loner",
    titel: "Löner",
    typer: ["payroll_run", "payslip", "payroll_agi_booking", "employee", "employee_salary_setting"],
  },
  { key: "fakturor", titel: "Fakturor", typer: ["invoice", "invoice_draft", "credit_note", "payment"] },
];

export const revisionsloggApi = {
  sida: async (typer: readonly string[], offset: number, antal = SIDSTORLEK): Promise<Loggsida> => {
    const params = new URLSearchParams({ limit: String(antal), offset: String(offset) });
    for (const t of typer) params.append("entity_type", t);
    const { data } = await apiClient.get<Loggsida>(`/api/v1/audit/log?${params}`);
    return { entries: data?.entries ?? [], offset: data?.offset ?? offset, has_more: !!data?.has_more };
  },
};

const SAK: Record<string, string> = {
  voucher: "Verifikation",
  voucher_series: "Verifikationsserie",
  transaction: "Banktransaktion",
  thread_draft: "Verifikationsförslag",
  period: "Period",
  fiscal_year: "Räkenskapsår",
  opening_balance: "Ingående balans",
  bokslut_inputs: "Bokslutsuppgifter",
  payroll_run: "Lönekörning",
  payslip: "Lönebesked",
  payroll_agi_booking: "Arbetsgivardeklaration",
  employee: "Anställd",
  employee_salary_setting: "Lön",
  invoice: "Faktura",
  invoice_draft: "Fakturautkast",
  credit_note: "Kreditfaktura",
  payment: "Betalning",
  decision: "Beslut",
  thread: "Tråd",
};

export const HANDLING: Record<string, string> = {
  created: "skapad",
  updated: "ändrad",
  posted: "bokförd",
  booked: "bokförd",
  approved_and_booked: "godkänd och bokförd",
  sent: "skickad",
  issued: "utfärdad",
  registered: "registrerad",
  locked: "låst",
  unlocked: "upplåst",
  deleted: "borttagen",
  corrected: "rättad",
  rejected: "avvisad",
  dismissed: "avfärdat",
  context_reset: "nollställd",
  statement_linked: "kopplad till kontoutdrag",
  statement_unlinked: "bortkopplad från kontoutdrag",
  underlag_waived: "godkänd utan underlag",
  underlag_waiver_revoked: "godkännande utan underlag återkallat",
};

const AKTOR: Record<string, string> = {
  agent: "agenten",
  api: "API-nyckeln",
  sie4_import: "SIE4-import",
  statement_match: "kontoutdragsmatchningen",
  system: "systemet",
};

const text = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v : null);

/** Det som pekar ut saken: verifikationsnumret, perioden, året, namnet. */
export function identitet(h: Logghandelse): string | null {
  const p = h.payload ?? {};
  if (h.entity_type === "voucher" && text(p.series) && typeof p.number === "number") {
    return `${p.series}-${p.number}`;
  }
  if (h.entity_type === "payroll_run" && typeof p.year === "number" && typeof p.month === "number") {
    return `${p.year}-${String(p.month).padStart(2, "0")}`;
  }
  if (h.entity_type === "fiscal_year" || h.entity_type === "opening_balance") {
    return text(p.fiscal_year)?.replace(" - ", " – ") ?? null;
  }
  return text(p.period) ?? text(p.invoice_number) ?? text(p.name) ?? null;
}

/** "Verifikation A-121 bokförd". */
export function handelseText(h: Logghandelse): string {
  const sak = SAK[h.entity_type] ?? h.entity_type;
  const handling = HANDLING[h.action] ?? h.action;
  const id = identitet(h);
  return [sak, id, handling].filter(Boolean).join(" ");
}

/** "agenten · 14:32 · 8 700". Beloppet bara för en verifikation. */
export function handelseMeta(h: Logghandelse): string {
  const tid = new Date(h.timestamp);
  const klocka = Number.isNaN(tid.getTime())
    ? h.timestamp
    : tid.toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit" });
  const debet = h.payload?.total_debit;
  const belopp = h.entity_type === "voucher" && typeof debet === "number" && debet > 0 ? formatBeloppHela(debet) : null;
  return [aktorText(h.actor), klocka, belopp].filter(Boolean).join(" · ");
}

/** Vem som gjorde det, i ord: "agenten", "SIE4-import", annars namnet. */
export function aktorText(actor: string): string {
  return AKTOR[actor] ?? actor;
}

/** Verifikationen händelsen gäller, om den går att öppna. */
export function verifikationAv(h: Logghandelse): string | null {
  if (h.entity_type === "voucher") return h.entity_id;
  return text(h.payload?.voucher_id);
}

/** Händelserna per dag, i den ordning de kom (nyast först). */
export function perDag(handelser: Logghandelse[]): { dag: string; handelser: Logghandelse[] }[] {
  const dagar: { dag: string; handelser: Logghandelse[] }[] = [];
  for (const h of handelser) {
    const d = new Date(h.timestamp);
    const dag = Number.isNaN(d.getTime())
      ? h.timestamp.slice(0, 10)
      : d.toLocaleDateString("sv-SE", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    const sista = dagar[dagar.length - 1];
    if (sista && sista.dag === dag) sista.handelser.push(h);
    else dagar.push({ dag, handelser: [h] });
  }
  return dagar;
}

export function revisionsloggStatus(
  forsta: Loggsida | undefined,
  isError: boolean
): { text: string; lage: VyLage } {
  if (isError) return { text: "kunde inte läsas", lage: "fel" };
  if (!forsta) return { text: "hämtar…", lage: "normal" };
  const senaste = forsta.entries?.[0];
  if (!senaste) return { text: "inga händelser", lage: "tomt" };
  const d = new Date(senaste.timestamp);
  const nar = Number.isNaN(d.getTime())
    ? senaste.timestamp
    : d.toLocaleString("sv-SE", { dateStyle: "short", timeStyle: "short" });
  return { text: `senast ${nar}`, lage: "normal" };
}
