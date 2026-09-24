/**
 * Trådens tillstånd (modul `chattyta`, SPEC-chattyta.md §6.3).
 *
 * En ren reducer, inte en hook: tillståndet har tre sätt att få en dubblett
 * — återuppspelning vid återanslutning, det optimistiska inlägget och den
 * strömmande platshållaren — och en ren funktion går att pröva händelse för
 * händelse (plan.md, C3). `hooks/useTrad.ts` kopplar den till nätet.
 *
 * Tre regler bär resten:
 *
 * 1. Allt som kommer från servern går genom `parseInlagg` (§4.1). `null`
 *    (okänd typ) faller bort; kontraktsbrott blir `okant_kontrakt`.
 * 2. Idempotent på `id`. Inlägg ändras aldrig (antagande 2), så ett id som
 *    redan finns är samma inlägg — en återuppspelning lägger inte till något
 *    (testfall 7).
 * 3. Det lagrade inlägget vinner över den ihopsamlade deltatexten vid
 *    `message.completed` (testfall 10). Deltan är en leverans, inte
 *    sanningen (SPEC-tradar.md §8.5).
 */

import { parseInlagg } from "@/lib/chattyta/parse";
import type { SseHandelse } from "@/lib/chattyta/strom";
import type { Inlagg, RaInlagg, UserTextInlagg } from "@/lib/chattyta/typer";

/**
 * Agentens svar medan det skrivs. Inte ett `Inlagg`: det har ingen `seq`
 * och ska aldrig sorteras in i tråden — `SkriverIndikator` ritar det, och
 * `message.completed` ersätter det med det lagrade.
 */
export interface Strommande {
  /** `streaming-{run_id}` (services/thread_stream.py). */
  id: string;
  run_id: string;
  text: string;
  /**
   * Senaste verktygsanropet, som serverns verktygsnamn. `null` tills det
   * första kommer; `SkriverIndikator` säger då `Läser…` (§5, testfall 11).
   */
  activity: string | null;
}

export interface TradTillstand {
  /** Server- och optimistiska inlägg på `id`. Ordningen ges av `listaInlagg`. */
  inlagg: Map<string, Inlagg>;
  strommande: Strommande | null;
  /** Högsta `seq` klienten sett. */
  maxSeq: number;
}

export type TradHandling =
  | { typ: "nollstall" }
  /** `GET /threads/{vk}` (§6.3 rad 1). */
  | { typ: "hamtad"; posts: RaInlagg[]; cursor: number }
  | { typ: "optimistisk"; id: string; text: string; skapad: string }
  /** `POST …/messages` svarade: det optimistiska byts mot serverns. */
  | { typ: "skickad"; lokaltId: string; posts: RaInlagg[]; cursor: number }
  | { typ: "misslyckad"; lokaltId: string }
  | { typ: "handelse"; handelse: SseHandelse };

/**
 * Prefix för optimistiska id:n. Serverns id:n är UUID:er och kan inte börja
 * så; därmed räcker id:t för att veta vilka inlägg som ännu inte är lagrade
 * — utan ett fält till på `Inlagg`, vars form är serverns (typer.ts).
 */
export const LOKALT_PREFIX = "lokal-";

export const arOptimistisk = (i: Inlagg): boolean => i.id.startsWith(LOKALT_PREFIX);

export function tomTrad(): TradTillstand {
  return { inlagg: new Map(), strommande: null, maxSeq: 0 };
}

const STROMMANDE_PREFIX = "streaming-";

const arObjekt = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/** Råinlägg in i en kopia av kartan. `null` från `parseInlagg` faller bort. */
function laggIn(karta: Map<string, Inlagg>, posts: RaInlagg[]): number {
  let hogsta = 0;
  for (const raw of posts) {
    const inlagg = parseInlagg(raw);
    if (Number.isInteger(raw.seq)) hogsta = Math.max(hogsta, raw.seq);
    if (inlagg) karta.set(inlagg.id, inlagg);
  }
  return hogsta;
}

function handelse(t: TradTillstand, { event, data }: SseHandelse): TradTillstand {
  if (!arObjekt(data) || typeof data.id !== "string") return t;

  switch (event) {
    case "message.created": {
      const run_id = typeof data.run_id === "string" ? data.run_id : data.id.slice(STROMMANDE_PREFIX.length);
      // En sen prenumerant får en pågående tur som ett `created` med det
      // som sagts hittills (`ThreadBroker.subscribe`). Texten ERSÄTTER, den
      // läggs inte till — då dubblas inget vid en återanslutning mitt i.
      return {
        ...t,
        strommande: {
          id: data.id,
          run_id,
          text: typeof data.text === "string" ? data.text : "",
          activity: typeof data.activity === "string" ? data.activity : null,
        },
      };
    }

    case "message.delta": {
      // En delta utan `message.created` startar platshållaren ändå. Turen
      // startar i POST och strömmen öppnas efter svaret (§6.2 punkt 3), så
      // `created` kan ha gått innan någon lyssnade — och en tyst tråd vore
      // precis den anonyma väntan designen förbjuder.
      const nu: Strommande =
        t.strommande?.id === data.id
          ? t.strommande
          : {
              id: data.id,
              run_id: data.id.startsWith(STROMMANDE_PREFIX)
                ? data.id.slice(STROMMANDE_PREFIX.length)
                : data.id,
              text: "",
              activity: null,
            };
      // Två former (§2): `{text}` byggs på, `{activity}` byter indikatorn.
      // Den ena rör aldrig den andra, så indikatorn blir aldrig tom igen.
      if (typeof data.text === "string") {
        return { ...t, strommande: { ...nu, text: nu.text + data.text } };
      }
      if (typeof data.activity === "string") {
        return { ...t, strommande: { ...nu, activity: data.activity } };
      }
      return t;
    }

    case "message.completed": {
      const raw = data as unknown as RaInlagg;
      const platshallare =
        t.strommande !== null && typeof raw.run_id === "string" && t.strommande.id === `${STROMMANDE_PREFIX}${raw.run_id}`;
      const finns = t.inlagg.has(raw.id);
      // Återuppspelning av något redan sett: samma objekt tillbaka, ingen
      // omritning (testfall 7).
      if (finns && !platshallare) return t;

      const inlagg = new Map(t.inlagg);
      const seq = finns ? 0 : laggIn(inlagg, [raw]);
      return {
        inlagg,
        // Det lagrade ersätter platshållaren. Den ihopsamlade texten kastas —
        // även om den skiljer sig är det lagrade sanningen (testfall 10).
        strommande: platshallare ? null : t.strommande,
        maxSeq: Math.max(t.maxSeq, seq),
      };
    }

    // `view.changed` rör inte tråden; hooken invaliderar frågorna (§6.3).
    default:
      return t;
  }
}

export function tradReducer(t: TradTillstand, h: TradHandling): TradTillstand {
  switch (h.typ) {
    case "nollstall":
      return tomTrad();

    case "hamtad": {
      // Ersätter serverns inlägg. Det människan redan skrivit men som inte
      // svarats på står kvar: ett sent GET-svar ska inte ta hennes text.
      const inlagg = new Map<string, Inlagg>();
      for (const [id, i] of t.inlagg) if (arOptimistisk(i)) inlagg.set(id, i);
      laggIn(inlagg, h.posts);
      return { ...t, inlagg, maxSeq: h.cursor };
    }

    case "optimistisk": {
      const inlagg = new Map(t.inlagg);
      const du: UserTextInlagg = {
        id: h.id,
        // Ingen `seq` än — sorteras sist av `listaInlagg`, oavsett tal.
        seq: -1,
        type: "user_text",
        actor: "du",
        created_at: h.skapad,
        traces: null,
        run_id: null,
        body: { text: h.text },
      };
      inlagg.set(h.id, du);
      return { ...t, inlagg };
    }

    case "skickad": {
      const inlagg = new Map(t.inlagg);
      inlagg.delete(h.lokaltId);
      const seq = laggIn(inlagg, h.posts);
      return { ...t, inlagg, maxSeq: Math.max(t.maxSeq, h.cursor, seq) };
    }

    case "misslyckad": {
      if (!t.inlagg.has(h.lokaltId)) return t;
      const inlagg = new Map(t.inlagg);
      inlagg.delete(h.lokaltId);
      return { ...t, inlagg };
    }

    case "handelse":
      return handelse(t, h.handelse);
  }
}

/**
 * Tråden i visningsordning: serverns inlägg på `seq`, optimistiska sist i
 * den ordning de skrevs (§6.3). Ordningen är serverns — klienten slår inte
 * ihop och flyttar inte (§5).
 */
export function listaInlagg(t: TradTillstand): Inlagg[] {
  const lagrade: Inlagg[] = [];
  const lokala: Inlagg[] = [];
  for (const i of t.inlagg.values()) (arOptimistisk(i) ? lokala : lagrade).push(i);
  lagrade.sort((a, b) => a.seq - b.seq);
  return [...lagrade, ...lokala];
}
