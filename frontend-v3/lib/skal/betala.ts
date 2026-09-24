/**
 * Fakturering och Löner ur riktiga data (modul `skal`).
 *
 * Båda är läsvyer (SPEC-skal.md §11): skrivning sker tills vidare i de
 * gamla vyerna, och det säger fottexten.
 */

import apiClient from "@/lib/api";
import { formatBeloppHela } from "@/lib/skal/format";
import type { VyData, VyRadData, VySektionData } from "@/lib/skal/vydata";

// ─── API-svaren ───────────────────────────────────────────────────────────

export interface Faktura {
  id: string;
  invoice_number: string | number | null;
  customer_name: string | null;
  invoice_date: string;
  due_date: string;
  amount_inc_vat: number;
  remaining_amount: number;
  status: string;
  is_overdue: boolean;
}

export interface Fakturalista {
  total: number;
  invoices: Faktura[];
}

export interface Lonekorning {
  id: string;
  year: number;
  month: number;
  payment_date: string | null;
  status: string;
  payslip_count: number;
  total_gross_salary: number;
  total_net_salary: number;
}

export interface Lonekorningar {
  payroll_runs: Lonekorning[];
}

export const betalaApi = {
  getFakturor: async (): Promise<Fakturalista> => {
    const { data } = await apiClient.get<Fakturalista>("/api/v1/invoices");
    return data;
  },

  getLonekorningar: async (): Promise<Lonekorningar> => {
    const { data } = await apiClient.get<Lonekorningar>("/api/v1/payroll/runs");
    return data;
  },
};

// ─── Fakturering ──────────────────────────────────────────────────────────

/** Så många betalda fakturor visas. */
export const BETALDA_ANTAL = 10;

const OBETALD = new Set(["sent", "partially_paid", "overdue"]);

function fakturarad(f: Faktura): VyRadData {
  const nummer = f.invoice_number ?? "utan nummer";
  const forfallen = f.status !== "paid" && f.is_overdue;
  let meta: string;
  if (f.status === "draft") meta = `${nummer} · utkast`;
  else if (f.status === "paid") meta = `${nummer} · betald`;
  else if (forfallen) meta = `${nummer} · förföll ${f.due_date}`;
  else meta = `${nummer} · förfaller ${f.due_date}`;
  return {
    id: f.id,
    titel: f.customer_name ?? "Okänd kund",
    meta,
    hoger: formatBeloppHela(f.status === "paid" ? f.amount_inc_vat : f.remaining_amount),
    variant: forfallen ? "fel" : f.status === "draft" ? "vantar" : undefined,
  };
}

export function faktureringVy(lista: Fakturalista): VyData {
  const nyast = (a: Faktura, b: Faktura) => b.invoice_date.localeCompare(a.invoice_date);
  const obetalda = lista.invoices.filter((f) => OBETALD.has(f.status));
  const utkast = lista.invoices.filter((f) => f.status === "draft");
  const betalda = lista.invoices
    .filter((f) => f.status === "paid")
    .sort(nyast)
    .slice(0, BETALDA_ANTAL);
  const forfallna = obetalda.filter((f) => f.is_overdue).length;

  const sektioner: VySektionData[] = [];
  if (obetalda.length > 0) {
    sektioner.push({
      titel: "Obetalda",
      rader: obetalda.sort((a, b) => a.due_date.localeCompare(b.due_date)).map(fakturarad),
    });
  }
  if (utkast.length > 0) sektioner.push({ titel: "Utkast", rader: utkast.sort(nyast).map(fakturarad) });
  if (betalda.length > 0) sektioner.push({ titel: "Senast betalda", rader: betalda.map(fakturarad) });

  const tomt = sektioner.length === 0;
  return {
    lage: tomt ? "tomt" : forfallna > 0 ? "vantar" : "normal",
    status: tomt
      ? "inga fakturor"
      : forfallna > 0
        ? `${forfallna} förfallen${forfallna > 1 ? "a" : ""}`
        : `${obetalda.length} obetald${obetalda.length === 1 ? "" : "a"}`,
    period: `${lista.total} fakturor i systemet`,
    sektioner,
    fot: "Agenten svarar på frågor om fakturorna. Skicka och kreditera görs tills vidare i den gamla fakturavyn.",
  };
}

// ─── Löner ────────────────────────────────────────────────────────────────

/** Så många lönekörningar visas. */
export const LONEKORNINGAR_ANTAL = 12;

const LONESTATUS: Record<string, string> = {
  draft: "utkast",
  generated: "lönebesked skapade",
  booked: "bokförd",
};

const MANAD = [
  "januari", "februari", "mars", "april", "maj", "juni",
  "juli", "augusti", "september", "oktober", "november", "december",
];

export function lonerVy(lista: Lonekorningar): VyData {
  const korningar = [...lista.payroll_runs]
    .sort((a, b) => b.year - a.year || b.month - a.month)
    .slice(0, LONEKORNINGAR_ANTAL);
  const oklara = korningar.filter((k) => k.status !== "booked").length;

  const rader: VyRadData[] = korningar.map((k) => ({
    id: k.id,
    titel: `${MANAD[k.month - 1] ?? k.month} ${k.year}`,
    meta: [
      LONESTATUS[k.status] ?? k.status,
      `${k.payslip_count} lönebesked`,
      k.payment_date ? `utbetalning ${k.payment_date}` : null,
    ]
      .filter(Boolean)
      .join(" · "),
    hoger: formatBeloppHela(k.total_gross_salary),
    variant: k.status === "booked" ? undefined : "vantar",
  }));

  const tomt = rader.length === 0;
  return {
    lage: tomt ? "tomt" : oklara > 0 ? "vantar" : "normal",
    status: tomt ? "inga lönekörningar" : oklara > 0 ? `${oklara} ej bokförd${oklara > 1 ? "a" : ""}` : "alla bokförda",
    period: tomt ? "Bruttolön per körning" : `${lista.payroll_runs.length} lönekörningar · bruttolön`,
    sektioner: tomt ? [] : [{ titel: "Lönekörningar", rader }],
    fot: "Agenten svarar på frågor om lönerna. Godkännande görs tills vidare i den gamla lönevyn.",
  };
}
