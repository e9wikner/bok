/**
 * Den optimistiska raden (SPEC-flode-verifikationer.md §11.2, F14).
 *
 * Förslagskortets `Posta` (`usePostaUtkast`, i tråden) och vyn Verifikationer
 * (`useVyer`, i läskolumnen) är olika komponenter som delar en sak: vilka
 * utkast som postas just nu, och vilka som nyss blev postade. Den bor i
 * TanStack-cachen under `POSTNINGAR_NYCKEL`, så att båda når den genom samma
 * `QueryClient` och inget modulglobalt tillstånd läcker mellan tester.
 *
 * Posten är klientens, aldrig serverns: ingen `queryFn`, ingen invalidering
 * når den, och efter en omladdning finns den inte — vyn visar då vad servern
 * svarar (§11.2 sista punkten).
 */

import type { QueryClient } from "@tanstack/react-query";
import type { VerifikationSvar } from "@/lib/chattyta/api";

/** Utanför `VOUCHERS_NYCKEL`/`DRAFTS_NYCKEL`: ingen invalidering ska röra den. */
export const POSTNINGAR_NYCKEL = ["postningar"] as const;

/**
 * Samma varaktighet som `VyRad`s `ny`-markering (`NY_MARKERING_MS`); ett test
 * håller de två lika. Står här för att `lib` inte ska läsa en komponentfil.
 */
export const NY_POSTNING_MS = 6000;

/** Vad vyn behöver om utkastet medan numret inte finns, ögonblicksbild vid trycket. */
export interface PostningUtkast {
  titel: string;
  serie: string;
  belopp: number;
}

export type Postning =
  | { draftId: string; lage: "pagaende"; utkast: PostningUtkast | null }
  | {
      draftId: string;
      lage: "postad";
      utkast: PostningUtkast | null;
      /** Serverns verifikation; `null` bara vid `already_posted` utan bifogad verifikation. */
      verifikation: VerifikationSvar | null;
    };

const lista = (qc: QueryClient): Postning[] =>
  qc.getQueryData<Postning[]>(POSTNINGAR_NYCKEL) ?? [];

const skriv = (qc: QueryClient, ut: Postning[]) => qc.setQueryData<Postning[]>(POSTNINGAR_NYCKEL, ut);

/**
 * Utkastet som vyn senast såg det, ur vilken fråga under `["vouchers", …]`
 * som helst som har det. `null` om ingen har det (t.ex. i ett test utan vy).
 */
function utkastIVyn(qc: QueryClient, draftId: string): PostningUtkast | null {
  for (const [, data] of qc.getQueriesData<{ vouchers?: unknown }>({ queryKey: ["vouchers"] })) {
    const vouchers = (data as { vouchers?: unknown } | undefined)?.vouchers;
    if (!Array.isArray(vouchers)) continue;
    const v = vouchers.find((x) => (x as { id?: unknown })?.id === draftId) as
      | { description?: string; series?: string; total_debit?: number }
      | undefined;
    if (v) return { titel: v.description ?? "", serie: v.series ?? "", belopp: v.total_debit ?? 0 };
  }
  return null;
}

/** Trycket på `Posta`: raden läggs överst i Postade, och händelsen lämnar Väntar. */
export function startaPostning(qc: QueryClient, draftId: string): void {
  const utkast = utkastIVyn(qc, draftId);
  skriv(qc, [
    { draftId, lage: "pagaende", utkast },
    ...lista(qc).filter((p) => p.draftId !== draftId),
  ]);
}

/**
 * `200`, uppspelning eller `already_posted`: raden byts mot serverns
 * verifikation på samma nyckel och står som `ny` i `NY_POSTNING_MS`.
 * Därefter tas posten bort; vyns egen lista har verifikationen då.
 */
export function postningKlar(
  qc: QueryClient,
  draftId: string,
  verifikation: VerifikationSvar | null
): void {
  const fore = lista(qc).find((p) => p.draftId === draftId);
  const post: Postning = { draftId, lage: "postad", utkast: fore?.utkast ?? null, verifikation };
  skriv(qc, [post, ...lista(qc).filter((p) => p.draftId !== draftId)]);
  setTimeout(() => {
    // Bara om det är samma post: ett nytt tryck under tiden äger raden.
    if (lista(qc).find((p) => p.draftId === draftId) === post) taBortPostning(qc, draftId);
  }, NY_POSTNING_MS);
}

/** Fel, eller ett svar vi aldrig fick: händelsen går tillbaka till Väntar. */
export function taBortPostning(qc: QueryClient, draftId: string): void {
  const fore = lista(qc);
  if (!fore.some((p) => p.draftId === draftId)) return;
  skriv(qc, fore.filter((p) => p.draftId !== draftId));
}
