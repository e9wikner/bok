import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  BACKOFF_START_MS,
  BACKOFF_TAK_MS,
  lasHandelser,
  oppnaStrom,
  type SseHandelse,
  type StromSvar,
} from "@/lib/chattyta/strom";

// ─── Hjälpare ─────────────────────────────────────────────────────────────

const kodare = new TextEncoder();

/** En ström som ger exakt de här byte-bitarna och sedan stänger. */
function stromAv(bitar: Array<string | Uint8Array>): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(c) {
      for (const b of bitar) c.enqueue(typeof b === "string" ? kodare.encode(b) : b);
      c.close();
    },
  });
}

/** Samma text, men en byte i taget — varje tänkbar chunk-gräns prövas. */
function byteForByte(text: string): Uint8Array[] {
  return Array.from(kodare.encode(text), (b) => new Uint8Array([b]));
}

/**
 * En ström som ger bitarna och sedan står öppen, som servern gör mellan
 * hjärtslagen, tills signalen avbryter — då felar den som `fetch` gör.
 */
function oppenStrom(bitar: string[], signal: AbortSignal): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(c) {
      for (const b of bitar) c.enqueue(kodare.encode(b));
      signal.addEventListener("abort", () =>
        c.error(new DOMException("Avbruten", "AbortError"))
      );
    },
  });
}

async function samla(stream: ReadableStream<Uint8Array>): Promise<SseHandelse[]> {
  const ut: SseHandelse[] = [];
  for await (const h of lasHandelser(stream)) ut.push(h);
  return ut;
}

const svar = (status: number, body: ReadableStream<Uint8Array> | null = null): StromSvar => ({
  ok: status >= 200 && status < 300,
  status,
  body,
});

const completed = (seq: number) =>
  `event: message.completed\ndata: ${JSON.stringify({ id: `p-${seq}`, seq, type: "agent_text" })}\n\n`;

// ─── Ramparsern ───────────────────────────────────────────────────────────

describe("lasHandelser — ramparsern (testfall 5)", () => {
  const TVA_RAMAR =
    'event: message.created\ndata: {"id":"streaming-r1","type":"agent_text"}\n\n' +
    'event: message.delta\ndata: {"id":"streaming-r1","text":"Hej då, ärendet är klart"}\n\n';

  const FORVANTAT: SseHandelse[] = [
    { event: "message.created", data: { id: "streaming-r1", type: "agent_text" } },
    { event: "message.delta", data: { id: "streaming-r1", text: "Hej då, ärendet är klart" } },
  ];

  it("ger händelserna i ordning, med data JSON-tolkad", async () => {
    expect(await samla(stromAv([TVA_RAMAR]))).toEqual(FORVANTAT);
  });

  it("ramar delade över chunk-gränser — även mitt i ett flerbytestecken (å, ä, ö)", async () => {
    // Servern skriver ensure_ascii=False, så ö är två byte på tråden och en
    // chunk-gräns kan hamna mellan dem.
    expect(await samla(stromAv(byteForByte(TVA_RAMAR)))).toEqual(FORVANTAT);
  });

  it("kommentarsramen (hjärtslaget var 15 s) ignoreras", async () => {
    const h = await samla(stromAv([": keep-alive\n\n", TVA_RAMAR, ": keep-alive\n\n"]));
    expect(h).toEqual(FORVANTAT);
  });

  it("hjärtslag mellan två ramar, delat byte för byte, ger inga extra händelser", async () => {
    const text = completed(1) + ": keep-alive\n\n" + completed(2);
    const h = await samla(stromAv(byteForByte(text)));
    expect(h.map((x) => (x.data as { seq: number }).seq)).toEqual([1, 2]);
  });

  it("flerradig data: raderna fogas med radbrytning, som SSE-specen säger", async () => {
    const h = await samla(stromAv(['event: message.delta\ndata: {"id":"s",\ndata: "text":"a"}\n\n']));
    expect(h).toEqual([{ event: "message.delta", data: { id: "s", text: "a" } }]);
  });

  it("CRLF och ensamt CR som radslut — även CR och LF i var sin chunk", async () => {
    const h = await samla(
      stromAv(['event: view.changed\r', '\ndata: {"view_key":"verifikationer"}\r\n\r', "\n"])
    );
    expect(h).toEqual([{ event: "view.changed", data: { view_key: "verifikationer" } }]);
  });

  it("en ram utan event: heter message, som i EventSource", async () => {
    expect(await samla(stromAv(['data: {"a":1}\n\n']))).toEqual([
      { event: "message", data: { a: 1 } },
    ]);
  });

  it("en ram utan avslutande tomrad när strömmen stänger skickas inte — den är inte färdig", async () => {
    const h = await samla(stromAv([completed(1), 'event: message.completed\ndata: {"seq":2}\n']));
    expect(h).toHaveLength(1);
  });

  it("en ram med data som inte är JSON faller bort med en varning; strömmen fortsätter", async () => {
    const varning = vi.spyOn(console, "warn").mockImplementation(() => {});
    const h = await samla(stromAv(["event: message.delta\ndata: {trasig\n\n", completed(3)]));
    expect(h.map((x) => x.event)).toEqual(["message.completed"]);
    expect(varning).toHaveBeenCalledTimes(1);
    varning.mockRestore();
  });

  it("fält med och utan mellanslag efter kolon, och okända fält, hanteras som SSE-specen", async () => {
    const h = await samla(stromAv(['id: 7\nretry: 100\nevent:message.delta\ndata:{"x":1}\n\n']));
    expect(h).toEqual([{ event: "message.delta", data: { x: 1 } }]);
  });
});

// ─── Anslutningen ─────────────────────────────────────────────────────────

describe("oppnaStrom", () => {
  let styrning: AbortController;
  let vantetider: number[];
  const vanta = vi.fn(async (ms: number) => {
    vantetider.push(ms);
  });

  beforeEach(() => {
    styrning = new AbortController();
    vantetider = [];
    vanta.mockClear();
    // Node 22+ har ett eget globalt `localStorage` som skuggar jsdoms och
    // är tomt utan `--localstorage-file`. En stubbe med samma nyckel som
    // `lib/api.ts` läser räcker — det är källan som testas, inte lagringen.
    const lagrat = new Map([["auth_token", "hemlig-token"]]);
    vi.stubGlobal("localStorage", { getItem: (k: string) => lagrat.get(k) ?? null });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("öppnar med fetch mot /threads/{vk}/stream?since=, med bearer ur samma källa som lib/api.ts", async () => {
    const hamta = vi.fn(async () => {
      styrning.abort();
      return svar(200, stromAv([]));
    });
    await oppnaStrom({
      viewKey: "verifikationer",
      since: 3,
      signal: styrning.signal,
      onHandelse: () => {},
      hamta,
      vanta,
    });
    expect(hamta).toHaveBeenCalledTimes(1);
    const [url, init] = hamta.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/threads/verifikationer/stream?since=3");
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer hemlig-token");
    expect(headers.get("Accept")).toBe("text/event-stream");
    expect(init.signal).toBe(styrning.signal);
  });

  it("lämnar varje händelse till onHandelse i ordning", async () => {
    const sedda: SseHandelse[] = [];
    const hamta = vi.fn(async () => svar(200, oppenStrom([completed(4), completed(5)], styrning.signal)));
    await oppnaStrom({
      viewKey: "bank",
      since: 3,
      signal: styrning.signal,
      onHandelse: (h) => {
        sedda.push(h);
        if (sedda.length === 2) styrning.abort();
      },
      hamta,
      vanta,
    });
    expect(sedda.map((h) => (h.data as { seq: number }).seq)).toEqual([4, 5]);
  });

  describe("återanslutning (testfall 6)", () => {
    it("ny begäran med since = högsta sedda seq ur message.completed", async () => {
      const urlar: string[] = [];
      const hamta = vi.fn(async (url: string) => {
        urlar.push(url);
        if (urlar.length === 1) {
          // Högsta seq kommer inte sist: since är högsta, inte senaste.
          return svar(
            200,
            stromAv([
              completed(9),
              'event: message.delta\ndata: {"id":"streaming-r","text":"x"}\n\n',
              completed(7),
            ])
          );
        }
        styrning.abort();
        return svar(200, stromAv([]));
      });
      await oppnaStrom({
        viewKey: "bank",
        since: 3,
        signal: styrning.signal,
        onHandelse: () => {},
        hamta,
        vanta,
      });
      expect(urlar).toEqual([
        "/api/v1/threads/bank/stream?since=3",
        "/api/v1/threads/bank/stream?since=9",
      ]);
    });

    it("backoff växer 1 → 2 → 4 … och taket 30 s håller", async () => {
      let anrop = 0;
      const hamta = vi.fn(async () => {
        anrop += 1;
        if (anrop === 9) styrning.abort();
        if (anrop % 2) throw new TypeError("Failed to fetch");
        return svar(503);
      });
      await oppnaStrom({
        viewKey: "bank",
        since: 0,
        signal: styrning.signal,
        onHandelse: () => {},
        hamta,
        vanta,
      });
      expect(BACKOFF_START_MS).toBe(1000);
      expect(BACKOFF_TAK_MS).toBe(30_000);
      expect(vantetider).toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000]);
    });

    it("backoff börjar om på 1 s efter en lyckad anslutning", async () => {
      let anrop = 0;
      const hamta = vi.fn(async () => {
        anrop += 1;
        if (anrop === 5) styrning.abort();
        // fel, fel, lyckad som stänger, fel, …
        if (anrop === 3) return svar(200, stromAv([completed(1)]));
        return svar(500);
      });
      await oppnaStrom({
        viewKey: "bank",
        since: 0,
        signal: styrning.signal,
        onHandelse: () => {},
        hamta,
        vanta,
      });
      expect(vantetider).toEqual([1000, 2000, 1000, 2000]);
    });

    it("en ström som bryts mitt i läsningen återansluts, från högsta seq", async () => {
      const urlar: string[] = [];
      const hamta = vi.fn(async (url: string) => {
        urlar.push(url);
        if (urlar.length === 2) styrning.abort();
        // Första läsningen ger en ram, andra felar — `error()` i `start`
        // hade kastat ramen i kön innan den lästs.
        let lasningar = 0;
        const bruten = new ReadableStream<Uint8Array>({
          pull(c) {
            lasningar += 1;
            if (lasningar === 1) c.enqueue(kodare.encode(completed(12)));
            else c.error(new TypeError("network error"));
          },
        });
        return svar(200, bruten);
      });
      await oppnaStrom({
        viewKey: "bank",
        since: 10,
        signal: styrning.signal,
        onHandelse: () => {},
        hamta,
        vanta,
      });
      expect(urlar[1]).toBe("/api/v1/threads/bank/stream?since=12");
    });
  });

  describe("401 (testfall 9)", () => {
    it("ingen återanslutning; utloggningsvägen anropas en gång", async () => {
      const onObehorig = vi.fn();
      const hamta = vi.fn(async () => svar(401));
      await oppnaStrom({
        viewKey: "bank",
        since: 0,
        signal: styrning.signal,
        onHandelse: () => {},
        onObehorig,
        hamta,
        vanta,
      });
      expect(hamta).toHaveBeenCalledTimes(1);
      expect(vanta).not.toHaveBeenCalled();
      expect(onObehorig).toHaveBeenCalledTimes(1);
    });

    it("401 efter en tidigare lyckad anslutning avslutar också", async () => {
      let anrop = 0;
      const hamta = vi.fn(async () => {
        anrop += 1;
        return anrop === 1 ? svar(200, stromAv([completed(1)])) : svar(401);
      });
      await oppnaStrom({
        viewKey: "bank",
        since: 0,
        signal: styrning.signal,
        onHandelse: () => {},
        hamta,
        vanta,
      });
      expect(hamta).toHaveBeenCalledTimes(2);
    });
  });

  describe("avbrott", () => {
    it("signalen under en öppen ström avslutar rent: löftet löser sig, ingen ny begäran", async () => {
      const hamta = vi.fn(async () => svar(200, oppenStrom([completed(1)], styrning.signal)));
      const klar = oppnaStrom({
        viewKey: "bank",
        since: 0,
        signal: styrning.signal,
        onHandelse: () => styrning.abort(),
        hamta,
        vanta,
      });
      await expect(klar).resolves.toBeUndefined();
      expect(hamta).toHaveBeenCalledTimes(1);
      expect(vanta).not.toHaveBeenCalled();
    });

    it("signalen under väntan före återanslutning: ingen ny begäran", async () => {
      const hamta = vi.fn(async () => svar(500));
      const vantaOchAvbryt = vi.fn(async () => {
        styrning.abort();
      });
      await oppnaStrom({
        viewKey: "bank",
        since: 0,
        signal: styrning.signal,
        onHandelse: () => {},
        hamta,
        vanta: vantaOchAvbryt,
      });
      expect(hamta).toHaveBeenCalledTimes(1);
    });

    it("en redan avbruten signal öppnar ingenting", async () => {
      styrning.abort();
      const hamta = vi.fn(async () => svar(200, stromAv([])));
      await oppnaStrom({
        viewKey: "bank",
        since: 0,
        signal: styrning.signal,
        onHandelse: () => {},
        hamta,
        vanta,
      });
      expect(hamta).not.toHaveBeenCalled();
    });

    it("standardväntan släpper direkt när signalen avbryts — ingen timer hänger kvar", async () => {
      vi.useFakeTimers();
      try {
        const hamta = vi.fn(async () => svar(500));
        const klar = oppnaStrom({
          viewKey: "bank",
          since: 0,
          signal: styrning.signal,
          onHandelse: () => {},
          hamta,
        });
        await vi.advanceTimersByTimeAsync(0);
        expect(vi.getTimerCount()).toBe(1);
        styrning.abort();
        await klar;
        expect(vi.getTimerCount()).toBe(0);
        expect(hamta).toHaveBeenCalledTimes(1);
      } finally {
        vi.useRealTimers();
      }
    });
  });
});
