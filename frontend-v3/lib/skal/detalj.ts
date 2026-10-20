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
import { harUnderlag, type Verifikation, type VerifikationRef } from "@/lib/skal/bocker";
import { formatBeloppHela } from "@/lib/skal/format";
import type { VyData, VyRadData, VySektionData } from "@/lib/skal/vydata";
import type { ViewKey } from "@/lib/skal/vyer";
import { formatVerifikationsnummer } from "@/lib/utils";

/** Det lagret visar. Bara det översta i stacken syns. */
export type Detalj = { typ: "konto"; kod: string } | { typ: "ver"; id: string };

/** Vart en rad leder: ett lager, eller en annan vy på samma sida. */
export type RadMal = Detalj | { typ: "vy"; key: ViewKey };

export function sammaDetalj(a: Detalj, b: Detalj): boolean {
  return a.typ === "konto" ? b.typ === "konto" && a.kod === b.kod : b.typ === "ver" && a.id === b.id;
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
    description: string;
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
    rader.push({
      id: `${t.voucher_id}:${i}`,
      titel: t.description,
      meta: `${nummerAv(t)} · ${t.date} · saldo ${formatBeloppHela(t.balance)}`,
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

  const sektioner: VySektionData[] = [{ titel: "Konteringar", rader: konteringar }];

  if (!utkast) {
    const underlag: VyRadData = harUnderlag(v)
      ? { id: "underlag", titel: "Underlag", hoger: "", kvitto: { voucherId: v.id, nummer } }
      : saknar
        ? {
            id: "underlag",
            titel: "Underlag",
            meta: `saknas sedan ${v.age_days ?? 0} dgr`,
            hoger: "",
            variant: "saknar",
            ageDays: v.age_days,
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
    status: utkast ? "utkast" : saknar ? "saknar underlag" : "postad · låst",
    period: `${v.date} · ${v.description}${postad}`,
    sektioner,
    fot: utkast
      ? "Utkastet är inte bokfört. Det postas från chatten."
      : "En postad verifikation ändras aldrig. Ett fel rättas med en ny verifikation i B-serien.",
  };
  if (v.corrected_by) {
    vy.banner = {
      ton: "neutral",
      text: `Rättad av ${nummerAv(v.corrected_by)}. Rättelsen står i en egen verifikation; den här ligger kvar som den postades.`,
    };
  }
  return vy;
}
