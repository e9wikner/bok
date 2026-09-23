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
 * Beslutssvaret (C7) och postningen (C12) ligger här.
 */

import axios from "axios";
import apiClient from "@/lib/api";
import { nyckelForUtkast } from "@/lib/chattyta/idempotens";
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

// ─── Svar på beslut (SPEC-beslut.md §6.2, SPEC-chattyta.md §7) ──────────

/** `api/schemas.py::DecisionAnswerResponse` — kroppen i `202`. */
export interface BeslutSvarSvar {
  decision: BeslutSvar;
  /** Människans `user_text`-inlägg som servern skrev för svaret. */
  answer_post_id: string;
  answer_post_seq: number;
}

/**
 * Hur ett svar slutade, så som kortet behöver veta det. Två utfall, inte
 * tre: `202` och `409 decision_already_answered` är samma sak för
 * människan — beslutet är besvarat (§7). Skillnaden är bara VILKET svar som
 * gäller: vid `409` är det serverns, som kan vara ett annat alternativ än
 * det som trycktes, eller fritext (`answer_option_id: null`).
 */
export type BeslutSvarUtfall =
  | { utfall: "besvarat"; svar: BeslutSvarSvar }
  | {
      utfall: "redan_besvarat";
      answered_at: string | null;
      answer_post_id: string | null;
      answer_option_id: string | null;
      answer_text: string | null;
    };

/** `409`-kroppens `detail` (`api/routes/decisions.py::answer_decision`). */
interface RedanBesvaratDetalj {
  code: "decision_already_answered";
  answered_at?: string | null;
  answer_post_id?: string | null;
  answer_option_id?: string | null;
  answer_text?: string | null;
}

function arRedanBesvarat(fel: unknown): RedanBesvaratDetalj | null {
  if (!axios.isAxiosError(fel) || fel.response?.status !== 409) return null;
  // FastAPIs `HTTPException(detail={...})` → `{"detail": {...}}`.
  const detalj = (fel.response.data as { detail?: unknown } | undefined)?.detail;
  if (typeof detalj !== "object" || detalj === null) return null;
  return (detalj as { code?: unknown }).code === "decision_already_answered"
    ? (detalj as RedanBesvaratDetalj)
    : null;
}

/**
 * `POST /decisions/{id}/answer {option_id}` — knappvägen. Fritexten går
 * aldrig hit utan via `skickaMeddelande` (§7: agenten tolkar den, klienten
 * gissar inte vilket beslut en text svarar på).
 *
 * Allt annat än `202` och `409 decision_already_answered` kastas vidare:
 * `409 decision_not_answerable` (syntetiska beslut, som inte har något
 * `options`-inlägg att trycka i), `404`, `400`, `5xx` och nätverksfel. För
 * kortet är de samma sak — svaret kom inte fram.
 */
export async function svaraBeslut(decisionId: string, optionId: string): Promise<BeslutSvarUtfall> {
  try {
    const { data } = await apiClient.post<BeslutSvarSvar>(
      `/api/v1/decisions/${encodeURIComponent(decisionId)}/answer`,
      { option_id: optionId }
    );
    return { utfall: "besvarat", svar: data };
  } catch (fel) {
    const redan = arRedanBesvarat(fel);
    if (!redan) throw fel;
    return {
      utfall: "redan_besvarat",
      answered_at: redan.answered_at ?? null,
      answer_post_id: redan.answer_post_id ?? null,
      answer_option_id: redan.answer_option_id ?? null,
      answer_text: redan.answer_text ?? null,
    };
  }
}

// ─── Postning (SPEC-chattyta.md §8, SPEC-idempotens.md §6) ───────────────

/**
 * `api/schemas.py::VoucherResponse`, de fält klienten läser. Kortets klara
 * läge är `{series}-{number}` (§8); resten lämnas åt `flode-verifikationer`.
 */
export interface VerifikationSvar {
  id: string;
  series: string;
  number: number;
  date: string;
  period_id: string;
  status: string;
  posted_at?: string | null;
}

/**
 * Hur en postning slutade, så som kortet behöver veta det — en rad per rad i
 * §8:s tabell. Två saker är avsiktligt INTE fel:
 * - `redan_postad` (`409 already_posted`) är samma sak som `postad` för
 *   människan: verifikationen finns, med det nummer servern säger.
 *   `verifikation` är `null` bara om servern inte hittade den att bifoga
 *   (`_posting_http_error`); då vet klienten att den är postad men inte som vad.
 * - `pagar` (`409 request_in_flight`) är ett "fråga igen strax", inte ett slut.
 */
export type PostaUtfall =
  | { utfall: "postad"; verifikation: VerifikationSvar; uppspelad: boolean }
  | { utfall: "redan_postad"; verifikation: VerifikationSvar | null }
  | { utfall: "pagar"; retry_after_ms: number }
  | { utfall: "nyckel_ateranvand" }
  | {
      utfall: "period_last";
      /** Serverns id — ett UUID, inte en etikett. Det är allt `detail` bär om perioden. */
      period_id: string | null;
      /** ISO, utan tidszon (`period.locked_at.isoformat()`). */
      locked_at: string | null;
      /** Servern ersätter redan `null` med `"okänd"`, men kontraktet (§2) tillåter `null`. */
      locked_by: string | null;
    }
  /** `status: null` = inget svar alls (nätverket). */
  | { utfall: "natverk"; status: number | null };

/** Servern har ingen `retry_after_ms` att ge i något känt fall; 500 ms är vad den skickar i dag. */
const STANDARD_VANTAN_MS = 500;

/** FastAPIs `HTTPException(detail={...})` → `{"detail": {...}}`; annars `null`. */
function feldetalj(fel: unknown): Record<string, unknown> | null {
  if (!axios.isAxiosError(fel)) return null;
  const detalj = (fel.response?.data as { detail?: unknown } | undefined)?.detail;
  return typeof detalj === "object" && detalj !== null ? (detalj as Record<string, unknown>) : null;
}

const strangEllerNull = (v: unknown): string | null => (typeof v === "string" ? v : null);

/**
 * `POST /vouchers/{draftId}/post` med `Idempotency-Key` härledd ur utkastet
 * (C11). **Nyckeln görs bara här, bara med `nyckelForUtkast`** — ett andra
 * tryck, en annan flik, en omladdning och `FelKort`s `Försök igen` går alla
 * genom den här funktionen och får samma nyckel (§8 steg 1, testfall 25).
 *
 * Det här är det ENDA anropsstället för en postning från chattytan. §15.1
 * lämnar öppet om människan ska posta direkt eller via tråden; byts vägen
 * byts den här, och kortet märker inget. `PUT /vouchers/{id}` anropas aldrig
 * härifrån: förslag ändras i samtalet (§8 steg 4).
 *
 * Allt som inte står i §8:s tabell kastas vidare (t.ex. `400
 * voucher_date_outside_period`, `404`): det är inte kortets sak att gissa
 * vad de betyder.
 */
export async function postaUtkast(draftId: string): Promise<PostaUtfall> {
  const nyckel = await nyckelForUtkast(draftId);
  try {
    const svar = await apiClient.post<VerifikationSvar>(
      `/api/v1/vouchers/${encodeURIComponent(draftId)}/post`,
      undefined,
      { headers: { "Idempotency-Key": nyckel } }
    );
    // axios gemenar headernamnen. En uppspelning är samma verifikation (§8).
    const replay = (svar.headers as Record<string, unknown> | undefined)?.["idempotent-replay"];
    return { utfall: "postad", verifikation: svar.data, uppspelad: replay === "true" };
  } catch (fel) {
    if (!axios.isAxiosError(fel)) throw fel;
    const status = fel.response?.status;
    // Inget svar, eller servern föll: ingenting vet vi är bokfört, och samma
    // nyckel gör ett nytt försök ofarligt.
    if (status === undefined || status >= 500) return { utfall: "natverk", status: status ?? null };

    const detalj = feldetalj(fel);
    const kod = detalj?.code;
    if (status === 409 && kod === "already_posted") {
      const v = detalj?.voucher;
      return {
        utfall: "redan_postad",
        verifikation: typeof v === "object" && v !== null ? (v as VerifikationSvar) : null,
      };
    }
    if (status === 409 && kod === "request_in_flight") {
      const ms = detalj?.retry_after_ms;
      return {
        utfall: "pagar",
        retry_after_ms: typeof ms === "number" && ms >= 0 ? ms : STANDARD_VANTAN_MS,
      };
    }
    if (status === 422 && kod === "idempotency_key_reuse") return { utfall: "nyckel_ateranvand" };
    if (status === 409 && kod === "period_locked") {
      return {
        utfall: "period_last",
        period_id: strangEllerNull(detalj?.period_id),
        locked_at: strangEllerNull(detalj?.locked_at),
        locked_by: strangEllerNull(detalj?.locked_by),
      };
    }
    throw fel;
  }
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
