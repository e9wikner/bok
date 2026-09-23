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

// ─── Beslut (SPEC-beslut.md §6.1, SPEC-chattyta.md §7, §10) ──────────────

/**
 * `abstention` och `approval` är riktiga beslut (`decisions.kind`, migration
 * 026); `intake` och `correction` är de två syntetiska källorna, vars `id`
 * bär prefixet `intake:`/`correction:` (SPEC-beslut.md §5). Servern typar
 * fältet som `str`; värdena här är de fyra den kan ge.
 */
export type BeslutSort = "abstention" | "approval" | "intake" | "correction";

/** `superseded` syns bara vid `status=all` (`DecisionService.list_decisions`). */
export type BeslutStatus = "open" | "answered" | "superseded";

/** Frågans filter, inte ett besluts status: `all` är inget läge ett beslut kan ha. */
export type BeslutFilter = "open" | "answered" | "all";

/** `api/schemas.py::DecisionOptionResponse`. Alltid `[]` för syntetiska beslut. */
export interface BeslutAlternativSvar {
  id: string;
  position: number;
  title: string;
  rationale: string;
  account: string | null;
  amount_ore: number | null;
  recommended: boolean;
  is_exit: boolean;
}

/**
 * `api/schemas.py::DecisionSourceResponse`. `kind` är öppen (`intake_source`,
 * `voucher`, eller vad agenten angav) och lämnas som sträng.
 */
export interface BeslutKallaSvar {
  kind: string;
  id: string;
  /** ISO-datum `YYYY-MM-DD`, eller `null`. */
  date: string | null;
}

/** `api/schemas.py::DecisionResponse`, fält för fält. */
export interface BeslutSvar {
  id: string;
  view_key: string;
  kind: BeslutSort;
  status: BeslutStatus;
  title: string;
  amount_ore: number | null;
  /** För `correction` är det människans text, inte agentens (schemats docstring). */
  reason: string;
  consequence: string;
  /** `null` för ett beslut som togs upp mitt i samtalet (SPEC-beslut.md §2 antagande 5). */
  source: BeslutKallaSvar | null;
  /** Serverns tal; färgas med `aldersTon` (`lib/chattyta/alder.ts`). */
  age_days: number;
  /** `null` för syntetiska beslut — de har inget inlägg i någon tråd (§7). */
  thread_id: string | null;
  post_id: string | null;
  options: BeslutAlternativSvar[];
}

/**
 * `api/schemas.py::DecisionListResponse`. `total` är unionens antal FÖRE
 * `limit`/`offset` — därför räcker `limit=1` för märket (§10).
 */
export interface BeslutListSvar {
  decisions: BeslutSvar[];
  total: number;
}

/**
 * `GET /decisions` — unionen av de tre källorna, äldst först. Utelämnade
 * parametrar lämnas åt serverns standard (`status=open`, `limit=50`); axios
 * skickar inte `undefined`.
 */
export async function hamtaBeslut({
  viewKey,
  status,
  limit,
  offset,
}: {
  viewKey?: string;
  status?: BeslutFilter;
  limit?: number;
  offset?: number;
}): Promise<BeslutListSvar> {
  const { data } = await apiClient.get<BeslutListSvar>("/api/v1/decisions", {
    params: { view_key: viewKey, status, limit, offset },
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
