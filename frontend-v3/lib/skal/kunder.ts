/**
 * Kunder och artiklar (modul `skal`, vyn `betala.kunder`).
 *
 * Registren fakturorna skrivs ur: kunden med adress och betalningsvillkor,
 * artikeln med pris, moms och intäktskonto. Agenten läser dem
 * (`las_kunder`) när den lägger fram en faktura. Samma endpoints som de
 * gamla /invoices/customers- och /invoices/articles-sidorna.
 */

import apiClient from "@/lib/api";
import { FAKTUROR_NYCKEL } from "@/lib/chattyta/api";
import type { VyLage } from "@/lib/skal/vydata";

/** Under fakturornas nyckel: en ny kund ska synas där fakturorna skrivs. */
export const KUNDER_NYCKEL = [...FAKTUROR_NYCKEL, "kunder"] as const;
export const ARTIKLAR_NYCKEL = [...FAKTUROR_NYCKEL, "artiklar"] as const;

export interface Kund {
  id: string;
  name: string;
  org_number: string | null;
  email: string | null;
  address: string | null;
  payment_terms_days: number;
}

export interface Artikel {
  id: string;
  article_number: string;
  name: string;
  unit: string;
  unit_price: number;
  vat_code: string;
  revenue_account: string;
}

export const MOMSKODER: readonly { kod: string; text: string }[] = [
  { kod: "MP1", text: "25 %" },
  { kod: "MP2", text: "12 %" },
  { kod: "MP3", text: "6 %" },
  { kod: "MF", text: "momsfri" },
];

export const kunderApi = {
  kunder: async (): Promise<Kund[]> => {
    const { data } = await apiClient.get<{ customers?: Kund[] }>("/api/v1/customers");
    return data?.customers ?? [];
  },
  skapaKund: async (k: Omit<Kund, "id">): Promise<Kund> => {
    const { data } = await apiClient.post<Kund>("/api/v1/customers", k);
    return data;
  },
  artiklar: async (): Promise<Artikel[]> => {
    const { data } = await apiClient.get<{ articles?: Artikel[] }>("/api/v1/articles");
    return data?.articles ?? [];
  },
  skapaArtikel: async (a: Omit<Artikel, "id">): Promise<Artikel> => {
    const { data } = await apiClient.post<Artikel>("/api/v1/articles", a);
    return data;
  },
};

/** "556000-0001 · 30 dagar · faktura@x.se". */
export function kundMeta(k: Kund): string {
  return [k.org_number, `${k.payment_terms_days} dagar`, k.email].filter(Boolean).join(" · ");
}

export function momsText(kod: string): string {
  return MOMSKODER.find((m) => m.kod === kod)?.text ?? kod;
}

/** "A1 · per h · moms 25 % · 3011". */
export function artikelMeta(a: Artikel): string {
  return [a.article_number, `per ${a.unit}`, `moms ${momsText(a.vat_code)}`, a.revenue_account].join(" · ");
}

/** Kronor som text → öre, eller null om det inte är ett belopp. */
export function kronorTillOre(text: string): number | null {
  const t = text.replace(/\s/g, "").replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return null;
  return Math.round(Number(t) * 100);
}

export function kunderStatus(
  kunder: Kund[] | undefined,
  artiklar: Artikel[] | undefined,
  isError: boolean
): { text: string; lage: VyLage } {
  if (isError) return { text: "kunde inte läsas", lage: "fel" };
  if (!kunder || !artiklar) return { text: "hämtar…", lage: "normal" };
  if (kunder.length === 0) return { text: "inga kunder", lage: "tomt" };
  const k = kunder.length === 1 ? "1 kund" : `${kunder.length} kunder`;
  const a = artiklar.length === 1 ? "1 artikel" : `${artiklar.length} artiklar`;
  return { text: `${k} · ${a}`, lage: "normal" };
}
