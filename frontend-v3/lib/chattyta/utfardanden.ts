/**
 * Den optimistiska raden för ett utfärdande (SPEC-fakturering-f1.md §10.2).
 *
 * Samma mönster som postningarna (`postningar.ts`): fakturakortets `Utfärda`
 * (i tråden) och vyn Fakturering (i läskolumnen) delar vilka förslag som
 * utfärdas just nu och vilka som nyss blev fakturor. Det bor i TanStack-cachen
 * under `UTFARDANDEN_NYCKEL`, aldrig hos servern: ingen `queryFn`, ingen
 * invalidering, och efter en omladdning visar vyn det servern svarar.
 */

import type { QueryClient } from "@tanstack/react-query";
import { NY_POSTNING_MS } from "@/lib/chattyta/postningar";

/** Utanför alla frågenycklar som invalideras. */
export const UTFARDANDEN_NYCKEL = ["utfardanden"] as const;

/** Vad vyn behöver medan fakturan inte finns, ögonblicksbild vid trycket. */
export interface UtfardandeForslag {
  kund: string;
  nummer: string;
  belopp: number;
  forfaller: string;
}

export type Utfardande =
  | { draftId: string; lage: "pagaende"; forslag: UtfardandeForslag | null }
  | {
      draftId: string;
      lage: "utfardad";
      forslag: UtfardandeForslag | null;
      /** Serverns faktura-id, eller `null` om svaret inte bar det. */
      invoiceId: string | null;
      /** `HH:MM`, klientens klocka vid svaret. */
      klockslag: string;
    };

const lista = (qc: QueryClient): Utfardande[] =>
  qc.getQueryData<Utfardande[]>(UTFARDANDEN_NYCKEL) ?? [];

const skriv = (qc: QueryClient, ut: Utfardande[]) =>
  qc.setQueryData<Utfardande[]>(UTFARDANDEN_NYCKEL, ut);

/** Trycket på `Utfärda`: raden står som `utfärdas…`, och förslaget lämnar Väntar. */
export function startaUtfardande(
  qc: QueryClient,
  draftId: string,
  forslag: UtfardandeForslag | null
): void {
  skriv(qc, [
    { draftId, lage: "pagaende", forslag },
    ...lista(qc).filter((u) => u.draftId !== draftId),
  ]);
}

/** `201` eller `draft_already_issued`: raden står som `ny` i `NY_POSTNING_MS`. */
export function utfardandeKlart(qc: QueryClient, draftId: string, invoiceId: string | null): void {
  const fore = lista(qc).find((u) => u.draftId === draftId);
  const nu = new Date();
  const tva = (n: number) => String(n).padStart(2, "0");
  const post: Utfardande = {
    draftId,
    lage: "utfardad",
    forslag: fore?.forslag ?? null,
    invoiceId,
    klockslag: `${tva(nu.getHours())}:${tva(nu.getMinutes())}`,
  };
  skriv(qc, [post, ...lista(qc).filter((u) => u.draftId !== draftId)]);
  setTimeout(() => {
    if (lista(qc).find((u) => u.draftId === draftId) === post) taBortUtfardande(qc, draftId);
  }, NY_POSTNING_MS);
}

/** Fel, eller ett svar vi aldrig fick: förslaget går tillbaka till Väntar. */
export function taBortUtfardande(qc: QueryClient, draftId: string): void {
  const fore = lista(qc);
  if (!fore.some((u) => u.draftId === draftId)) return;
  skriv(qc, fore.filter((u) => u.draftId !== draftId));
}
