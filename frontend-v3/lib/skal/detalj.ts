/**
 * Detaljlagret (modul `skal`): ett kontos huvudbok och en verifikation.
 *
 * Lagret står i läskolumnens ställe och lämnar chatten och svepraden orörda.
 * Det är inte en vy: de sju `view_key` är en sluten lista (`vyer.ts`), och
 * chatten bredvid är fortfarande den underliggande vyns. Ett konto leder
 * till sin huvudbok, en huvudboksrad till sin verifikation och en kontering
 * tillbaka till kontots huvudbok.
 *
 * Som i `bocker.ts` är funktionerna här rena avbildningar från API-svar till
 * `VyData`. Beloppen är öre, debet positivt och kredit negativt.
 */

import apiClient from "@/lib/api";
import type { OverviewFiscalYear } from "@/lib/skal/api";
import { harUnderlag, underlagAlder, UTAN_UNDERLAG_TEXT, type Rattelse, type Verifikation, type VerifikationRef } from "@/lib/skal/bocker";
import { formatBeloppHela } from "@/lib/skal/format";
import type { VyData, VyRadData, VySektionData } from "@/lib/skal/vydata";
import { allaVyer, type Vynyckel } from "@/lib/skal/vyer";
import { formatVerifikationsnummer } from "@/lib/utils";

/** Det lagret visar. Bara det översta i stacken syns. */
export type Detalj = { typ: "konto"; kod: string } | { typ: "ver"; id: string };

/** Vart en rad leder: ett lager, eller en annan vy på samma sida. */
export type RadMal = Detalj | { typ: "vy"; key: Vynyckel };

export function sammaDetalj(a: Detalj, b: Detalj): boolean {
  if (a.typ === "konto") return b.typ === "konto" && a.kod === b.kod;
  return b.typ === "ver" && a.id === b.id;
}

// ─── API-svaren ───────────────────────────────────────────────────────────

/** `GET /reports/general-ledger/{kod}` (`api/routes/reports.py`). */
export interface Huvudbok {
  account_code: string;
  account_name: string;
  /** Kontots läge när perioden börjar: årets IB för ett balanskonto. */
  opening_balance: number;
  closing_balance: number;
  total_debit: number;
  total_credit: number;
  transaction_count: number;
  transactions: Array<{
    date: string;
    voucher_id: string;
    series: string;
    number: number | null;
    /** Radens text, annars verifikationens (den gamla huvudbokens fält). */
    description: string;
    /** Valfria: en server från före fälten skickar bara `description`. */
    voucher_description?: string;
    row_description?: string | null;
    debit: number;
    credit: number;
    balance: number;
  }>;
}

/** `GET /vouchers/{id}` (`VoucherResponse`), de fält detaljen läser. */
export interface VerifikationDetalj extends Verifikation {
  rows: Array<{
    id: string;
    account_code: string;
    account_name?: string | null;
    debit: number;
    credit: number;
    description?: string | null;
  }>;
  total_credit: number;
  created_by: string;
  /**
   * Vad verifikationen bokför, när en faktura, en betalning, ett lönebesked
   * eller en AGI postade den (`services/voucher_origin.py`). Valfri: en
   * äldre server skickar den inte, och en verifikation ur ett underlag har
   * ingen.
   */
  origin?: { kind: string; title: string; view_key: string } | null;
  /**
   * Verifikationens kommentar (migration 045), skriven när den skapades —
   * t.ex. växlingskursen ett utländskt belopp räknades om med, kursens datum
   * och källa. Ändras aldrig när verifikationen är postad. Valfri: en äldre
   * server skickar den inte.
   */
  comment?: string | null;
}

export const detaljApi = {
  getHuvudbok: async (kod: string, fiscalYearId: string): Promise<Huvudbok> => {
    const { data } = await apiClient.get<Huvudbok>(
      `/api/v1/reports/general-ledger/${encodeURIComponent(kod)}`,
      { params: { fiscal_year_id: fiscalYearId } }
    );
    return data;
  },

  getVerifikation: async (id: string): Promise<VerifikationDetalj> => {
    const { data } = await apiClient.get<VerifikationDetalj>(`/api/v1/vouchers/${encodeURIComponent(id)}`);
    return data;
  },
};

// ─── Avbildningarna ───────────────────────────────────────────────────────

const nummerAv = (r: { series: string; number: number | null }) =>
  formatVerifikationsnummer(r.number, r.series, "-");

/** Klass 1–2. Ett resultatkonto börjar året på noll och har ingen IB-rad. */
function arBalanskonto(kod: string): boolean {
  return kod.startsWith("1") || kod.startsWith("2");
}

/** Lagrets rubrik, som också står i tillbakalänken när lagret ovanpå stängs. */
export function huvudbokTitel(kod: string, namn?: string): string {
  return namn && namn !== kod ? `${kod} ${namn}` : `Konto ${kod}`;
}

export function verifikationTitel(v: { series: string; number: number | null; status: string }): string {
  return v.status === "draft" ? "Utkast" : `Verifikation ${nummerAv(v)}`;
}

/**
 * Kontots huvudbok för räkenskapsåret, i datumordning med löpande saldo.
 * Ett balanskonto börjar i årets ingående balans — IB är ingen verifikation
 * och har ingen rad att öppna — så att utgående saldo är balansräkningens.
 */
export function huvudbokVy(ar: OverviewFiscalYear, h: Huvudbok): VyData {
  const balans = arBalanskonto(h.account_code);
  const rader: VyRadData[] = [];
  if (balans) {
    rader.push({ id: "ib", titel: "Ingående balans", meta: ar.start, hoger: formatBeloppHela(h.opening_balance) });
  }
  h.transactions.forEach((t, i) => {
    // Titeln säger vad affären var (verifikationens text). Radens egen text
    // — på ett bankkonto ofta bankens, "Kortbetalning Visa" — står i metan.
    const titel = t.voucher_description ?? t.description;
    const radtext = t.row_description && t.row_description !== titel ? ` · ${t.row_description}` : "";
    rader.push({
      id: `${t.voucher_id}:${i}`,
      titel,
      meta: `${nummerAv(t)} · ${t.date}${radtext} · saldo ${formatBeloppHela(t.balance)}`,
      hoger: formatBeloppHela(t.debit - t.credit),
      mal: { typ: "ver", id: t.voucher_id },
    });
  });
  rader.push({ id: "ub", titel: "Utgående saldo", hoger: formatBeloppHela(h.closing_balance), summa: true });

  const tomt = h.transactions.length === 0;
  return {
    lage: tomt && h.opening_balance === 0 ? "tomt" : "normal",
    status: tomt ? "inga transaktioner" : `saldo ${formatBeloppHela(h.closing_balance)}`,
    period: `${ar.start} – ${ar.end} · ${h.transaction_count} transaktioner`,
    sektioner: [{ titel: "Huvudbok", rader }],
    fot: balans
      ? "Debet positivt, kredit negativt. Saldot börjar i årets ingående balans."
      : "Debet positivt, kredit negativt. Ett resultatkonto börjar räkenskapsåret på noll.",
  };
}

function hanvisning(id: string, titel: string, ref: VerifikationRef): VyRadData {
  return { id, titel, meta: nummerAv(ref), hoger: "", mal: { typ: "ver", id: ref.id } };
}

/**
 * Konteringen som den står efter rättelsen, som i en pappersbok (§7.5): en
 * kontering rättelsen tog bort stryks över, en ändrad visar beloppet före
 * överstruket, en ny säger det — och vid varje ändrad rad står med vilken
 * verifikation, när och av vem. Beloppen är netto per konto, så att en
 * återföring och dess nya rad inte syns som fyra rader.
 */
function rattadeKonteringar(r: Rattelse): VyRadData[] {
  const nar = `${nummerAv(r.correction)} ${r.correction_date}${r.actor ? ` · ${r.actor}` : ""}`;
  const rader: VyRadData[] = r.accounts.map((a) => {
    const rad: VyRadData = {
      id: `rattad-${a.account_code}`,
      titel: a.account_name || a.account_code,
      meta: a.account_code,
      hoger: formatBeloppHela(a.after),
      mal: { typ: "konto", kod: a.account_code },
    };
    if (a.before === a.after) return rad;
    if (a.after === 0)
      return { ...rad, meta: `${a.account_code} · borttagen ${nar}`, hoger: formatBeloppHela(a.before), struken: true };
    if (a.before === 0) return { ...rad, meta: `${a.account_code} · ny ${nar}` };
    return { ...rad, meta: `${a.account_code} · ändrad ${nar}`, hogerFore: formatBeloppHela(a.before) };
  });
  rader.push({
    id: "rattad-omslutning",
    titel: "Omslutning",
    hoger: formatBeloppHela(r.after_total),
    hogerFore: r.before_total !== r.after_total ? formatBeloppHela(r.before_total) : undefined,
    summa: true,
  });
  return rader;
}

/**
 * Verifikationen: konteringarna (varje konto leder till sin huvudbok),
 * underlaget och hänvisningarna till andra verifikationer. Ingenting här
 * ändrar verifikationen — en postad rättas med en ny i B-serien.
 */
export function verifikationVy(v: VerifikationDetalj): VyData {
  const utkast = v.status === "draft";
  const nummer = nummerAv(v);
  const saknar = !utkast && v.missing_attachment === true;

  const konteringar: VyRadData[] = v.rows.map((r) => ({
    id: r.id,
    titel: r.account_name || r.account_code,
    meta: r.description && r.description !== v.description ? `${r.account_code} · ${r.description}` : r.account_code,
    hoger: formatBeloppHela(r.debit - r.credit),
    mal: { typ: "konto", kod: r.account_code },
  }));
  konteringar.push({ id: "omslutning", titel: "Omslutning", hoger: formatBeloppHela(v.total_debit), summa: true });

  // En rättad verifikation visar först hur konteringen står nu, sedan den
  // som postades. En rättelse visar först vad den ändrade, sedan sina egna
  // rader — återföringen och de nya — som de bokfördes.
  const r = v.correction?.correction_status === "posted" ? v.correction : null;
  const rattelseNr = r ? nummerAv(r.correction) : "";
  const makulerad = r !== null && Boolean(v.corrected_by) && r.kind === "makulering";
  const sektioner: VySektionData[] = [];
  if (r && v.corrected_by) {
    sektioner.push({
      titel: makulerad ? `Makulerad med ${rattelseNr}` : `Kontering efter ${rattelseNr}`,
      rader: rattadeKonteringar(r),
    });
    sektioner.push({ titel: "Som postad", rader: konteringar });
  } else if (v.correction && v.corrects) {
    const vad = v.correction.kind === "makulering" ? "Makulerar" : "Ändrar";
    sektioner.push({ titel: `${vad} ${nummerAv(v.correction.original)}`, rader: rattadeKonteringar(v.correction) });
    sektioner.push({ titel: "Konteringar som bokförda", rader: konteringar });
  } else {
    sektioner.push({ titel: "Konteringar", rader: konteringar });
  }

  // Kommentaren, en rad per stycke: kursraden servern skrev, sedan agentens text.
  const kommentar = (v.comment ?? "")
    .split("\n")
    .map((t) => t.trim())
    .filter((t) => t.length > 0);
  if (kommentar.length > 0) {
    sektioner.push({
      titel: "Kommentar",
      rader: kommentar.map((text, i) => ({ id: `kommentar-${i}`, titel: text, hoger: "" })),
    });
  }

  // Var den kommer ifrån: lönebeskedet, AGI:n, fakturan eller betalningen.
  // Raden leder tillbaka till vyn där den bor, som vyns rad leder hit.
  if (v.origin) {
    const vy = allaVyer().find((x) => x.key === v.origin!.view_key);
    sektioner.push({
      titel: "Uppstod ur",
      rader: [
        {
          id: "ursprung",
          titel: v.origin.title,
          meta: vy ? `i ${vy.titel}` : undefined,
          hoger: "",
          mal: vy ? { typ: "vy", key: vy.key } : undefined,
        },
      ],
    });
  }

  if (!utkast) {
    const underlag: VyRadData = makulerad
      ? // Rättelsen dokumenterar varför; ett kvitto som finns går ändå att öppna.
        { id: "underlag", titel: "Underlag", meta: `makulerad med ${rattelseNr}`, hoger: "", kvitto: { voucherId: v.id, nummer } }
      : harUnderlag(v)
      ? { id: "underlag", titel: "Underlag", hoger: "", kvitto: { voucherId: v.id, nummer } }
      : saknar
        ? {
            id: "underlag",
            titel: "Underlag",
            meta: underlagAlder("", v.age_days),
            hoger: "",
            variant: (v.age_days ?? 0) < 0 ? undefined : "saknar",
            ageDays: (v.age_days ?? 0) < 0 ? undefined : v.age_days,
            underlagsval: { voucherId: v.id },
          }
        : v.underlag_waiver
        ? // Godkänd utan underlag (migration 051): vem och när, och `ångra`.
          {
            id: "underlag",
            titel: "Underlag",
            meta: `${UTAN_UNDERLAG_TEXT[v.underlag_waiver.reason]} · godkänt av ${v.underlag_waiver.waived_by} ${v.underlag_waiver.created_at.slice(0, 10)}`,
            hoger: "",
            underlagsval: { voucherId: v.id, godkant: v.underlag_waiver.reason },
          }
        : // En rättelses underlag är originalet (SPEC-flode-underlag.md D3).
          { id: "underlag", titel: "Underlag", meta: "originalets", hoger: "" };
    sektioner.push({ titel: "Underlag", rader: [underlag] });
  }

  const hanvisningar: VyRadData[] = [];
  if (v.corrects) hanvisningar.push(hanvisning("rattar", "Rättar", v.corrects));
  if (v.corrected_by) hanvisningar.push(hanvisning("rattad-av", "Rättad av", v.corrected_by));
  if (v.referenced_by) hanvisningar.push(hanvisning("korrigering", "Korrigering", v.referenced_by));
  if (hanvisningar.length > 0) sektioner.push({ titel: "Hänvisningar", rader: hanvisningar });

  const postad = v.posted_at ? ` · postad ${v.posted_at.slice(0, 10)}` : "";
  const vy: VyData = {
    lage: utkast || saknar ? "vantar" : "klart",
    status: utkast ? "utkast" : saknar ? "saknar underlag" : makulerad ? "makulerad · låst" : "postad · låst",
    period: `${v.date} · ${v.description}${postad}`,
    sektioner,
    fot: utkast
      ? "Utkastet är inte bokfört. Det postas från chatten."
      : "En postad verifikation ändras aldrig. Ett fel rättas med en ny verifikation i B-serien.",
  };
  if (r && v.corrected_by) {
    const vad = makulerad ? "Makulerad" : "Ändrad";
    const vem = r.actor ? ` av ${r.actor}` : "";
    const varfor = r.reason ? ` — ${r.reason}` : "";
    vy.banner = {
      ton: "neutral",
      text: `${vad} med ${rattelseNr} ${r.correction_date}${vem}${varfor}. Rättelsen står i en egen verifikation; den här ligger kvar som den postades.`,
    };
  } else if (v.corrected_by) {
    vy.banner = {
      ton: "neutral",
      text: `Rättad av ${nummerAv(v.corrected_by)}. Rättelsen står i en egen verifikation; den här ligger kvar som den postades.`,
    };
  }
  return vy;
}
