import { describe, expect, it, vi } from "vitest";
import {
  arOptimistisk,
  listaInlagg,
  tomTrad,
  tradReducer,
  type TradHandling,
  type TradTillstand,
} from "@/lib/chattyta/trad";
import type { SseHandelse } from "@/lib/chattyta/strom";
import type { RaInlagg } from "@/lib/chattyta/typer";
import { FIXTUR_AGENT_TEXT, FIXTUR_USER_TEXT } from "@/lib/chattyta/__fixtures__/inlagg";

// ─── Hjälpare ─────────────────────────────────────────────────────────────

function kor(...handlingar: TradHandling[]): TradTillstand {
  return handlingar.reduce(tradReducer, tomTrad());
}

const agent = (id: string, seq: number, text: string, run_id: string | null = null): RaInlagg => ({
  ...FIXTUR_AGENT_TEXT,
  id,
  seq,
  body: { text },
  traces: null,
  run_id,
});

const du = (id: string, seq: number, text: string): RaInlagg => ({
  ...FIXTUR_USER_TEXT,
  id,
  seq,
  body: { text },
});

const h = (event: string, data: unknown): TradHandling => ({
  typ: "handelse",
  handelse: { event, data } satisfies SseHandelse,
});

const skapad = (run: string) =>
  h("message.created", { id: `streaming-${run}`, type: "agent_text", actor: "agent", run_id: run });
const delta = (run: string, text: string) => h("message.delta", { id: `streaming-${run}`, text });
const aktivitet = (run: string, activity: string) =>
  h("message.delta", { id: `streaming-${run}`, activity });
const klar = (post: RaInlagg) => h("message.completed", post);

const texter = (t: TradTillstand) =>
  listaInlagg(t).map((i) => ("body" in i && "text" in i.body ? i.body.text : i.type));

// ─── GET-svaret ───────────────────────────────────────────────────────────

describe("tradReducer — GET-svaret (§6.3 rad 1)", () => {
  it("ersätter listan, sorterar på seq och sätter maxSeq = cursor", () => {
    const t = kor({
      typ: "hamtad",
      posts: [agent("p-3", 3, "tre"), du("p-1", 1, "ett"), agent("p-2", 2, "två")],
      cursor: 3,
    });
    expect(texter(t)).toEqual(["ett", "två", "tre"]);
    expect(t.maxSeq).toBe(3);
  });

  it("ett andra GET-svar ersätter det första i stället för att lägga till", () => {
    const t = kor(
      { typ: "hamtad", posts: [agent("p-1", 1, "gammal")], cursor: 1 },
      { typ: "hamtad", posts: [agent("p-9", 9, "ny")], cursor: 9 }
    );
    expect(texter(t)).toEqual(["ny"]);
  });

  it("okänd typ faller bort; kontraktsbrott blir okant_kontrakt — parseInlagg är vägen in", () => {
    const varning = vi.spyOn(console, "warn").mockImplementation(() => {});
    const t = kor({
      typ: "hamtad",
      posts: [
        { ...agent("p-1", 1, "x"), type: "hologram" },
        { ...agent("p-2", 2, "x"), body: { inte_text: 1 } },
      ],
      cursor: 2,
    });
    const lista = listaInlagg(t);
    expect(lista).toHaveLength(1);
    expect(lista[0]).toMatchObject({ id: "p-2", type: "okant_kontrakt" });
    varning.mockRestore();
  });
});

// ─── Det optimistiska inlägget ────────────────────────────────────────────

describe("tradReducer — optimistiskt user_text (testfall 12)", () => {
  const optimistisk: TradHandling = {
    typ: "optimistisk",
    id: "lokal-1",
    text: "Vad består kundfordringarna av?",
    skapad: "2026-09-23T08:00:00.000Z",
  };

  it("syns direkt, sist, som user_text med tillfälligt id (testfall 12)", () => {
    const t = kor({ typ: "hamtad", posts: [agent("p-1", 1, "hej")], cursor: 1 }, optimistisk);
    const lista = listaInlagg(t);
    expect(lista.map((i) => i.id)).toEqual(["p-1", "lokal-1"]);
    expect(lista[1]).toMatchObject({
      type: "user_text",
      body: { text: "Vad består kundfordringarna av?" },
    });
    expect(arOptimistisk(lista[1])).toBe(true);
    expect(arOptimistisk(lista[0])).toBe(false);
  });

  it("står kvar sist även när ett serverinlägg med högre seq strömmar in (testfall 12)", () => {
    const t = kor(optimistisk, klar(agent("p-7", 7, "svar från en tidigare tur")));
    expect(listaInlagg(t).map((i) => i.id)).toEqual(["p-7", "lokal-1"]);
  });

  it("ersätts av serverns inlägg på id när POST svarat (testfall 12)", () => {
    const t = kor(
      { typ: "hamtad", posts: [agent("p-1", 1, "hej")], cursor: 1 },
      optimistisk,
      { typ: "skickad", lokaltId: "lokal-1", posts: [du("p-2", 2, "Vad består kundfordringarna av?")], cursor: 2 }
    );
    const lista = listaInlagg(t);
    expect(lista.map((i) => i.id)).toEqual(["p-1", "p-2"]);
    expect(lista.some(arOptimistisk)).toBe(false);
    expect(t.maxSeq).toBe(2);
  });

  it("ett GET-svar som kommer sent tar inte bort det människan redan skrivit", () => {
    const t = kor(optimistisk, { typ: "hamtad", posts: [agent("p-1", 1, "hej")], cursor: 1 });
    expect(listaInlagg(t).map((i) => i.id)).toEqual(["p-1", "lokal-1"]);
  });

  it("misslyckat POST tar bort det optimistiska — tråden låtsas inte att servern lagrat det", () => {
    const t = kor({ typ: "hamtad", posts: [agent("p-1", 1, "hej")], cursor: 1 }, optimistisk, {
      typ: "misslyckad",
      lokaltId: "lokal-1",
    });
    expect(listaInlagg(t).map((i) => i.id)).toEqual(["p-1"]);
  });

  it("serverinlägget som spelats upp före POST-svaret blir ingen dubblett när svaret kommer", () => {
    // Återanslutning mitt i en tur kan spela upp människans inlägg som
    // `message.completed` innan POST-svaret hunnit fram.
    const t = kor(optimistisk, klar(du("p-2", 2, "Vad består kundfordringarna av?")), {
      typ: "skickad",
      lokaltId: "lokal-1",
      posts: [du("p-2", 2, "Vad består kundfordringarna av?")],
      cursor: 2,
    });
    expect(listaInlagg(t).map((i) => i.id)).toEqual(["p-2"]);
  });
});

// ─── Strömmen ─────────────────────────────────────────────────────────────

describe("tradReducer — strömmen (§6.3)", () => {
  it("message.created startar ett strömmande inlägg med streaming-id och tom text", () => {
    const t = kor(skapad("r-1"));
    expect(t.strommande).toEqual({ id: "streaming-r-1", run_id: "r-1", text: "", activity: null });
    // Platshållaren är inte ett inlägg i listan — den ritas av SkriverIndikator.
    expect(listaInlagg(t)).toEqual([]);
  });

  it("message.created med text och activity (en tur som redan pågick) blir platshållaren som den är", () => {
    // Servern skickar det en sen prenumerant missat som ett `created` med
    // det som sagts hittills (SPEC-chattyta §15, fråga 5).
    const t = kor(
      h("message.created", {
        id: "streaming-r-1",
        run_id: "r-1",
        text: "148 500 kr i tre",
        activity: "las_bankhandelser",
      }),
      delta("r-1", " fakturor.")
    );
    expect(t.strommande).toEqual({
      id: "streaming-r-1",
      run_id: "r-1",
      text: "148 500 kr i tre fakturor.",
      activity: "las_bankhandelser",
    });
  });

  it("en återanslutning mitt i en tur ersätter texten i stället för att dubbla den", () => {
    const t = kor(
      skapad("r-1"),
      delta("r-1", "148 500"),
      h("message.created", { id: "streaming-r-1", run_id: "r-1", text: "148 500 kr", activity: null })
    );
    expect(t.strommande?.text).toBe("148 500 kr");
  });

  it("delta {text} läggs till det strömmande inläggets text", () => {
    const t = kor(skapad("r-1"), delta("r-1", "Kund"), delta("r-1", "fordringar"));
    expect(t.strommande?.text).toBe("Kundfordringar");
  });

  it("delta {activity} byter indikatorns text utan att röra den ihopsamlade texten (testfall 11)", () => {
    let t = kor(skapad("r-1"), delta("r-1", "Jag tittar"));
    expect(t.strommande?.activity).toBeNull();
    t = tradReducer(t, aktivitet("r-1", "las_bankhandelser"));
    expect(t.strommande).toMatchObject({ text: "Jag tittar", activity: "las_bankhandelser" });
    t = tradReducer(t, aktivitet("r-1", "posta_verifikation"));
    expect(t.strommande?.activity).toBe("posta_verifikation");
    // En textdelta efteråt tömmer inte aktiviteten — indikatorn är aldrig tom.
    t = tradReducer(t, delta("r-1", " på det."));
    expect(t.strommande).toMatchObject({
      text: "Jag tittar på det.",
      activity: "posta_verifikation",
    });
  });

  it("en delta utan föregående message.created startar platshållaren ändå", () => {
    // Turen startar i POST; strömmen öppnas efter svaret och kan missa
    // `message.created`. En tyst tråd vore en anonym väntan.
    const t = kor(delta("r-1", "Hej"));
    expect(t.strommande).toEqual({ id: "streaming-r-1", run_id: "r-1", text: "Hej", activity: null });
  });

  it("delta {text} × n + completed: platshållaren ersätts av det lagrade, texten är den lagrade (testfall 10)", () => {
    const t = kor(
      { typ: "hamtad", posts: [du("p-1", 1, "fråga")], cursor: 1 },
      skapad("r-1"),
      delta("r-1", "Ihop"),
      delta("r-1", "samlad "),
      delta("r-1", "text"),
      klar(agent("p-2", 2, "Lagrad text.", "r-1"))
    );
    expect(t.strommande).toBeNull();
    expect(texter(t)).toEqual(["fråga", "Lagrad text."]);
    expect(t.maxSeq).toBe(2);
  });

  it("completed från en annan körning lämnar platshållaren kvar", () => {
    const t = kor(skapad("r-2"), delta("r-2", "pågår"), klar(agent("p-5", 5, "annat", "r-1")));
    expect(t.strommande?.id).toBe("streaming-r-2");
    expect(texter(t)).toEqual(["annat"]);
  });

  it("completed läggs in på sin seq, inte sist", () => {
    const t = kor(
      { typ: "hamtad", posts: [agent("p-1", 1, "ett"), agent("p-3", 3, "tre")], cursor: 3 },
      klar(agent("p-2", 2, "två"))
    );
    expect(texter(t)).toEqual(["ett", "två", "tre"]);
    expect(t.maxSeq).toBe(3);
  });

  it("återuppspelning av ett redan sett inlägg ger ingen dubblett (testfall 7)", () => {
    const fore = kor({ typ: "hamtad", posts: [agent("p-1", 1, "ett"), agent("p-2", 2, "två")], cursor: 2 });
    const efter = kor(
      { typ: "hamtad", posts: [agent("p-1", 1, "ett"), agent("p-2", 2, "två")], cursor: 2 },
      klar(agent("p-2", 2, "två")),
      klar(agent("p-1", 1, "ett"))
    );
    expect(texter(efter)).toEqual(["ett", "två"]);
    expect(efter.maxSeq).toBe(2);
    expect(listaInlagg(efter)).toEqual(listaInlagg(fore));
  });

  it("återuppspelning utan något nytt lämnar tillståndet orört (testfall 7)", () => {
    const t = kor({ typ: "hamtad", posts: [agent("p-1", 1, "ett")], cursor: 1 });
    expect(tradReducer(t, klar(agent("p-1", 1, "ett")))).toBe(t);
  });

  it("completed av okänd typ faller bort men tar ändå bort sin platshållare", () => {
    const t = kor(skapad("r-1"), klar({ ...agent("p-1", 1, "x", "r-1"), type: "hologram" }));
    expect(t.strommande).toBeNull();
    expect(listaInlagg(t)).toEqual([]);
  });

  it("view.changed, okända händelser och trasiga ramar rör inte tråden", () => {
    const t = kor({ typ: "hamtad", posts: [agent("p-1", 1, "ett")], cursor: 1 });
    for (const handling of [
      h("view.changed", { view_key: "verifikationer", changed: { voucher_id: "v-1", kind: "voucher_posted" } }),
      h("message.okand", { id: "x" }),
      h("message.completed", null),
      h("message.delta", { text: "utan id" }),
    ]) {
      expect(tradReducer(t, handling)).toBe(t);
    }
  });

  it("nollställ ger en tom tråd — vybyte börjar om", () => {
    const t = kor(
      { typ: "hamtad", posts: [agent("p-1", 1, "ett")], cursor: 1 },
      skapad("r-1"),
      { typ: "nollstall" }
    );
    expect(t).toEqual(tomTrad());
  });
});
