import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  FIXTUR_AGENT_TEXT,
  FIXTUR_DECISION,
  FIXTUR_DRAFT,
  FIXTUR_ERROR,
  FIXTUR_OPTIONS,
  FIXTUR_RECEIPT,
  FIXTUR_USER_FILE,
  FIXTUR_USER_TEXT,
  FIXTURER,
  kropp,
  kroppUtan,
  medKropp,
} from "@/lib/chattyta/__fixtures__/inlagg";
import { _glomVarnadeTyper, parseInlagg } from "@/lib/chattyta/parse";
import type { RaInlagg } from "@/lib/chattyta/typer";

beforeEach(() => {
  _glomVarnadeTyper();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("parseInlagg — de åtta typerna (testfall 1)", () => {
  it.each(FIXTURER.map((f) => [f.type, f] as const))(
    "%s blir sin egen variant, med kroppen orörd",
    (typ, fixtur) => {
      const inlagg = parseInlagg(fixtur);
      expect(inlagg).not.toBeNull();
      expect(inlagg!.type).toBe(typ);
      // Agenten formulerar (antagande 3): kroppen passerar ordagrant.
      expect("body" in inlagg! && inlagg.body).toEqual(fixtur.body);
    }
  );

  it("bär kuvertets fält vidare: id, seq, actor, created_at, traces, run_id", () => {
    const inlagg = parseInlagg(FIXTUR_AGENT_TEXT)!;
    expect(inlagg.id).toBe(FIXTUR_AGENT_TEXT.id);
    expect(inlagg.seq).toBe(FIXTUR_AGENT_TEXT.seq);
    expect(inlagg.actor).toBe("agent");
    expect(inlagg.created_at).toBe(FIXTUR_AGENT_TEXT.created_at);
    expect(inlagg.run_id).toBe(FIXTUR_AGENT_TEXT.run_id);
    expect(inlagg.traces).toEqual([
      { tool: "las_bankhandelser", label: "bankhändelser lästa" },
      {
        tool: "posta_verifikation",
        label: "verifikation postad",
        detail: "A-118",
        voucher_id: "v-118",
      },
    ]);
  });

  it("påminnelsen är ett agent_text som också bär decision_id", () => {
    const inlagg = parseInlagg(medKropp(FIXTUR_AGENT_TEXT, { text: "Påminnelse.", decision_id: "d-1" }));
    expect(inlagg?.type).toBe("agent_text");
  });

  it("amount: null i ett beslut är giltigt — ett avstående mitt i samtalet har inget belopp", () => {
    const inlagg = parseInlagg(medKropp(FIXTUR_DECISION, { ...kropp(FIXTUR_DECISION), amount: null, source: null }));
    expect(inlagg?.type).toBe("decision");
  });

  it("retry_draft_id: null i ett fel är giltigt — det är vad backenden skriver i dag", () => {
    expect(parseInlagg(FIXTUR_ERROR)?.type).toBe("error");
    expect((FIXTUR_ERROR.body as { retry_draft_id: unknown }).retry_draft_id).toBeNull();
  });

  it("traces som inte är en lista blir null; trasiga chips faller bort, hela inlägget gör det inte", () => {
    expect(parseInlagg({ ...FIXTUR_USER_TEXT, traces: "fel" as unknown as null })?.traces).toBeNull();
    const inlagg = parseInlagg({
      ...FIXTUR_AGENT_TEXT,
      traces: [{ tool: "x" }, { tool: "y", label: "y läst" }],
    });
    expect(inlagg?.type).toBe("agent_text");
    expect(inlagg?.traces).toEqual([{ tool: "y", label: "y läst" }]);
  });
});

describe("okänd typ (testfall 2)", () => {
  it("renderas inte, och loggas en gång per typ — inte en gång per inlägg", () => {
    const varning = vi.spyOn(console, "warn").mockImplementation(() => {});
    const okand: RaInlagg = { ...FIXTUR_USER_TEXT, type: "poll" };
    expect(parseInlagg(okand)).toBeNull();
    expect(parseInlagg({ ...okand, id: "annat" })).toBeNull();
    expect(varning).toHaveBeenCalledTimes(1);
    expect(varning.mock.calls[0].join(" ")).toContain("poll");
  });
});

describe("kontraktsbrott blir okant_kontrakt (testfall 3, 4)", () => {
  const brott = (raw: RaInlagg) => {
    const inlagg = parseInlagg(raw);
    expect(inlagg?.type).toBe("okant_kontrakt");
    return inlagg as Extract<NonNullable<typeof inlagg>, { type: "okant_kontrakt" }>;
  };

  it("options med två recommended — en rekommendation är ett märke, två är ett förval", () => {
    const body = FIXTUR_OPTIONS.body as { options: Array<Record<string, unknown>> };
    const inlagg = brott(
      medKropp(FIXTUR_OPTIONS, {
        ...body,
        options: body.options.map((o) => ({ ...o, recommended: !o.is_exit })),
      })
    );
    expect(inlagg.ursprungligTyp).toBe("options");
    expect(inlagg.brott).toMatch(/recommended/);
  });

  it("options där sista alternativet inte är en väg ut", () => {
    const body = FIXTUR_OPTIONS.body as { options: Array<Record<string, unknown>> };
    brott(medKropp(FIXTUR_OPTIONS, { ...body, options: body.options.slice(0, -1) }));
  });

  it("options utan alternativ alls — det finns ingen väg ut att vara sist", () => {
    brott(medKropp(FIXTUR_OPTIONS, { ...kropp(FIXTUR_OPTIONS), options: [] }));
  });

  it("receipt där en rad saknar ett av sina två tal (testfall 4)", () => {
    const body = FIXTUR_RECEIPT.body as { rows: Array<Record<string, unknown>> };
    const inlagg = brott(
      medKropp(FIXTUR_RECEIPT, { ...body, rows: [{ ...body.rows[0], right_ore: null }] })
    );
    expect(inlagg.brott).toMatch(/båda talen/);
  });

  it("receipt med tom rows är giltigt (frånkoppling utan jämförelse, underlag-ersatt)", () => {
    const inlagg = parseInlagg(medKropp(FIXTUR_RECEIPT, { ...kropp(FIXTUR_RECEIPT), rows: [] }));
    expect(inlagg?.type).toBe("receipt");
  });

  it("receipt utan rows alls", () => {
    brott(medKropp(FIXTUR_RECEIPT, kroppUtan(FIXTUR_RECEIPT, "rows")));
  });

  it("receipt utan två etiketter", () => {
    brott(medKropp(FIXTUR_RECEIPT, { ...kropp(FIXTUR_RECEIPT), labels: ["var"] }));
  });

  it("draft utan draft_id — klienten postar aldrig utan ett utkast-id", () => {
    brott(medKropp(FIXTUR_DRAFT, kroppUtan(FIXTUR_DRAFT, "draft_id")));
  });

  it("draft med kind ≠ voucher — faktura och lön är ur scope (§4.3)", () => {
    brott(medKropp(FIXTUR_DRAFT, { ...kropp(FIXTUR_DRAFT), kind: "invoice" }));
  });

  it("en draft-rad med både debet och kredit, eller ingetdera", () => {
    const body = FIXTUR_DRAFT.body as { rows: Array<Record<string, unknown>> };
    brott(medKropp(FIXTUR_DRAFT, { ...body, rows: [{ ...body.rows[0], credit_ore: 100 }] }));
    brott(medKropp(FIXTUR_DRAFT, { ...body, rows: [{ ...body.rows[0], debit_ore: null }] }));
  });

  it("ett beslut utan decision_id går inte att svara på och visas inte som ett", () => {
    brott(medKropp(FIXTUR_DECISION, kroppUtan(FIXTUR_DECISION, "decision_id")));
  });

  it.each([
    ["agent_text", FIXTUR_AGENT_TEXT, { text: 42 }],
    ["user_text", FIXTUR_USER_TEXT, {}],
    ["user_file", FIXTUR_USER_FILE, { filename: "a.pdf" }],
    ["error", FIXTUR_ERROR, { cause: "x" }],
  ] as const)("%s med en kropp som saknar sina fält", (_typ, fixtur, body) => {
    brott(medKropp(fixtur, body));
  });

  it("okant_kontrakt bär id och seq, så att raden kan säga vilket inlägg det gäller", () => {
    const inlagg = brott(medKropp(FIXTUR_DRAFT, { ...kropp(FIXTUR_DRAFT), kind: "payroll" }));
    expect(inlagg.id).toBe(FIXTUR_DRAFT.id);
    expect(inlagg.seq).toBe(FIXTUR_DRAFT.seq);
  });
});
