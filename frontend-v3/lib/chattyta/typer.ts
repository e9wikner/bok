/**
 * Trådens kontrakt i klienten (modul `chattyta`, SPEC-chattyta.md §4).
 *
 * En diskriminerad union över `type`, med kroppen typad per typ. Formen är
 * serverns, ordagrant: fältnamnen i `body` översätts inte, eftersom agenten
 * formulerar och klienten inte skriver om (antagande 3). Källorna är
 * `api/schemas.py::ThreadPostResponse`, `services/thread_service.py` och
 * `services/decision_service.py` — tabellen i SPEC §2. `draft` och
 * `receipt` har ingen producent än; deras form spikas i SPEC §4.3 och är
 * kontraktet `flode-verifikationer` skriver mot.
 *
 * Belopp är alltid i öre. Klienten formaterar, räknar aldrig (regel 2).
 *
 * Ett råinlägg blir en av de här typerna på ETT ställe: `parse.ts`.
 */

/** Ett inlägg som servern skickar det, före `parseInlagg`. */
export interface RaInlagg {
  id: string;
  seq: number;
  type: string;
  actor: string;
  created_at: string;
  body: unknown;
  traces?: unknown;
  run_id?: string | null;
}

/** Ett `SparChip`: vad agenten läste, räknade och gjorde (`build_trace`). */
export interface Spar {
  tool: string;
  /** På svenska, färdig att rendera. */
  label: string;
  /** En rad värd att visa, t.ex. `A-118`. */
  detail?: string;
  voucher_id?: string;
}

interface Kuvert {
  id: string;
  seq: number;
  actor: string;
  created_at: string;
  traces: Spar[] | null;
  run_id: string | null;
}

// ─── Kropparna ────────────────────────────────────────────────────────────

/** `RadLista/i-tråd` inuti ett agentsvar: en kolumn tal. */
export interface RadListaRad {
  key: string;
  text: string;
  amount_ore: number;
}

export interface AgentTextKropp {
  text: string;
  /** Sätts på påminnelsen (`_reminder_post_body`). */
  decision_id?: string;
  rows?: RadListaRad[];
}

export interface UserTextKropp {
  text: string;
}

export interface UserFileKropp {
  filename: string;
  size_bytes: number;
  pages: number | null;
  intake_source_id: string;
}

export interface BeslutKalla {
  kind: string;
  id: string;
}

export interface DecisionKropp {
  decision_id: string;
  title: string;
  /** Öre, eller `null` för ett avstående utan belopp. */
  amount: number | null;
  reason: string;
  source: BeslutKalla | null;
  consequence: string;
}

export interface Alternativ {
  option_id: string;
  title: string;
  account: string | null;
  amount_ore: number | null;
  rationale: string;
  /** Ett märke, inte ett val (SPEC §4.2). */
  recommended: boolean;
  is_exit: boolean;
}

export interface OptionsKropp {
  decision_id: string;
  options: Alternativ[];
  footnote: string | null;
}

export interface KonteringsRad {
  account: string;
  name: string;
  /** Exakt ett av de två är satt. */
  debit_ore: number | null;
  credit_ore: number | null;
}

export interface DraftKropp {
  /** `vouchers.id` för ett utkast. Klienten postar aldrig utan det (regel 3). */
  draft_id: string;
  /** `invoice` och `payroll` är ur scope och blir `okant_kontrakt`. */
  kind: "voucher";
  title: string;
  meta: string;
  rows: KonteringsRad[];
  footnote: string | null;
  /** Bär varningen. Inte metatext (komponenter.md). */
  consequence: string;
  decision_id: string | null;
}

export interface ErrorKropp {
  cause: string;
  consequence: string;
  /** `null` i allt backenden skriver i dag — då finns ingen `Försök igen` (SPEC §9). */
  retry_draft_id: string | null;
}

export interface JamforelseRad {
  key: string;
  text: string;
  /** Båda talen, alltid. En ensam ny summa är fel. */
  left_ore: number;
  right_ore: number;
}

export interface ReceiptKropp {
  title: string;
  /** `["var", "blir"]` eller `["kvitto", "A-118"]`. */
  labels: [string, string];
  rows: JamforelseRad[];
  voucher_id: string | null;
}

// ─── Unionen ──────────────────────────────────────────────────────────────

export type AgentTextInlagg = Kuvert & { type: "agent_text"; body: AgentTextKropp };
export type UserTextInlagg = Kuvert & { type: "user_text"; body: UserTextKropp };
export type UserFileInlagg = Kuvert & { type: "user_file"; body: UserFileKropp };
export type DecisionInlagg = Kuvert & { type: "decision"; body: DecisionKropp };
export type OptionsInlagg = Kuvert & { type: "options"; body: OptionsKropp };
export type DraftInlagg = Kuvert & { type: "draft"; body: DraftKropp };
export type ErrorInlagg = Kuvert & { type: "error"; body: ErrorKropp };
export type ReceiptInlagg = Kuvert & { type: "receipt"; body: ReceiptKropp };

/**
 * Ett kort som inte kan visas ärligt (SPEC §4.4). Säger att något finns
 * utan att låtsas veta vad — och bär `id`/`seq` så att raden kan peka ut
 * vilket inlägg det gäller.
 */
export type OkantKontraktInlagg = Kuvert & {
  type: "okant_kontrakt";
  ursprungligTyp: string;
  /** Vilken regel som bröts. För konsolen och testerna, inte för människan. */
  brott: string;
};

export type Inlagg =
  | AgentTextInlagg
  | UserTextInlagg
  | UserFileInlagg
  | DecisionInlagg
  | OptionsInlagg
  | DraftInlagg
  | ErrorInlagg
  | ReceiptInlagg
  | OkantKontraktInlagg;

export type InlaggsTyp = Exclude<Inlagg["type"], "okant_kontrakt">;

export const INLAGGSTYPER: readonly InlaggsTyp[] = [
  "agent_text",
  "user_text",
  "user_file",
  "decision",
  "options",
  "draft",
  "error",
  "receipt",
];
