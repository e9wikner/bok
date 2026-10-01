"use client";

/**
 * Märket på mobilens `ChattList`: hur många beslut som väntar i en vy
 * (SPEC-chattyta.md §10).
 *
 * Talet är serverns `total` ur `GET /decisions?view_key&status=open&limit=1`
 * — unionen, alltså även de syntetiska besluten (`intake`, `correction`),
 * samma tal som headerns `open_decisions` (SPEC-beslut.md §6.6). Klienten
 * räknar inte själv och filtrerar ingenting: ett tal som räknats på två
 * ställen visar förr eller senare två olika tal. `limit=1` för att raderna
 * inte behövs, bara `total`, som är unionens antal före sidningen.
 */

import { useQuery } from "@tanstack/react-query";
import { BESLUT_NYCKEL, hamtaBeslut } from "@/lib/chattyta/api";

/**
 * Under `BESLUT_NYCKEL`, så att `useTrad`s invalidering av roten (§7:
 * `view.changed`, `message.completed` av beslutstyperna) och C7:s svar
 * träffar märket utan att veta om det. C6:s status per vy ligger bredvid,
 * `[...BESLUT_NYCKEL, viewKey, "all"]`.
 */
export const beslutMarkeNyckel = (viewKey: string) => [...BESLUT_NYCKEL, viewKey, "open"] as const;

/**
 * `aktiv: false` frågar inte — desktop har inget märke. Minimerad chatt är
 * däremot INTE ett skäl att låta bli: märket ska synas just då
 * (komponenter.md), så anroparen styr bara på om märket finns alls.
 *
 * Ger `0` medan frågan laddar eller om den misslyckats; märket faller då
 * tillbaka på inläggsräkningen, som det gjorde utan beslut.
 */
export function useVantandeBeslut(viewKey: string, { aktiv = true }: { aktiv?: boolean } = {}): number {
  const { data } = useQuery({
    queryKey: beslutMarkeNyckel(viewKey),
    queryFn: () => hamtaBeslut({ viewKey, status: "open", limit: 1 }),
    select: (svar) => svar.total,
    enabled: aktiv,
    // Samma som headerns `useOverview`: de två ska visa samma tal, och
    // ändringar som sker i tråden invalideras ändå direkt av `useTrad`.
    staleTime: 60 * 1000,
  });
  return data ?? 0;
}
