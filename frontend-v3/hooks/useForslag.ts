"use client";

/**
 * Förslagens status i en vy (SPEC-flode-verifikationer.md §10).
 *
 * Samma mönster som besluten (`useBeslut`, SPEC-chattyta.md §7): `draft`-
 * inlägget ändras aldrig, så om förslaget redan är postat eller ersatt vet
 * bara `GET /drafts`. Klienten läser vyns hela lista EN gång (`status=all`)
 * och slår upp `draft_id` lokalt. Varje förslagskort anropar hooken, men
 * nyckeln är vyns, så TanStack Query ger ett anrop per vy.
 */

import { useQuery } from "@tanstack/react-query";
import {
  DRAFTS_NYCKEL,
  hamtaForslag,
  type ForslagListSvar,
  type ForslagStatusSvar,
} from "@/lib/chattyta/api";

/** Serverns tak (`api/routes/drafts.py`, `le=200`). */
export const FORSLAG_GRANS = 200;

/** `[...DRAFTS_NYCKEL, viewKey]`: under roten som `useTrad` och `usePostaUtkast` invaliderar. */
export const forslagNyckel = (viewKey: string) => [...DRAFTS_NYCKEL, viewKey] as const;

/** `draft_id` → raden ur `GET /drafts`. */
export type ForslagUppslag = ReadonlyMap<string, ForslagStatusSvar>;

// Utanför hooken så att `select` är samma funktion varje render.
const tillUppslag = (svar: ForslagListSvar): ForslagUppslag =>
  new Map(svar.drafts.map((f) => [f.draft_id, f]));

/**
 * `viewKey` saknas → ingen fråga. Ger `undefined` tills svaret finns, och
 * vid fel: då vet klienten inte statusen och kortet står som i dag (`pending`).
 */
export function useForslag(viewKey: string | undefined): ForslagUppslag | undefined {
  const { data } = useQuery({
    queryKey: forslagNyckel(viewKey ?? ""),
    queryFn: () => hamtaForslag({ viewKey: viewKey ?? "", status: "all", limit: FORSLAG_GRANS }),
    select: tillUppslag,
    enabled: viewKey !== undefined,
    staleTime: 60 * 1000,
  });
  return data;
}
