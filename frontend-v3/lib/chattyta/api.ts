/**
 * Trådens anrop (modul `chattyta`, SPEC-chattyta.md §2, §6.2).
 *
 * Via axios-instansen i `lib/api.ts`, så att bearer-headern kommer ur samma
 * interceptor som resten av appen. Strömmen går inte hit: den är `fetch`
 * (§6.1) och bor i `strom.ts`.
 *
 * Svaren lämnas som råinlägg. `parseInlagg` är det enda stället där de blir
 * typade (§4.1) — den körs i reducern (`trad.ts`), inte här, så att GET,
 * POST och strömmen går genom samma dörr.
 *
 * Senare uppgifter lägger beslutssvaret (C7) och postningen (C12) här.
 */

import apiClient from "@/lib/api";
import type { RaInlagg } from "@/lib/chattyta/typer";

/** `api/schemas.py::ThreadResponse`. */
export interface TradSvar {
  view_key: string;
  /** `null` = ingen har sagt något i vyn i år. Då finns ingen ström att öppna (§2 rad 3). */
  thread_id: string | null;
  fiscal_year_id: string | null;
  model: string | null;
  posts: RaInlagg[];
  /** Högsta `seq`; strömmen öppnas med `since` = den (§6.2 punkt 2). */
  cursor: number;
  archive_fiscal_year_ids: string[];
}

/**
 * `api/schemas.py::ThreadMessageResponse`. Bär bara människans egna
 * inlägg — agentens svar kommer över strömmen (SPEC-tradar.md §6.1).
 */
export interface MeddelandeSvar {
  thread_id: string;
  view_key: string;
  fiscal_year_id: string;
  posts: RaInlagg[];
  cursor: number;
}

const tradUrl = (viewKey: string) => `/api/v1/threads/${encodeURIComponent(viewKey)}`;

export async function hamtaTrad(viewKey: string): Promise<TradSvar> {
  const { data } = await apiClient.get<TradSvar>(tradUrl(viewKey));
  return data;
}

/**
 * Fritextvägen, och samtidigt beslutskanalen (§7): klienten gissar inte om
 * texten är ett svar på ett beslut — agenten tolkar den.
 */
export async function skickaMeddelande(viewKey: string, text: string): Promise<MeddelandeSvar> {
  const { data } = await apiClient.post<MeddelandeSvar>(`${tradUrl(viewKey)}/messages`, {
    text,
    attachments: [],
  });
  return data;
}

// ─── Frågenycklar ─────────────────────────────────────────────────────────

/**
 * Skalets `useOverview` (`hooks/useSkal.ts`). Står här och inte där för att
 * `useTrad` ska kunna invalidera den utan att skalets hook rörs; ett test
 * håller de två lika.
 */
export const OVERVIEW_NYCKEL = ["overview"] as const;

/**
 * Roten för varje beslutsfråga: C6:s status per vy (`status=all`) och C8:s
 * märke (`status=open`). De lägger sina nycklar UNDER den här roten, t.ex.
 * `[...BESLUT_NYCKEL, viewKey, "all"]`, så att en invalidering här (§7:
 * `view.changed`, `message.completed` av vissa typer) träffar alla på en gång.
 * Ett beslut i en vy kan ändra märket i en annan — syntetiska beslut räknas
 * i unionen (§10) — så roten invalideras hel, inte per vy.
 */
export const BESLUT_NYCKEL = ["decisions"] as const;
