/**
 * SRU-kopplingen (modul `skal`, vyn `bokslut.sru`).
 *
 * Vilket fält i INK2R varje konto summeras till, för det räkenskapsår som
 * är valt i headern. Varje konto har en standardkoppling ur BAS-tabellen
 * (`domain/sru_fields.py`); en koppling som sparas för året går före den.
 * Samma endpoints som den gamla /settings/sru-mappings-sidan
 * (`api/routes/sru_mappings.py`). SRU-filerna och INK2-raderna finns i
 * INK2-vyn.
 */

import apiClient from "@/lib/api";
import type { Konto } from "@/lib/skal/kontoplan";
import type { VyLage } from "@/lib/skal/vydata";

export const sruNyckel = (arId: string) => ["skal", "sru", arId] as const;
export const rorelseNyckel = (arId: string) => ["skal", "sru", arId, "rorelse"] as const;

export interface SruFalt {
  code: string;
  row: string;
  label: string;
  section: string;
  accounts: string;
}

interface Koppling {
  id: string | null;
  account_code: string;
  sru_field: string;
}

/** Ett kontos koppling: årets sparade, standarden, och den som gäller. */
export interface Kontokoppling {
  sparad: { id: string; falt: string } | null;
  standard: string | null;
  galler: string | null;
}

export interface SruData {
  falt: SruFalt[];
  /** Per kontonummer. Ett konto utan standard och utan sparad saknas. */
  kopplingar: Record<string, Kontokoppling>;
}

export const sruApi = {
  hamta: async (arId: string): Promise<SruData> => {
    const [falt, standard, sparade] = await Promise.all([
      apiClient.get<SruFalt[]>("/api/v1/sru-fields"),
      apiClient.get<Koppling[]>(`/api/v1/fiscal-years/${arId}/sru-mappings/default`),
      apiClient.get<Koppling[]>(`/api/v1/fiscal-years/${arId}/sru-mappings`),
    ]);
    return { falt: falt.data ?? [], kopplingar: slaIhop(standard.data ?? [], sparade.data ?? []) };
  },

  /** Kontona med en bokförd transaktion under året (`GET /accounts/with-transactions`). */
  kontonMedTransaktioner: async (arId: string): Promise<string[]> => {
    const { data } = await apiClient.get<{ codes?: string[] }>("/api/v1/accounts/with-transactions", {
      params: { fiscal_year_id: arId },
    });
    return data?.codes ?? [];
  },

  /** Sparar årets koppling för kontot (ersätter en tidigare). */
  koppla: async (arId: string, konto: string, falt: string): Promise<void> => {
    await apiClient.post(`/api/v1/fiscal-years/${arId}/sru-mappings`, { account_code: konto, sru_field: falt });
  },

  /** Tar bort årets koppling, så att standarden gäller. */
  anvandStandard: async (arId: string, kopplingId: string): Promise<void> => {
    await apiClient.delete(`/api/v1/fiscal-years/${arId}/sru-mappings/${kopplingId}`);
  },

  arvFranForegaende: async (arId: string): Promise<void> => {
    await apiClient.post(`/api/v1/fiscal-years/${arId}/sru-mappings/inherit-previous`);
  },

  aterstallStandard: async (arId: string): Promise<void> => {
    await apiClient.post(`/api/v1/fiscal-years/${arId}/sru-mappings/reset-default`);
  },
};

export function slaIhop(standard: Koppling[], sparade: Koppling[]): Record<string, Kontokoppling> {
  const ut: Record<string, Kontokoppling> = {};
  for (const s of standard) ut[s.account_code] = { sparad: null, standard: s.sru_field, galler: s.sru_field };
  for (const s of sparade) {
    const k = ut[s.account_code] ?? { sparad: null, standard: null, galler: null };
    ut[s.account_code] = { ...k, sparad: s.id ? { id: s.id, falt: s.sru_field } : null, galler: s.sru_field };
  }
  return ut;
}

/** "7410 Nettoomsättning" — fältets rad och namn, eller koden om den är okänd. */
export function faltText(falt: SruFalt[], kod: string | null): string {
  if (!kod) return "ingen koppling";
  const f = falt.find((x) => x.code === kod);
  return f ? `${f.row} ${f.label}` : kod;
}

/** En sparad koppling som skiljer sig från standarden. */
export function arAnpassad(k: Kontokoppling | undefined): boolean {
  return !!k?.sparad && k.sparad.falt !== k.standard;
}

/**
 * Kontona som visas. `medTransaktioner` är kontona med en bokförd transaktion
 * under året, eller null för alla konton; `baraAnpassade` begränsar till de
 * vars koppling skiljer sig från standarden. Båda villkoren gäller samtidigt.
 */
export function filtreraKonton(
  konton: Konto[],
  data: SruData,
  baraAnpassade: boolean,
  medTransaktioner: ReadonlySet<string> | null = null
): Konto[] {
  return konton.filter(
    (k) =>
      (!baraAnpassade || arAnpassad(data.kopplingar[k.code])) && (!medTransaktioner || medTransaktioner.has(k.code))
  );
}

export function sruStatus(data: SruData | undefined, isError: boolean, arId: string | null | undefined): { text: string; lage: VyLage } {
  if (arId === null) return { text: "inget räkenskapsår", lage: "tomt" };
  if (isError) return { text: "kunde inte läsas", lage: "fel" };
  if (!data) return { text: "hämtar…", lage: "normal" };
  const anpassade = Object.values(data.kopplingar).filter(arAnpassad).length;
  if (anpassade === 0) return { text: "standardkoppling", lage: "normal" };
  return { text: `${anpassade} anpassad${anpassade === 1 ? "" : "e"}`, lage: "normal" };
}
