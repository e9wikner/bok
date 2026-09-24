/**
 * `parseInlagg` — det enda stället där ett råinlägg från servern blir en
 * typad sak (SPEC-chattyta.md §4.1).
 *
 * Den vägrar det som bryter kontraktet i stället för att rendera det halvt:
 * ett kort som ser rätt ut men bryter kontraktet är värre än inget kort
 * (SPEC-skal.md §13). Servern garanterar redan flera av reglerna
 * (SPEC-beslut.md §6.3); klienten kontrollerar ändå, av samma skäl som
 * append-only vaktas på tre ställen.
 *
 * Kroppen släpps igenom ORDAGRANT när den håller. Ingen text trimmas,
 * ingenting fylls i med standardvärden — agenten formulerar (antagande 3).
 */

import {
  INLAGGSTYPER,
  type Inlagg,
  type InlaggsTyp,
  type RaInlagg,
  type Spar,
} from "@/lib/chattyta/typer";

type Rad = Record<string, unknown>;

/** Ett brott, eller `null` om kroppen håller. */
type Kontroll = (body: Rad) => string | null;

const arStrang = (v: unknown): v is string => typeof v === "string";
const arHeltal = (v: unknown): v is number => Number.isInteger(v);
const arObjekt = (v: unknown): v is Rad =>
  typeof v === "object" && v !== null && !Array.isArray(v);

function saknar(body: Rad, falt: Record<string, (v: unknown) => boolean>): string | null {
  for (const [namn, ok] of Object.entries(falt)) {
    if (!ok(body[namn])) return `fältet ${namn} saknas eller har fel typ`;
  }
  return null;
}

const strangEllerNull = (v: unknown) => v === null || arStrang(v);
const heltalEllerNull = (v: unknown) => v === null || arHeltal(v);
const valfriStrang = (v: unknown) => v === undefined || arStrang(v);

const KONTROLLER: Record<InlaggsTyp, Kontroll> = {
  agent_text: (b) => {
    const fel = saknar(b, { text: arStrang, decision_id: valfriStrang });
    if (fel) return fel;
    if (b.rows === undefined) return null;
    if (!Array.isArray(b.rows)) return "rows är inte en lista";
    for (const r of b.rows) {
      if (!arObjekt(r) || saknar(r, { key: arStrang, text: arStrang, amount_ore: arHeltal })) {
        return "en rad i rows saknar key, text eller amount_ore";
      }
    }
    return null;
  },

  user_text: (b) => saknar(b, { text: arStrang }),

  user_file: (b) =>
    saknar(b, {
      filename: arStrang,
      size_bytes: arHeltal,
      pages: heltalEllerNull,
      intake_source_id: arStrang,
    }),

  decision: (b) => {
    const fel = saknar(b, {
      decision_id: arStrang,
      title: arStrang,
      amount: heltalEllerNull,
      reason: arStrang,
      consequence: arStrang,
    });
    if (fel) return fel;
    const k = b.source;
    if (k !== null && !(arObjekt(k) && arStrang(k.kind) && arStrang(k.id))) {
      return "source är varken null eller {kind, id}";
    }
    return null;
  },

  options: (b) => {
    const fel = saknar(b, { decision_id: arStrang, footnote: strangEllerNull });
    if (fel) return fel;
    if (!Array.isArray(b.options) || b.options.length === 0) {
      return "options är tom — det finns ingen väg ut att vara sist";
    }
    for (const o of b.options) {
      if (
        !arObjekt(o) ||
        saknar(o, {
          option_id: arStrang,
          title: arStrang,
          account: strangEllerNull,
          amount_ore: heltalEllerNull,
          rationale: arStrang,
          recommended: (v) => typeof v === "boolean",
          is_exit: (v) => typeof v === "boolean",
        })
      ) {
        return "ett alternativ saknar sina fält";
      }
    }
    const alternativ = b.options as Rad[];
    // komponenter.md: högst en rekommendation, och sista är alltid en väg ut.
    if (alternativ.filter((o) => o.recommended).length > 1) {
      return "mer än ett alternativ är recommended";
    }
    if (!alternativ[alternativ.length - 1].is_exit) {
      return "sista alternativet är inte is_exit";
    }
    return null;
  },

  draft: (b) => {
    const fel = saknar(b, {
      draft_id: arStrang,
      title: arStrang,
      meta: arStrang,
      footnote: strangEllerNull,
      consequence: arStrang,
      decision_id: strangEllerNull,
    });
    if (fel) return fel;
    // Faktura- och löneförslag är ur scope (ANALYS.md §2, SPEC §4.3).
    if (b.kind !== "voucher") return `kind ${String(b.kind)} renderas inte`;
    if (!Array.isArray(b.rows) || b.rows.length === 0) return "rows saknas";
    for (const r of b.rows) {
      if (!arObjekt(r) || saknar(r, { account: arStrang, name: arStrang })) {
        return "en konteringsrad saknar konto eller namn";
      }
      const debet = arHeltal(r.debit_ore);
      const kredit = arHeltal(r.credit_ore);
      if (debet === kredit || !heltalEllerNull(r.debit_ore) || !heltalEllerNull(r.credit_ore)) {
        return "en konteringsrad har inte exakt ett av debet och kredit";
      }
    }
    return null;
  },

  error: (b) =>
    saknar(b, { cause: arStrang, consequence: arStrang, retry_draft_id: strangEllerNull }),

  receipt: (b) => {
    const fel = saknar(b, { title: arStrang, voucher_id: strangEllerNull });
    if (fel) return fel;
    if (!Array.isArray(b.labels) || b.labels.length !== 2 || !b.labels.every(arStrang)) {
      return "labels är inte två strängar";
    }
    if (!Array.isArray(b.rows) || b.rows.length === 0) return "rows saknas";
    for (const r of b.rows) {
      if (!arObjekt(r) || saknar(r, { key: arStrang, text: arStrang })) {
        return "en rad saknar key eller text";
      }
      // En ensam ny summa är en lögn om vad som ändras (komponenter.md).
      if (!arHeltal(r.left_ore) || !arHeltal(r.right_ore)) {
        return "en rad visar inte båda talen";
      }
    }
    return null;
  },
};

function parseSpar(traces: unknown): Spar[] | null {
  if (!Array.isArray(traces)) return null;
  // Ett trasigt chip faller bort; inlägget gör det inte. Spåren är
  // agentens redovisning, inte kortets kontrakt.
  return traces.filter(
    (t): t is Spar => arObjekt(t) && arStrang(t.tool) && arStrang(t.label)
  );
}

const varnadeTyper = new Set<string>();

/** Bara för testerna: varningen för okänd typ går en gång per process. */
export function _glomVarnadeTyper() {
  varnadeTyper.clear();
}

/**
 * Råinlägg → typat inlägg, `okant_kontrakt`, eller `null` för en typ
 * klienten inte känner till. En okänd typ loggas en gång per typ, inte en
 * gång per inlägg — en tråd med hundra av dem ska inte dränka konsolen.
 */
export function parseInlagg(raw: RaInlagg): Inlagg | null {
  const kuvert = {
    id: raw.id,
    seq: raw.seq,
    actor: raw.actor,
    created_at: raw.created_at,
    traces: parseSpar(raw.traces),
    run_id: raw.run_id ?? null,
  };

  if (!(INLAGGSTYPER as readonly string[]).includes(raw.type)) {
    if (!varnadeTyper.has(raw.type)) {
      varnadeTyper.add(raw.type);
      console.warn(`[chattyta] okänd inläggstyp renderas inte: ${raw.type}`);
    }
    return null;
  }

  const typ = raw.type as InlaggsTyp;
  const brott = arObjekt(raw.body) ? KONTROLLER[typ](raw.body) : "body är inte ett objekt";
  if (brott) {
    return { ...kuvert, type: "okant_kontrakt", ursprungligTyp: typ, brott };
  }
  // Kontrollen ovan är beviset för att kroppen har typens form.
  return { ...kuvert, type: typ, body: raw.body } as Inlagg;
}
