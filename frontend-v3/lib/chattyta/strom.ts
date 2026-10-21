/**
 * Trådens ström (modul `chattyta`, SPEC-chattyta.md §6).
 *
 * `fetch` + `ReadableStream`, inte `EventSource`: `EventSource` kan inte
 * skicka en `Authorization`-header, och API:t autentiserar med bearer.
 * Token i query-strängen eller cookies hade krävt en backendändring och
 * lagt token i loggar (§6.1, antagande 1).
 *
 * Två delar, med olika skäl att finnas:
 *
 * - `lasHandelser` är en ren funktion av en byteström → händelser. Den vet
 *   inget om nätverk, auth eller vyer, så chunk-gränser, hjärtslag och
 *   flerradig `data:` går att testa utan server (testfall 5) — samma skäl
 *   som `thread_stream.format_sse` är en fri funktion på serversidan.
 * - `oppnaStrom` är anslutningen: bearer, återanslutning med `since`,
 *   backoff, `401` och avbrott (§6.2 punkt 4–6). Klocka och `fetch` är
 *   injicerbara så att testerna inte sover.
 *
 * Strömmen tolkar inte händelserna. Vad `message.completed` gör med tråden
 * är reducerns (`trad.ts`, §6.3); här läses bara `seq` för att veta var
 * en återanslutning ska börja.
 */

import apiClient from "@/lib/api";

/** En SSE-ram, med `data` JSON-tolkad. Servern skickar alltid JSON. */
export interface SseHandelse {
  event: string;
  data: unknown;
}

// ─── Ramparsern ───────────────────────────────────────────────────────────

/**
 * Byteström → händelser, i ordning (WHATWG-specen för `text/event-stream`,
 * den del servern använder: `event`, `data`, kommentarer).
 *
 * Avkodaren körs med `stream: true`: servern skriver `ensure_ascii=False`,
 * så `ö` är två byte på tråden och en chunk-gräns kan hamna mellan dem.
 * Utan det blir tecknet två ersättningstecken och JSON-texten fel.
 */
export async function* lasHandelser(
  stream: ReadableStream<Uint8Array>
): AsyncGenerator<SseHandelse> {
  const lasare = stream.getReader();
  const avkodare = new TextDecoder("utf-8");
  let buffert = "";
  let handelse = "";
  let data: string[] = [];

  /** En tomrad avslutar ramen. Ram utan `data:` skickas inte (SSE-specen). */
  function avsluta(): SseHandelse | null {
    const ram = data.length ? { event: handelse || "message", text: data.join("\n") } : null;
    handelse = "";
    data = [];
    if (!ram) return null;
    try {
      return { event: ram.event, data: JSON.parse(ram.text) };
    } catch {
      // En trasig ram ska inte fälla strömmen: nästa ram kan vara hel, och
      // en återanslutning skulle bara spela upp samma sak igen.
      console.warn(`[chattyta] SSE-ram med data som inte är JSON faller bort: ${ram.event}`);
      return null;
    }
  }

  function rad(r: string): SseHandelse | null {
    if (r === "") return avsluta();
    // Kommentarsram: hjärtslaget var 15 s (`: keep-alive`). Håller proxyer
    // vid liv, bär ingenting.
    if (r.startsWith(":")) return null;
    const kolon = r.indexOf(":");
    const falt = kolon === -1 ? r : r.slice(0, kolon);
    let varde = kolon === -1 ? "" : r.slice(kolon + 1);
    if (varde.startsWith(" ")) varde = varde.slice(1);
    if (falt === "event") handelse = varde;
    else if (falt === "data") data.push(varde);
    // `id` och `retry` används inte: återanslutningen går på trådens `seq`,
    // inte på SSE:s `Last-Event-ID`, och servern sätter inga av dem.
    return null;
  }

  try {
    for (;;) {
      const { done, value } = await lasare.read();
      buffert += done ? avkodare.decode() : avkodare.decode(value, { stream: true });
      // Radslut är CRLF, LF eller ensamt CR. Ett CR sist i bufferten kan
      // vara första halvan av ett CRLF som delats över chunk-gränsen —
      // vänta på nästa chunk innan det tolkas, annars blir det en tomrad
      // för mycket och ramen avslutas mitt i.
      let m: RegExpExecArray | null;
      while ((m = /\r\n|\n|\r/.exec(buffert))) {
        if (m[0] === "\r" && m.index === buffert.length - 1 && !done) break;
        const h = rad(buffert.slice(0, m.index));
        buffert = buffert.slice(m.index + m[0].length);
        if (h) yield h;
      }
      // En ram utan avslutande tomrad när strömmen stänger är inte färdig
      // och skickas inte (SSE-specen) — halva inlägg är värre än inga.
      if (done) return;
    }
  } finally {
    // Konsumenten kan sluta iterera i förtid (avbrott, vybyte). Då ska
    // förbindelsen stängas, inte lämnas hängande med ett låst läsobjekt.
    await lasare.cancel().catch(() => {});
    lasare.releaseLock();
  }
}

// ─── Anslutningen ─────────────────────────────────────────────────────────

/** §6.2 punkt 4: 1 s → 2 s → 4 s → … tak 30 s. */
export const BACKOFF_START_MS = 1000;
export const BACKOFF_TAK_MS = 30_000;

/** Det lilla av `Response` som strömmen läser. Håller testernas svar små. */
export interface StromSvar {
  ok: boolean;
  status: number;
  body: ReadableStream<Uint8Array> | null;
}

export type Hamta = (url: string, init: RequestInit) => Promise<StromSvar>;
export type Vanta = (ms: number, signal: AbortSignal) => Promise<void>;

export interface StromAlternativ {
  viewKey: string;
  /** `cursor` ur `GET /threads/{vk}` eller `POST …/messages` (§6.2 punkt 2–3). */
  since: number;
  /** Vybyte stänger strömmen (§6.2 punkt 5). */
  signal: AbortSignal;
  onHandelse: (h: SseHandelse) => void;
  /**
   * `401`: sessionen är slut. Anroparen kopplar in utloggningen
   * (`useAuth().logout`) — den är en hook och går inte att nå härifrån.
   */
  onObehorig?: () => void;
  /** Injicerbara för testerna. */
  hamta?: Hamta;
  vanta?: Vanta;
}

/** Väntan som släpper direkt vid avbrott, så att ingen timer hänger kvar. */
const standardVanta: Vanta = (ms, signal) =>
  new Promise((klar) => {
    if (signal.aborted) return klar();
    const slapp = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", slapp);
      klar();
    };
    const timer = setTimeout(slapp, ms);
    signal.addEventListener("abort", slapp);
  });

/**
 * Bearer ur samma källa som axios-interceptorn i `lib/api.ts`. Den
 * interceptorn nås inte av `fetch`, så nyckeln läses på samma sätt här.
 */
function bearer(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("auth_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function hogstaSeq(h: SseHandelse, nu: number): number {
  if (h.event !== "message.completed") return nu;
  const seq = (h.data as { seq?: unknown } | null)?.seq;
  return Number.isInteger(seq) && (seq as number) > nu ? (seq as number) : nu;
}

/**
 * Håller strömmen öppen tills signalen avbryts eller servern svarar `401`.
 * Löftet löser sig då; det avvisas aldrig — varje annat fel är ett skäl
 * att återansluta, inte att ge upp.
 *
 * `since` följer högsta `seq` ur `message.completed`, så en återanslutning
 * spelar upp det som missades och inget annat. Det som ändå kommer två
 * gånger dedupliceras på `id` i reducern (§6.2 punkt 4, testfall 7).
 */
export async function oppnaStrom({
  viewKey,
  since,
  signal,
  onHandelse,
  onObehorig,
  hamta = (url, init) => fetch(url, init),
  vanta = standardVanta,
}: StromAlternativ): Promise<void> {
  // Samma bas-URL som axios-instansen, så att strömmen och resten av
  // API-anropen aldrig kan peka på olika servrar.
  const bas = apiClient.defaults.baseURL ?? "";
  let maxSeq = since;
  let backoff = BACKOFF_START_MS;

  while (!signal.aborted) {
    try {
      const svar = await hamta(
        `${bas}/api/v1/threads/${encodeURIComponent(viewKey)}/stream?since=${maxSeq}`,
        { headers: { Accept: "text/event-stream", ...bearer() }, signal }
      );
      if (svar.status === 401) {
        // En återanslutning kan inte lyckas med samma token (§6.2 punkt 6).
        onObehorig?.();
        return;
      }
      if (svar.ok && svar.body) {
        // En lyckad anslutning nollställer backoffen: nästa avbrott är ett
        // nytt avbrott, inte fortsättningen på en serie misslyckanden.
        backoff = BACKOFF_START_MS;
        for await (const h of lasHandelser(svar.body)) {
          maxSeq = hogstaSeq(h, maxSeq);
          onHandelse(h);
          if (signal.aborted) return;
        }
      }
      // Övriga svar (404 innan tråden finns, 5xx) och en ström som servern
      // stängt: försök igen efter backoff.
    } catch {
      // Nätverksfel, eller avbrottet självt — det senare fångas av
      // villkoret nedan.
    }
    if (signal.aborted) return;
    await vanta(backoff, signal);
    backoff = Math.min(backoff * 2, BACKOFF_TAK_MS);
  }
}
