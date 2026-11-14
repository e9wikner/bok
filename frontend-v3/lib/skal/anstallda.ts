/**
 * Anställda och deras löner (modul `skal`, vyn `installningar.anstallda`).
 *
 * Här ställs lönerna in: vem som är anställd, vad hen tjänar, skatten som
 * dras och arbetsgivaravgiften, och här skapas månadens lönekörning med ett
 * lönebesked per anställd. Inget av det bokför något — lönebeskeden bokförs
 * i Löner, med ett tryck i kortet agenten lägger fram. Samma endpoints som
 * den gamla /payroll-sidan (`api/routes/payroll.py`).
 */

import apiClient from "@/lib/api";
import type { PayrollEmployee, PayrollRun } from "@/lib/api";
import { LONER_NYCKEL } from "@/lib/chattyta/api";
import { formatBelopp } from "@/lib/skal/format";
import type { VyLage } from "@/lib/skal/vydata";

/**
 * Under `LONER_NYCKEL`, så att en ny anställd eller körning når Löner och
 * en bokföring i Löner når hit.
 */
export const ANSTALLDA_NYCKEL = [...LONER_NYCKEL, "anstallda"] as const;

/** Full arbetsgivaravgift; den som är ung eller äldre kan ha en lägre. */
export const STANDARD_AVGIFT_PROCENT = "31,42";
export const STANDARD_UTBETALNINGSDAG = 25;

export interface AnstalldUppgifter {
  name: string;
  personal_number: string | null;
  email: string | null;
  bank_account: string | null;
  active: boolean;
}

export interface LoneUppgifter {
  gross_monthly_salary: number;
  preliminary_tax: number;
  employer_fee_rate_bp: number;
  payment_day: number;
}

export const anstalldaApi = {
  lista: async (): Promise<PayrollEmployee[]> => {
    const { data } = await apiClient.get<{ employees: PayrollEmployee[] }>("/api/v1/payroll/employees");
    return data.employees;
  },

  skapa: async (u: AnstalldUppgifter): Promise<PayrollEmployee> => {
    const { data } = await apiClient.post<PayrollEmployee>("/api/v1/payroll/employees", u);
    return data;
  },

  andra: async (id: string, u: AnstalldUppgifter): Promise<PayrollEmployee> => {
    const { data } = await apiClient.put<PayrollEmployee>(`/api/v1/payroll/employees/${id}`, u);
    return data;
  },

  sattLon: async (id: string, l: LoneUppgifter): Promise<PayrollEmployee> => {
    const { data } = await apiClient.put<PayrollEmployee>(`/api/v1/payroll/employees/${id}/salary`, {
      ...l,
      employer_fee_amount: null,
      active: true,
    });
    return data;
  },

  /**
   * Skapar månadens körning och dess lönebesked i ett svep, som agentens
   * `skapa_lonekorning`. Misslyckas lönebeskeden tas den tomma körningen
   * bort igen, så att månaden inte blir upptagen av en körning utan besked.
   */
  skapaKorning: async (ar: number, manad: number, utbetalning: string): Promise<PayrollRun> => {
    const { data: korning } = await apiClient.post<PayrollRun>("/api/v1/payroll/runs", {
      year: ar,
      month: manad,
      payment_date: utbetalning,
    });
    try {
      const { data } = await apiClient.post<PayrollRun>(`/api/v1/payroll/runs/${korning.id}/generate`);
      return data;
    } catch (fel) {
      await apiClient.delete(`/api/v1/payroll/runs/${korning.id}`).catch(() => undefined);
      throw fel;
    }
  },
};

// ─── Tal in och ut ────────────────────────────────────────────────────────

/** "32 500,50" → 3250050 öre. Tomt eller ogiltigt → null. */
export function kronorTillOre(text: string): number | null {
  const t = text.replace(/[\s ]/g, "").replace(",", ".");
  if (t === "") return null;
  const n = Number(t);
  if (!Number.isFinite(n) || n < 0) return null;
  return Math.round(n * 100);
}

/** 3250050 öre → "32 500,50"; hela kronor utan decimaler: "32 500". */
export function oreTillKronor(ore: number): string {
  return formatBelopp(ore, ore % 100 === 0 ? 0 : 2);
}

/** "31,42" → 3142 baspunkter. Tomt eller ogiltigt → null. */
export function procentTillBp(text: string): number | null {
  const t = text.trim().replace(",", ".");
  if (t === "") return null;
  const n = Number(t);
  if (!Number.isFinite(n) || n < 0 || n > 100) return null;
  return Math.round(n * 100);
}

/** 3142 → "31,42". */
export function bpTillProcent(bp: number): string {
  return (bp / 100).toFixed(2).replace(".", ",");
}

/**
 * Utbetalningsdagen i månaden, flyttad till månadens sista dag när månaden
 * är kortare (25 → 25, 31 i februari → 28 eller 29). "YYYY-MM-DD".
 */
export function utbetalningsdatum(ar: number, manad: number, dag: number): string {
  const sista = new Date(Date.UTC(ar, manad, 0)).getUTCDate();
  const d = Math.min(Math.max(1, dag), sista);
  return `${ar}-${String(manad).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

/** Den utbetalningsdag de flesta aktiva anställda har; annars den 25:e. */
export function vanligasteUtbetalningsdag(anstallda: PayrollEmployee[]): number {
  const antal = new Map<number, number>();
  for (const a of anstallda) {
    const s = a.salary_setting;
    if (!a.active || !s?.active) continue;
    antal.set(s.payment_day, (antal.get(s.payment_day) ?? 0) + 1);
  }
  let basta = STANDARD_UTBETALNINGSDAG;
  let flest = 0;
  for (const [dag, n] of antal) {
    if (n > flest) [basta, flest] = [dag, n];
  }
  return basta;
}

/** Visar bara de fyra sista siffrorna i ett personnummer. */
export function maskeraPersonnummer(pnr: string | null | undefined): string | null {
  if (!pnr) return null;
  const siffror = pnr.replace(/\D/g, "");
  return siffror.length >= 4 ? `••••••-${siffror.slice(-4)}` : null;
}

/** Rubrikradens status: hur många som får lön, och vem som saknar inställning. */
export function anstalldaStatus(
  anstallda: PayrollEmployee[] | undefined,
  isError: boolean
): { text: string; lage: VyLage } {
  if (isError) return { text: "kunde inte läsas", lage: "fel" };
  if (!anstallda) return { text: "hämtar…", lage: "normal" };
  const aktiva = anstallda.filter((a) => a.active);
  if (aktiva.length === 0) return { text: "inga anställda", lage: "tomt" };
  const utanLon = aktiva.filter((a) => !a.salary_setting?.active).length;
  if (utanLon > 0) return { text: `${utanLon} utan lön inställd`, lage: "vantar" };
  return { text: `${aktiva.length} anställd${aktiva.length === 1 ? "" : "a"}`, lage: "normal" };
}

/** Serverns felmeddelande (`_validation_http`), annars en egen text. */
export function felText(fel: unknown, annars: string): string {
  const detail = (fel as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const d = detail as { error?: unknown; code?: unknown };
    if (d.code === "payroll_run_already_exists") return "Det finns redan en lönekörning för den månaden. Den står i Löner.";
    if (typeof d.error === "string") return d.error;
  }
  return annars;
}
