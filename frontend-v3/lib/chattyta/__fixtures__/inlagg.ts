/**
 * Ett råinlägg per typ, i serverns form (SPEC-chattyta.md §2).
 *
 * `FIXTUR_DRAFT.body` och `FIXTUR_RECEIPT.body` är ORDAGRANT §4.3:s JSON —
 * det är kontraktet `flode-verifikationer` skriver mot, och
 * `__tests__/parse.test.ts` läser specen och jämför. Ändras den ena ska den
 * andra ändras i samma commit. Platshållar-id:na (`<vouchers.id, …>`) är
 * alltså avsiktliga.
 *
 * De övriga sex följer kropparna backenden skriver i dag:
 * `services/thread_service.py` (`_error_body`, `_decision_body`,
 * `build_trace`) och `services/decision_service.py` (`_decision_post_body`,
 * `_options_post_body`). Exempeldatan är designens.
 */

import type { RaInlagg } from "@/lib/chattyta/typer";

const SKAPAD = "2026-09-18T06:41:00+00:00";

export const FIXTUR_AGENT_TEXT: RaInlagg = {
  id: "p-1",
  seq: 1,
  type: "agent_text",
  actor: "agent",
  created_at: SKAPAD,
  body: {
    text: "Jag postar elnätsfakturan från Nordkraft nu. Den matchar bankhändelsen på öret.",
  },
  traces: [
    { tool: "las_bankhandelser", label: "bankhändelser lästa" },
    {
      tool: "posta_verifikation",
      label: "verifikation postad",
      detail: "A-118",
      voucher_id: "v-118",
    },
  ],
  run_id: "r-1",
};

export const FIXTUR_USER_TEXT: RaInlagg = {
  id: "p-2",
  seq: 2,
  type: "user_text",
  actor: "api",
  created_at: SKAPAD,
  body: { text: "Vad består kundfordringarna av?" },
  traces: null,
  run_id: null,
};

export const FIXTUR_USER_FILE: RaInlagg = {
  id: "p-3",
  seq: 3,
  type: "user_file",
  actor: "api",
  created_at: SKAPAD,
  body: {
    filename: "kvitto-clas-ohlson.pdf",
    size_bytes: 218000,
    pages: 1,
    intake_source_id: "i-7",
  },
  traces: null,
  run_id: null,
};

export const FIXTUR_DECISION: RaInlagg = {
  id: "p-4",
  seq: 4,
  type: "decision",
  actor: "agent",
  created_at: SKAPAD,
  body: {
    decision_id: "d-1",
    title: "Swish 4 500 kr utan referens",
    amount: 450000,
    reason:
      "Beloppet stämmer med faktura 1044, men avsändaren är en privatperson. Jag bokför den inte mot kundfordran på gissning.",
    source: { kind: "bank", id: "b-31" },
    consequence: "Ingenting är bokfört. Beslutet ligger kvar tills du svarar på det.",
  },
  traces: null,
  run_id: "r-2",
};

export const FIXTUR_OPTIONS: RaInlagg = {
  id: "p-5",
  seq: 5,
  type: "options",
  actor: "agent",
  created_at: SKAPAD,
  body: {
    decision_id: "d-1",
    options: [
      {
        option_id: "o-1",
        title: "Betalning av faktura 1044",
        account: "1510",
        amount_ore: 450000,
        rationale: "Beloppet och datumet stämmer; avsändaren kan betala för kundens räkning.",
        recommended: true,
        is_exit: false,
      },
      {
        option_id: "o-2",
        title: "Övrig intäkt",
        account: "3990",
        amount_ore: 450000,
        rationale: "Om betalningen inte hör till någon faktura.",
        recommended: false,
        is_exit: false,
      },
      {
        option_id: "o-3",
        title: "Annat konto",
        account: null,
        amount_ore: null,
        rationale: "Skriv vad det är, så konterar jag därefter.",
        recommended: false,
        is_exit: true,
      },
    ],
    footnote: "Ingen moms i något av alternativen",
  },
  traces: null,
  run_id: "r-2",
};

/** SPEC-chattyta.md §4.3, ordagrant. */
export const FIXTUR_DRAFT: RaInlagg = {
  id: "p-6",
  seq: 6,
  type: "draft",
  actor: "agent",
  created_at: SKAPAD,
  body: {
    draft_id: "<vouchers.id, status=draft>",
    kind: "voucher",
    title: "Kontorsmaterial, Clas Ohlson",
    meta: "A · 2026-09-18",
    rows: [
      { account: "6110", name: "Kontorsmateriel", debit_ore: 71680, credit_ore: null },
      { account: "2640", name: "Ingående moms", debit_ore: 17920, credit_ore: null },
      { account: "1930", name: "Företagskonto", debit_ore: null, credit_ore: 89600 },
    ],
    footnote: "Underlag: kvitto 2026-09-18 · kompletteringsflagga sätts inte",
    consequence: "Låses vid postning · period september öppen till 2026-10-12",
    decision_id: "<om förslaget kommer ur ett besvarat beslut, annars null>",
  },
  traces: null,
  run_id: "r-3",
};

export const FIXTUR_ERROR: RaInlagg = {
  id: "p-7",
  seq: 7,
  type: "error",
  actor: "agent",
  created_at: SKAPAD,
  body: {
    cause: "period_locked: september 2026",
    consequence: "Ingenting är bokfört.",
    retry_draft_id: null,
  },
  traces: null,
  run_id: "r-3",
};

/** SPEC-chattyta.md §4.3, ordagrant. */
export const FIXTUR_RECEIPT: RaInlagg = {
  id: "p-8",
  seq: 8,
  type: "receipt",
  actor: "agent",
  created_at: SKAPAD,
  body: {
    title: "A-118 postad",
    labels: ["var", "blir"],
    rows: [{ key: "1510", text: "Kundfordringar", left_ore: 14850000, right_ore: 14400000 }],
    voucher_id: "<id, när kvittot gäller en postning>",
  },
  traces: null,
  run_id: "r-3",
};

export const FIXTURER: readonly RaInlagg[] = [
  FIXTUR_AGENT_TEXT,
  FIXTUR_USER_TEXT,
  FIXTUR_USER_FILE,
  FIXTUR_DECISION,
  FIXTUR_OPTIONS,
  FIXTUR_DRAFT,
  FIXTUR_ERROR,
  FIXTUR_RECEIPT,
];

/** Samma inlägg med en annan kropp — för kontraktsbrotten i testerna. */
export function medKropp(fixtur: RaInlagg, body: unknown): RaInlagg {
  return { ...fixtur, body };
}

/** Fixturens kropp som ett objekt att sprida och ändra i. */
export function kropp(fixtur: RaInlagg): Record<string, unknown> {
  return fixtur.body as Record<string, unknown>;
}

/** Fixturens kropp utan ett fält. */
export function kroppUtan(fixtur: RaInlagg, falt: string): Record<string, unknown> {
  return Object.fromEntries(Object.entries(kropp(fixtur)).filter(([k]) => k !== falt));
}
