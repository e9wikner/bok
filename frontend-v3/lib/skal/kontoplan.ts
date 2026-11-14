/**
 * Kontoplanen (modul `skal`, vyn `installningar.kontoplan`).
 *
 * BAS-kontona som bokföringen använder, grupperade per kontoklass, med
 * momskod och SRU-kod. Bara läsning: ett konto läggs till av agenten eller
 * genom en SIE4-import. Samma endpoint som den gamla /accounts-sidan
 * (`GET /api/v1/accounts`).
 */

import apiClient from "@/lib/api";
import type { VyLage } from "@/lib/skal/vydata";

export const KONTOPLAN_NYCKEL = ["skal", "kontoplan"] as const;

export interface Konto {
  code: string;
  name: string;
  account_type: string;
  vat_code?: string | null;
  sru_code?: string | null;
  active: boolean;
}

export const kontoplanApi = {
  lista: async (): Promise<Konto[]> => {
    const { data } = await apiClient.get<{ accounts: Konto[] }>("/api/v1/accounts");
    return data?.accounts ?? [];
  },
};

/** BAS kontoklasser, efter första siffran. */
const KLASSER: Record<string, string> = {
  "1": "Tillgångar",
  "2": "Eget kapital och skulder",
  "3": "Rörelsens inkomster",
  "4": "Material och varor",
  "5": "Övriga externa kostnader",
  "6": "Övriga externa kostnader",
  "7": "Personal, av- och nedskrivningar",
  "8": "Finansiella poster, bokslut och skatt",
};

export interface Kontoklass {
  klass: string;
  titel: string;
  konton: Konto[];
}

/**
 * Kontona i klassordning (1–8), sorterade på nummer inom klassen. Klass 5
 * och 6 har samma rubrik i BAS och slås ihop. Med en sökterm finns bara de
 * konton kvar vars nummer börjar med termen eller vars namn innehåller den.
 */
export function kontoklasser(konton: Konto[], sok = ""): Kontoklass[] {
  const term = sok.trim().toLowerCase();
  const traffar = term
    ? konton.filter((k) => k.code.startsWith(term) || k.name.toLowerCase().includes(term))
    : konton;
  const grupper = new Map<string, Kontoklass>();
  for (const k of [...traffar].sort((a, b) => a.code.localeCompare(b.code))) {
    const forsta = k.code[0] ?? "?";
    const titel = KLASSER[forsta] ?? "Övriga konton";
    const nyckel = forsta === "6" ? "5" : forsta;
    const g = grupper.get(nyckel) ?? { klass: nyckel === "5" ? "5–6" : nyckel, titel, konton: [] };
    g.konton.push(k);
    grupper.set(nyckel, g);
  }
  return [...grupper.values()];
}

/** Kontots metarad: moms- och SRU-kod, när de finns. */
export function kontoMeta(k: Konto): string {
  return [k.vat_code ? `moms ${k.vat_code}` : null, k.sru_code ? `SRU ${k.sru_code}` : null]
    .filter(Boolean)
    .join(" · ");
}

export function kontoplanStatus(konton: Konto[] | undefined, isError: boolean): { text: string; lage: VyLage } {
  if (isError) return { text: "kunde inte läsas", lage: "fel" };
  if (!konton) return { text: "hämtar…", lage: "normal" };
  if (konton.length === 0) return { text: "inga konton", lage: "tomt" };
  return { text: `${konton.length} konton`, lage: "normal" };
}
