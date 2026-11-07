"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { skalApi } from "@/lib/skal/api";

/**
 * Headerns enda källa till sidornas prickar och metarader.
 *
 * Ett anrop, inte fyra. Dagens Översikt (`app/page.tsx`) avfyrar åtta
 * parallella hookar och räknar i klienten — det är precis problemet
 * SPEC-oversikt.md §1 beskriver och som den här hooken stänger.
 */
/**
 * Sidornas och flikarnas räknare för årsväljarens år (`null`: innevarande).
 * Under `["overview"]`, så att varje invalidering av översikten når alla år.
 */
export function useOverview(arId: string | null = null) {
  return useQuery({
    queryKey: ["overview", arId ?? "aktuellt"],
    queryFn: () => skalApi.getOverview(arId),
    // Räknarna för det förra året står kvar tills det nya årets kommer, så
    // att headern och årsväljaren inte blinkar bort vid ett årsbyte.
    placeholderData: keepPreviousData,
    staleTime: 60 * 1000,
  });
}

/**
 * Agentläget är globalt, inte per sida (SPEC-tradar.md §7, §12.5).
 *
 * `retry: false`: går anropet inte fram ska `AgentStatus` visa ingenting —
 * aldrig "pausad". Pausad är ett riktigt läge med en orsak, och att gissa
 * det ur ett nätverksfel vore en lögn i produkttonen.
 */
export function useAgentStatus() {
  return useQuery({
    queryKey: ["agent-status"],
    queryFn: skalApi.getAgentStatus,
    staleTime: 15 * 1000,
    refetchInterval: 30 * 1000,
    retry: false,
  });
}
