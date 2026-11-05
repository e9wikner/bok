/**
 * Rapporter och Åtgärder ur riktiga data (modul `skal`).
 *
 * Rapporter listar räkenskapsåren med ett lås per år. Årets rad öppnar
 * bokslutet (`components/skal/BokslutLager.tsx`, `GET /api/v1/bokslut/{id}`):
 * kontrollerna, INK2, momsdeklarationen, årsredovisningen och filerna att
 * ladda ner. Åtgärder är de öppna avvikelserna från BFL-kontrollerna
 * (`/api/v1/compliance/issues`).
 */

import apiClient from "@/lib/api";
import type { LasData } from "@/lib/skal/las";
import { formatBeloppHela } from "@/lib/skal/format";
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

// ─── Bokslutet (`api/routes/bokslut.py`) ──────────────────────────────────

export type KontrollNiva = "ok" | "info" | "varning" | "fel";

export interface Kontroll {
  id: string;
  niva: KontrollNiva;
  titel: string;
  text: string;
}

export interface Ink2Rad {
  code: string;
  label: string;
  sru_fields: string[];
  sign: string | null;
  value: number | null;
  source_accounts: { account: string; name: string; value: number }[];
}

export interface Ink2 {
  tabs: { id: string; label: string; description: string }[];
  summary: { accounting_result: number; taxable_result: number };
  sections: Record<string, { title: string; rows: Ink2Rad[] }[]>;
  validation: { errors: string[]; warnings: string[]; is_valid: boolean };
}

export interface Justering {
  code: string;
  row: string;
  label: string;
  value: number;
  calculated: number;
  override: number | null;
  basis: string;
  sources: { account: string; name: string; value: number }[];
}

export interface Skatt {
  overskott: number;
  underskott: number;
  underlag: number;
  beraknad_skatt: number;
  bokford_skatt: number;
  differens: number;
  slr_procent: number | null;
  slr_kalla: string;
  justeringar: Justering[];
  periodiseringsfonder: {
    account: string;
    name: string;
    avsattningsar: number | null;
    opening: number;
    closing: number;
    reversed: number;
    allocated: number;
  }[];
  max_avsattning_periodiseringsfond: number;
  bokford_avsattning: number;
  ej_avdragsgilla_konton: string[];
  skattefria_konton: string[];
}

export interface MomsRuta {
  box: string;
  label: string;
  amount: number;
  amount_sek: number;
  sources: { account_code: string; account_name: string; amount_sek: number }[];
}

export interface Moms {
  period: string;
  boxes: MomsRuta[];
  warnings?: string[];
  summary: { net_vat_sek: number; action: string };
}

/** Två kolumner: i år och föregående år. `null` = saknas. */
export type Par = [number | null, number | null];

export interface ArRad {
  key: string;
  label: string;
  not: string | null;
  belopp: Par;
}

export interface Arsredovisning {
  company: { name: string; org_number: string; seat: string };
  period: { start: string; end: string };
  prior_period: { start: string; end: string };
  forvaltningsberattelse: {
    verksamhet: string | null;
    vasentliga_handelser: string | null;
    flerarsoversikt: {
      ar: string;
      nettoomsattning: number | null;
      resultat_efter_finansiella: number | null;
      balansomslutning: number | null;
      soliditet: number | null;
    }[];
    eget_kapital: { kolumner: string[]; rader: { label: string; belopp: number[] }[] };
    vinstdisposition: {
      balanserat_resultat: number;
      arets_resultat: number;
      summa: number;
      utdelning: number;
      i_ny_rakning: number;
    };
  };
  resultatrakning: {
    sektioner: { titel: string; rader: ArRad[]; summa: Par | null }[];
    arets_resultat: Par;
  };
  balansrakning: {
    tillgangar: { titel: string; grupper: { titel: string; rader: ArRad[]; summa: Par }[]; summa: Par }[];
    summa_tillgangar: Par;
    eget_kapital: {
      bundet: { rader: ArRad[]; summa: Par };
      fritt: { rader: ArRad[]; summa: Par };
      summa: Par;
    };
    skulder: { titel: string; rader: ArRad[]; summa: Par }[];
    summa_ek_skulder: Par;
    fritt_eget_kapital: Par;
  };
  noter: {
    personal: { medeltal_anstallda: [number | null, number | null] };
  };
  underskrifter: { ort: string | null; datum: string | null; personer: { namn: string; roll: string }[] };
  missing: { key: string; label: string }[];
  warnings: string[];
}

export interface Nedladdning {
  id: string;
  grupp: string;
  label: string;
  beskrivning: string;
  url: string;
}

export type Uppgifter = Record<string, unknown>;

export interface Bokslut {
  fiscal_year: { id: string; start: string; end: string; locked: boolean };
  company: { name: string; org_number: string };
  kontroller: Kontroll[];
  ink2: Ink2;
  skatt: Skatt;
  moms: Moms;
  arsredovisning: Arsredovisning;
  uppgifter: Uppgifter;
  uppgifter_schema: { key: string; label: string }[];
  nedladdningar: Nedladdning[];
}

export const bokslutApi = {
  getBokslut: async (arId: string): Promise<Bokslut> => {
    const { data } = await apiClient.get<Bokslut>(`/api/v1/bokslut/${encodeURIComponent(arId)}`);
    return data;
  },

  sparaUppgifter: async (arId: string, values: Uppgifter): Promise<Uppgifter> => {
    const { data } = await apiClient.post<{ values: Uppgifter }>(
      `/api/v1/bokslut/${encodeURIComponent(arId)}/uppgifter`,
      { values }
    );
    return data.values;
  },

  /** Filen som blob, med serverns filnamn (bearer krävs, se AGENTS.md). */
  hamtaFil: async (url: string): Promise<{ blob: Blob; filnamn: string }> => {
    const response = await apiClient.get(url, { responseType: "blob" });
    const disposition: string | undefined = response.headers?.["content-disposition"];
    const match = disposition?.match(/filename="?([^";]+)"?/);
    return { blob: response.data as Blob, filnamn: match ? match[1] : url.split("/").pop() ?? "fil" };
  },

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

/**
 * `las` ger varje år sitt lås. Utan den visar raden läget i text, som
 * innan låset fanns.
 */
export function rapporterVy(
  lista: Rakenskapsarslista,
  las?: (ar: Rakenskapsar) => LasData
): VyData {
  const ar = [...lista.fiscal_years].sort((a, b) => b.start_date.localeCompare(a.start_date));
  const lasta = ar.filter((a) => a.locked).length;

  const rader: VyRadData[] = ar.map((a) => ({
    id: a.id,
    titel: `Räkenskapsår ${arsnamn(a)}`,
    meta: `${a.start_date} – ${a.end_date}${a.locked && a.locked_at ? ` · låst ${a.locked_at.slice(0, 10)}` : ""}`,
    hoger: las ? "" : a.locked ? "låst" : "öppet",
    las: las?.(a),
    mal: { typ: "bokslut", arId: a.id },
  }));

  const tomt = rader.length === 0;
  return {
    lage: tomt ? "tomt" : "normal",
    status: tomt ? "inga räkenskapsår" : `${lasta} av ${ar.length} låsta`,
    period: tomt ? "" : `${arsnamn(ar[ar.length - 1])} – ${arsnamn(ar[0])}`,
    sektioner: tomt ? [] : [{ titel: "Räkenskapsår", rader }],
    fot: "Öppna ett år för bokslutet: kontroller, inkomstdeklaration, momsdeklaration och årsredovisning, med filerna att ladda ner.",
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

// ─── Bokslutets sammanfattning ────────────────────────────────────────────

/** Hela kronor → "1 139 320", med designens minustecken. */
export function kronor(v: number | null | undefined): string {
  if (v === null || v === undefined) return "–";
  return formatBeloppHela(v * 100);
}

/** Det som ska göras innan bokslutet är klart: fel och varningar. */
export function attAtgarda(k: readonly Kontroll[]): Kontroll[] {
  return k.filter((x) => x.niva === "fel" || x.niva === "varning");
}

/** "Bokslut 2025": årets namn som i Rapporter. */
export function bokslutTitel(b: Bokslut): string {
  return `Bokslut ${arsnamn({ start_date: b.fiscal_year.start, end_date: b.fiscal_year.end })}`;
}

/** Statusraden i bokslutets rubrik. */
export function bokslutStatus(b: Bokslut): { text: string; lage: VyData["lage"] } {
  const kvar = attAtgarda(b.kontroller);
  if (kvar.some((k) => k.niva === "fel")) return { text: `${kvar.length} att åtgärda`, lage: "fel" };
  if (kvar.length > 0) return { text: `${kvar.length} att åtgärda`, lage: "vantar" };
  return { text: b.fiscal_year.locked ? "klart · låst" : "klart", lage: "klart" };
}

/** Ett INK2S-fält: det angivna beloppet om ett finns, annars det beräknade. */
export function justeringsText(j: Justering): string {
  if (j.override === null || j.override === j.calculated) return j.basis;
  return `angivet för hand · beräknat ${kronor(j.calculated)}`;
}
