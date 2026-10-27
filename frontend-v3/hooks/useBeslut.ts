"use client";

/**
 * Beslutens status i en vy (SPEC-chattyta.md §7).
 *
 * Inlägget säger inte om beslutet är besvarat — inlägg ändras aldrig
 * (antagande 2). Statusen finns bara i `GET /decisions`, så klienten läser
 * vyns hela lista EN gång (`status=all`, annars syns varken `answered` eller
 * `superseded`) och slår upp `decision_id` lokalt. Ett anrop per vy, inte
 * ett per kort (testfall 20).
 *
 * Hooken anropas av varje beslutskort, men frågenyckeln är vyns: TanStack
 * Query slår ihop dem till en begäran och ett svar. Det gör också att en
 * tråd utan beslutsinlägg inte frågar alls, och att bara den aktiva vyn
 * frågar — de inaktiva ritar ingen tråd (`OLAST_TRAD`, C5).
 */

import { useQuery } from "@tanstack/react-query";
import { BESLUT_NYCKEL, hamtaBeslut, type BeslutListSvar, type BeslutSvar } from "@/lib/chattyta/api";

/**
 * Serverns tak (`api/routes/decisions.py`, `le=200`). En vy med fler beslut
 * än så får de äldsta i svaret (unionen är äldst först); ett kort vars id
 * inte finns med står i öppet läge utan påstående (`BeslutKort`).
 */
export const BESLUT_GRANS = 200;

/**
 * Under `BESLUT_NYCKEL`, bredvid märkets `[..., viewKey, "open"]` (C8). Då
 * träffar `useTrad`s invalidering av roten (§7: `view.changed`,
 * `message.completed` av typerna `decision`/`options`/`user_text`) och C7:s
 * svar den här frågan utan att veta om den.
 */
export const beslutStatusNyckel = (viewKey: string) => [...BESLUT_NYCKEL, viewKey, "all"] as const;

export type BeslutUppslag = ReadonlyMap<string, BeslutSvar>;

// Utanför hooken så att `select` är samma funktion varje render och TanStack
// Query kan memoisera uppslaget i stället för att bygga om det per kort.
const tillUppslag = (svar: BeslutListSvar): BeslutUppslag =>
  new Map(svar.decisions.map((b) => [b.id, b]));

/**
 * `viewKey` saknas → ingen fråga (renderaren används utan vy, t.ex. i
 * test). Ger `undefined` tills svaret finns, och vid fel: då vet klienten
 * inte statusen och ska inte låtsas veta den.
 */
export function useBeslut(viewKey: string | undefined): BeslutUppslag | undefined {
  const { data } = useQuery({
    queryKey: beslutStatusNyckel(viewKey ?? ""),
    queryFn: () => hamtaBeslut({ viewKey, status: "all", limit: BESLUT_GRANS }),
    select: tillUppslag,
    enabled: viewKey !== undefined,
    // Som märket (`useVantandeBeslut`): ändringar i tråden invalideras ändå
    // direkt av `useTrad`, och ett kort som monteras senare ska inte fråga
    // om det bara för att det är nytt.
    staleTime: 60 * 1000,
  });
  return data;
}
