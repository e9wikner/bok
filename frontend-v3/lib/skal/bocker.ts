/**
 * Böckernas tre vyer ur riktiga data (modul `skal`).
 *
 * Serverns rapporter för det räkenskapsår översikten pekar ut. Funktionerna
 * här är rena avbildningar från API-svar till `VyData`; hämtningen ligger i
 * `bockerApi` och cachningen i `hooks/useVyer.ts`.
 *
 * Beloppen kommer i öre och visas i hela kronor, som designen kräver.
 */

import apiClient from "@/lib/api";
import { formatBelopp, formatBeloppHela } from "@/lib/skal/format";
import { formatVerifikationsnummer } from "@/lib/utils";
import { parBelopp, type VyData, type VyRadData, type VySektionData } from "@/lib/skal/vydata";
import type { OverviewFiscalYear } from "@/lib/skal/api";
import {
  oppnaFil,
  underlagsfilSokvag,
  type BeslutSvar,
  type ForslagStatusSvar,
  type UtanUnderlag,
} from "@/lib/chattyta/api";
import type { Koppling } from "@/lib/chattyta/kopplingar";
import type { Postning } from "@/lib/chattyta/postningar";
import { periodnamn, type LasData, type Period } from "@/lib/skal/las";

// ─── API-svaren, bara de fält vyerna läser ────────────────────────────────

export interface BalansKonto {
  code: string;
  name: string;
  opening_balance: number;
  change: number;
  closing_balance: number;
}

export interface Balansrakning {
  closing_assets: number;
  closing_equity_liabilities: number;
  /** stated: första årets, angiven · derived: ur föregående år · none: saknas */
  opening_balance_source: "stated" | "derived" | "none";
  fixed_assets_details: BalansKonto[];
  receivables_details: BalansKonto[];
  bank_and_cash_details: BalansKonto[];
  current_assets_details: BalansKonto[];
  equity_details: BalansKonto[];
  long_term_liabilities_details: BalansKonto[];
  current_liabilities_details: BalansKonto[];
}

export interface ResultatKonto {
  code: string;
  name: string;
  amount: number;
}

export interface Resultatrakning {
  revenue: number;
  costs: number;
  financial: number;
  operating_profit: number;
  profit: number;
  revenue_details: ResultatKonto[];
  cost_details: ResultatKonto[];
  financial_details: ResultatKonto[];
  voucher_count: number;
}

export interface Verifikation {
  id: string;
  series: string;
  /** `null` för ett utkast; numret sätts vid postning. */
  number: number | null;
  date: string;
  description: string;
  status: string;
  total_debit: number;
  missing_attachment?: boolean;
  /** Serverns `age_days` (hela dagar sedan verifikationsdatumet). Klienten räknar den inte. */
  age_days?: number;
  /**
   * Medan verifikationen saknar underlag: kontoutdragskontona (1630,
   * 1900–1989) vars rader ännu saknar en kopplad transaktion. Tom för ett
   * inköp — dess underlag är ett kvitto.
   */
  missing_statement_accounts?: string[];
  posted_at?: string | null;
  /** Den postade rättelsen av den här (flode-verifikationer §7.5). */
  corrected_by?: VerifikationRef | null;
  /** Verifikationen den här rättar. */
  corrects?: VerifikationRef | null;
  /**
   * Den postade verifikation som hänvisar till den här verifikationens
   * kvitto: A-121 för A-118. Valfri: en
   * server från före FU16 skickar den inte.
   */
  referenced_by?: VerifikationRef | null;
  /**
   * En människas godkännande att stå utan underlag (migration 051), medan
   * det är det som håller verifikationen ur `Saknar underlag`. Valfri: en
   * äldre server skickar den inte.
   */
  underlag_waiver?: UtanUnderlagGodkannande | null;
  /**
   * Vad en rättelse gjorde (`api/schemas.py::VoucherCorrectionResponse`):
   * på en rättad verifikation alla dess postade rättelser sammantagna, på
   * en rättelse just den. Valfri: en äldre server skickar den inte.
   */
  correction?: Rattelse | null;
}

/** `api/schemas.py::UnderlagWaiverResponse`. */
export interface UtanUnderlagGodkannande {
  id: string;
  reason: UtanUnderlag;
  note?: string | null;
  waived_by: string;
  created_at: string;
}

/** Metans ord för ett godkännande utan underlag. */
export const UTAN_UNDERLAG_TEXT: Record<UtanUnderlag, string> = {
  later: "underlag kommer senare",
  none: "inget underlag behövs",
};

/** `api/schemas.py::VoucherCorrectionResponse`. Belopp i öre, netto debet − kredit per konto. */
export interface Rattelse {
  kind: "makulering" | "andring";
  /** `Makulering av A-53: …` — serverns rubrik för rättelsen. */
  title: string;
  original: VerifikationRef;
  original_description: string;
  correction: VerifikationRef;
  correction_date: string;
  correction_status: string;
  posted_at?: string | null;
  actor?: string | null;
  reason?: string | null;
  before_total: number;
  after_total: number;
  accounts: Array<{ account_code: string; account_name?: string | null; before: number; after: number }>;
}

/** `api/schemas.py::VoucherRefResponse`. */
export interface VerifikationRef {
  id: string;
  series: string;
  number: number | null;
}

export interface Verifikationslista {
  total: number;
  vouchers: Verifikation[];
}

/**
 * `GET /vouchers/{id}/source-context`, det kvittolänken läser. En källa
 * via en hänvisning (A-121 → kvittot via A-118, FU16) står bland de andra
 * med `via_voucher_id`.
 */
export interface Kallkontext {
  source_material: Array<{
    kind: string;
    id: string;
    original_filename?: string;
    via_voucher_id?: string | null;
  }>;
  /**
   * Kontoutdragstransaktionerna som är verifikationens underlag
   * (`services/statement_match.py`), med filen de kom från. Valfri: en
   * server från före kontoutdragen skickar den inte.
   */
  statement_links?: Array<{
    account_code: string;
    date: string;
    amount_ore: number;
    description: string | null;
    original_filename: string | null;
    download_url: string | null;
  }>;
}

/**
 * Filen kvittolänken öppnar: kvittot om det finns ett, annars kontoutdraget
 * med den första kopplade transaktionen.
 */
export function underlagsfil(ctx: Kallkontext): string | null {
  const kvitto = kvittoKalla(ctx);
  if (kvitto !== null) return underlagsfilSokvag(kvitto);
  return (ctx.statement_links ?? []).find((l) => l.download_url)?.download_url ?? null;
}

/**
 * Källan kvittolänken öppnar: en kopplad `voucher_source`, och bara om
 * ingen finns en via hänvisningen. Bankfiler är inga kvitton.
 */
export function kvittoKalla(ctx: Kallkontext): string | null {
  const kallor = (ctx.source_material ?? []).filter((k) => k.kind === "voucher_source");
  const egen = kallor.find((k) => !k.via_voucher_id);
  return (egen ?? kallor[0])?.id ?? null;
}

/**
 * Öppna verifikationens kvitto. `source-context` hämtas här, när länken
 * används — inte per rad (FU23). `false` när verifikationen inte har något.
 */
export function oppnaKvitto(voucherId: string): Promise<boolean> {
  return oppnaFil(async () => underlagsfil(await bockerApi.getKallkontext(voucherId)));
}

/** Postade hämtas så många i taget; nästa sida när listans slut syns. */
export const VERIFIKATIONER_ANTAL = 50;

/**
 * Postades hämtade sidor som en lista. Listan kan ha ändrats mellan två
 * sidor — en ny postning skjuter allt ett steg — så en verifikation står
 * bara på sin första plats. `total` är den senast hämtade sidans.
 */
export function slaSamman(sidor: readonly Verifikationslista[]): Verifikationslista {
  const sedda = new Set<string>();
  const vouchers: Verifikation[] = [];
  for (const sida of sidor) {
    for (const v of sida.vouchers) {
      if (sedda.has(v.id)) continue;
      sedda.add(v.id);
      vouchers.push(v);
    }
  }
  return { total: sidor[sidor.length - 1]?.total ?? 0, vouchers };
}

/** Nästa sidas `offset`, eller `undefined` när `total` är nådd (eller sidan var tom). */
export function nastaSida(sida: Verifikationslista, offset: number): number | undefined {
  const nasta = offset + sida.vouchers.length;
  return sida.vouchers.length > 0 && nasta < sida.total ? nasta : undefined;
}

/** En kontoutdragsrad som ingen verifikation står för (`GET /bank-inputs/transactions/open`). */
export interface OppenBanktransaktion {
  bank_transaction_id: string;
  account_code: string;
  date: string;
  /** Öre, negativt ut från kontot. */
  amount_ore: number;
  description: string | null;
  /** `candidates`: postade verifikationer som kan vara den; `none`: ingen. */
  match: "exact" | "candidates" | "none";
  candidates: { voucher_id: string; voucher_number: string; voucher_date: string; date_diff_days: number }[];
}

/** Ett kontos senaste kontoutdrag mot bokföringen samma dag. */
export interface Bankavstamning {
  account_code: string;
  date: string;
  statement_balance_ore: number;
  ledger_balance_ore: number;
  /** Utdraget minus bokföringen. */
  difference_ore: number;
  filename: string;
}

export interface OppnaBanktransaktioner {
  total: number;
  items: OppenBanktransaktion[];
  reconciliation?: Bankavstamning[];
}

export const bockerApi = {
  getOppnaBanktransaktioner: async (fiscalYearId: string): Promise<OppnaBanktransaktioner> => {
    const { data } = await apiClient.get<OppnaBanktransaktioner>("/api/v1/bank-inputs/transactions/open", {
      params: { fiscal_year_id: fiscalYearId },
    });
    return data;
  },

  getBalansrakning: async (fiscalYearId: string): Promise<Balansrakning> => {
    const { data } = await apiClient.get<Balansrakning>("/api/v1/reports/balance-sheet", {
      params: { fiscal_year_id: fiscalYearId },
    });
    return data;
  },

  getResultatrakning: async (fiscalYearId: string): Promise<Resultatrakning> => {
    const { data } = await apiClient.get<Resultatrakning>("/api/v1/reports/income-statement", {
      params: { fiscal_year_id: fiscalYearId },
    });
    return data;
  },

  /**
   * `missingAttachment`: `false` ger Postade
   * utan dem som saknar underlag, så att en verifikation står på ett ställe.
   * Utelämnad skickas den inte. `offset` sidar Postade.
   */
  getVerifikationer: async (
    fiscalYearId: string,
    status: "posted" | "draft",
    limit?: number,
    missingAttachment?: boolean,
    offset?: number
  ): Promise<Verifikationslista> => {
    const { data } = await apiClient.get<Verifikationslista>("/api/v1/vouchers", {
      params: {
        fiscal_year_id: fiscalYearId,
        status,
        limit,
        offset,
        sort_by: "date",
        sort_order: "desc",
        exclude_series: "IB",
        missing_attachment: missingAttachment,
      },
    });
    return data;
  },

  /**
   * Sektionen `Saknar underlag` (§10.4): postade verifikationer som saknar
   * underlag, äldst först — `sort_by=age` är stigande som standard
   * (`VoucherRepository.list_all`). Samma predikat som headerns räknare.
   */
  getKallkontext: async (voucherId: string): Promise<Kallkontext> => {
    const { data } = await apiClient.get<Kallkontext>(
      `/api/v1/vouchers/${encodeURIComponent(voucherId)}/source-context`
    );
    return data;
  },

  getSaknarUnderlag: async (fiscalYearId: string): Promise<Verifikationslista> => {
    const { data } = await apiClient.get<Verifikationslista>("/api/v1/vouchers", {
      params: {
        fiscal_year_id: fiscalYearId,
        status: "posted",
        missing_attachment: true,
        sort_by: "age",
        exclude_series: "IB",
      },
    });
    return data;
  },
};

// ─── Avbildningarna ───────────────────────────────────────────────────────

function arsrubrik(ar: OverviewFiscalYear): string {
  return `${ar.start} – ${ar.end}`;
}

/**
 * BAS-kontoplanens grupper, som balans- och resultaträkningen ställs upp i
 * (ÅRL:s scheman, förkortade). Första träffen vinner: längre prefix först.
 */
const BAS_GRUPPER: [string, string][] = [
  ["10", "Immateriella anläggningstillgångar"],
  ["11", "Materiella anläggningstillgångar"],
  ["12", "Materiella anläggningstillgångar"],
  ["13", "Finansiella anläggningstillgångar"],
  ["14", "Varulager"],
  ["15", "Kortfristiga fordringar"],
  ["16", "Kortfristiga fordringar"],
  ["17", "Kortfristiga fordringar"],
  ["18", "Kortfristiga placeringar"],
  ["19", "Kassa och bank"],
  ["20", "Eget kapital"],
  ["21", "Obeskattade reserver"],
  ["22", "Avsättningar"],
  ["23", "Långfristiga skulder"],
  ["2", "Kortfristiga skulder"],
  ["38", "Aktiverat arbete"],
  ["39", "Övriga rörelseintäkter"],
  ["3", "Nettoomsättning"],
  ["4", "Varor, material och tjänster"],
  ["5", "Övriga externa kostnader"],
  ["6", "Övriga externa kostnader"],
  ["77", "Av- och nedskrivningar"],
  ["78", "Av- och nedskrivningar"],
  ["79", "Övriga rörelsekostnader"],
  ["7", "Personalkostnader"],
  ["88", "Bokslutsdispositioner"],
  ["89", "Skatt"],
  ["8", "Finansiella poster"],
];

/** Kontots grupp i BAS, eller ingen för ett nummer utanför planen. */
export function basGrupp(kod: string): string | undefined {
  return BAS_GRUPPER.find(([prefix]) => kod.startsWith(prefix))?.[1];
}

export function kontorad(k: { code: string; name: string }, belopp: number): VyRadData {
  return {
    id: k.code,
    titel: k.name,
    nummer: k.code,
    grupp: basGrupp(k.code),
    hoger: formatBeloppHela(belopp),
    mal: { typ: "konto", kod: k.code },
  };
}

export function summarad(id: string, titel: string, belopp: number): VyRadData {
  return { id, titel, hoger: formatBeloppHela(belopp), summa: true };
}

function sorterade(...listor: BalansKonto[][]): BalansKonto[] {
  return listor
    .flat()
    // Ett konto som tömts under året står kvar: dess förändring är en del av bilden.
    .filter((k) => k.closing_balance !== 0 || k.opening_balance !== 0 || k.change !== 0)
    .sort((a, b) => a.code.localeCompare(b.code));
}

/** En förändring med tecken: "+12 000", "−3 500", "0". */
export function formatForandring(belopp: number): string {
  const s = formatBeloppHela(belopp);
  return belopp > 0 && s !== "0" ? `+${s}` : s;
}

function summa(konton: BalansKonto[], falt: "opening_balance" | "change"): number {
  return konton.reduce((acc, k) => acc + k[falt], 0);
}

/** Ett kontos rad med ingående balans och förändring före saldot. */
function balansrad(k: BalansKonto): VyRadData {
  return {
    ...kontorad(k, k.closing_balance),
    kolumner: [formatBeloppHela(k.opening_balance), formatForandring(k.change)],
  };
}

function balanssumma(id: string, titel: string, ib: number, forandring: number, ub: number): VyRadData {
  return {
    ...summarad(id, titel, ub),
    kolumner: [formatBeloppHela(ib), formatForandring(forandring)],
  };
}

/** Varifrån årets ingående balans kommer — IB är ingen verifikation. */
const IB_FOT: Record<Balansrakning["opening_balance_source"], string> = {
  derived: "Ingående balanser framräknade ur föregående räkenskapsårs utgående balans.",
  stated: "Ingående balanser angivna för första räkenskapsåret i böckerna.",
  none: "Räkenskapsåret saknar ingående balans.",
};

/**
 * Balansräkningen med tre kolumner per konto: ingående balans, årets
 * förändring och saldot — nuvarande under ett pågående år, utgående när
 * året är slut. Årets resultat räknas med.
 *
 * Serverns summa för eget kapital och skulder omfattar bara klass 2. Förrän
 * årets resultat är bokat mot 2099 ligger det i resultatkontona, så det
 * läggs till som en egen rad ur resultaträkningen. Då ska summorna mötas;
 * gör de inte det är vyn i felläge.
 */
export function balansVy(
  ar: OverviewFiscalYear,
  b: Balansrakning,
  r: Resultatrakning,
  idag: string = new Date().toISOString().slice(0, 10)
): VyData {
  const tillgangar = sorterade(
    b.fixed_assets_details,
    b.current_assets_details,
    b.receivables_details,
    b.bank_and_cash_details
  );
  const skulder = sorterade(
    b.equity_details,
    b.long_term_liabilities_details,
    b.current_liabilities_details
  );

  const summaSkulder = b.closing_equity_liabilities + r.profit;
  const differens = b.closing_assets - summaSkulder;

  const pagaende = idag <= ar.end;
  const kolumner = ["Ingående", "Förändring", pagaende ? "Nuvarande" : "Utgående"];
  // Mobilens metarad: förändringen bär sitt tecken och behöver ingen etikett.
  const kortRubriker = ["ib", ""];

  const skuldrader = skulder.map(balansrad);
  if (r.profit !== 0) {
    // Efter det sista eget kapital-kontot, före skulderna.
    const index = skulder.findIndex((k) => Number(k.code) >= 2100);
    const rad: VyRadData = {
      id: "arets-resultat",
      titel: "Årets resultat, ej bokfört",
      meta: "resultaträkningen",
      grupp: "Eget kapital",
      hoger: formatBeloppHela(r.profit),
      kolumner: [formatBeloppHela(0), formatForandring(r.profit)],
      mal: { typ: "vy", key: "bocker.resultat" },
    };
    skuldrader.splice(index === -1 ? skuldrader.length : index, 0, rad);
  }

  const vy: VyData = {
    lage: differens === 0 ? "normal" : "fel",
    status: differens === 0 ? "balanserar" : `differens ${formatBeloppHela(differens)}`,
    period: `${arsrubrik(ar)} · ${pagaende ? `saldo per ${idag}` : "utgående balans"}`,
    sektioner: [
      {
        titel: "Tillgångar",
        kolumner,
        kortRubriker,
        rader: [
          ...tillgangar.map(balansrad),
          balanssumma(
            "sum-t",
            "Summa tillgångar",
            summa(tillgangar, "opening_balance"),
            summa(tillgangar, "change"),
            b.closing_assets
          ),
        ],
      },
      {
        titel: "Eget kapital och skulder",
        kolumner,
        kortRubriker,
        rader: [
          ...skuldrader,
          balanssumma(
            "sum-s",
            "Summa eget kapital och skulder",
            summa(skulder, "opening_balance"),
            summa(skulder, "change") + r.profit,
            summaSkulder
          ),
        ],
      },
    ],
    fot: IB_FOT[b.opening_balance_source],
  };

  if (differens !== 0) {
    vy.banner = {
      ton: "fel",
      text: `Tillgångarna och eget kapital och skulder skiljer sig med ${formatBeloppHela(differens)} kr.`,
    };
  }
  return vy;
}

/** Resultaträkningen för räkenskapsåret. Kostnader visas med minustecken. */
export function resultatVy(ar: OverviewFiscalYear, r: Resultatrakning): VyData {
  const sektioner: VySektionData[] = [];

  if (r.revenue_details.length > 0) {
    sektioner.push({
      titel: "Intäkter",
      rader: [
        ...r.revenue_details.map((k) => kontorad(k, k.amount)),
        summarad("sum-i", "Summa intäkter", r.revenue),
      ],
    });
  }
  if (r.cost_details.length > 0) {
    sektioner.push({
      titel: "Kostnader",
      rader: [
        ...r.cost_details.map((k) => kontorad(k, -k.amount)),
        summarad("sum-k", "Summa kostnader", -r.costs),
        summarad("rorelse", "Rörelseresultat", r.operating_profit),
      ],
    });
  }
  if (r.financial_details.length > 0) {
    sektioner.push({
      titel: "Finansiella poster",
      rader: [
        ...r.financial_details.map((k) => kontorad(k, -k.amount)),
        summarad("sum-f", "Summa finansiella poster", -r.financial),
      ],
    });
  }
  if (sektioner.length > 0) {
    sektioner.push({
      titel: "Resultat",
      rader: [summarad("res", "Årets resultat", r.profit)],
    });
  }

  const tomt = sektioner.length === 0;
  return {
    lage: tomt ? "tomt" : "normal",
    status: tomt
      ? "inget bokfört"
      : r.profit >= 0
        ? `vinst ${formatBeloppHela(r.profit)}`
        : `förlust ${formatBeloppHela(-r.profit)}`,
    period: `${arsrubrik(ar)} · ${r.voucher_count} verifikationer`,
    sektioner,
    fot: "Intäkter och kostnader bokförda under räkenskapsåret, klass 3–8.",
  };
}

const nummerAv = (r: { series: string; number: number | null }) =>
  formatVerifikationsnummer(r.number, r.series, "-");

/** `2026-09-18T06:45:12` → `06:45`, skuren ur strängen som servern skrev den (lokal tid, ingen zon). */
function klockslag(iso: string | null | undefined): string | null {
  const m = iso ? /T(\d{2}:\d{2})/.exec(iso) : null;
  return m ? m[1] : null;
}

/** `Nyss postad` (§11.1): `{serie}-{nummer} · postad HH:MM · {vem} · låst`. Bara klientens eget tryck blir `ny`, så `{vem}` är du. */
function nyMeta(nummer: string, postadKl: string | null): string {
  return `${nummer} · postad${postadKl ? ` ${postadKl}` : ""} · du · låst`;
}

/** ` · A-121 korrigering` när en annan verifikation hänvisar till den här verifikationens kvitto (§10.4). */
function korrigering(v: { referenced_by?: VerifikationRef | null }): string {
  return v.referenced_by ? ` · ${nummerAv(v.referenced_by)} korrigering` : "";
}

/**
 * En rättad verifikation och dess rättelse läses som ett par (§7.5): det
 * makulerade stryks över, det ändrade visar beloppet före överstruket och
 * beloppet efter. Ändringen visas bara där, på originalet. Rättelsen säger
 * vad den gjorde med vad, när, av vem och varför, men upprepar varken
 * originalets text eller — när originalet står i samma lista — beloppen
 * (`parBelopp`): då såg man samma ändring två gånger.
 */
function rattelserad(v: Verifikation, r: Rattelse): VyRadData {
  const nummer = nummerAv(v);
  const fore = r.before_total !== r.after_total ? formatBeloppHela(r.before_total) : undefined;
  const rad: VyRadData = { id: v.id, titel: v.description, hoger: "", mal: { typ: "ver", id: v.id } };
  if (v.corrects) {
    const vad = r.kind === "makulering" ? "Makulering" : "Ändring";
    const vem = r.actor ? ` · ${r.actor}` : "";
    const varfor = r.reason ? ` · ${r.reason}` : "";
    return {
      ...rad,
      titel: `${vad} av ${nummerAv(r.original)}`,
      meta: `${nummer} · ${v.date}${vem}${varfor}`,
      rattar: { id: r.original.id, hoger: formatBeloppHela(r.after_total), hogerFore: fore },
    };
  }
  const vad = r.kind === "makulering" ? "makulerad" : "ändrad";
  const meta = `${nummer} · ${v.date} · ${vad} av ${nummerAv(r.correction)} ${r.correction_date}${korrigering(v)}`;
  if (r.kind === "makulering") return { ...rad, meta, hoger: formatBeloppHela(r.before_total), struken: true };
  const andrad: VyRadData = { ...rad, meta, hoger: formatBeloppHela(r.after_total), hogerFore: fore };
  if (harUnderlag(v)) andrad.kvitto = { voucherId: v.id, nummer };
  return andrad;
}

function verifikationsrad(v: Verifikation): VyRadData {
  if (v.status === "posted" && v.correction?.correction_status === "posted") return rattelserad(v, v.correction);
  const nummer = nummerAv(v);
  const saknar = v.status === "posted" && v.missing_attachment === true;
  const rattadAv = v.corrected_by ? ` · rättad av ${nummerAv(v.corrected_by)}` : "";
  const rattar = v.status === "posted" && v.corrects ? ` · rättar ${nummerAv(v.corrects)}` : "";
  const korr = v.status === "posted" ? korrigering(v) : "";
  const utan = v.status === "posted" && v.underlag_waiver ? ` · ${UTAN_UNDERLAG_TEXT[v.underlag_waiver.reason]}` : "";
  const rad: VyRadData = {
    id: v.id,
    titel: v.description,
    meta: `${nummer} · ${v.date}${saknar ? " · saknar underlag" : ""}${utan}${rattadAv}${rattar}${korr}`,
    hoger: formatBeloppHela(v.total_debit),
    variant: v.status === "draft" ? "vantar" : saknar ? "saknar" : undefined,
    mal: { typ: "ver", id: v.id },
  };
  if (harUnderlag(v)) rad.kvitto = { voucherId: v.id, nummer };
  return rad;
}

/**
 * Raden får kvittolänken (FU23) när den är postad och inte saknar underlag.
 * En rättelse får den inte: dess underlag är originalet (D3). Om underlaget
 * är ett kvitto vet klienten först när länken används. En verifikation som
 * godkänts utan underlag har inget att öppna.
 */
export function harUnderlag(
  v: Pick<Verifikation, "status" | "missing_attachment" | "corrects" | "underlag_waiver">
): boolean {
  return v.status === "posted" && v.missing_attachment === false && !v.corrects && !v.underlag_waiver;
}

/**
 * `Saknar underlag` (§10.4): `{serie}-{nummer} · kvitto saknas sedan {n} dgr`,
 * `n` = serverns `age_days`. En verifikation vars underlag är kontoutdrag
 * (en överföring, en skattekontohändelse) säger i stället vilka konton som
 * saknar utdrag: `kontoutdrag 1630 saknas`, eller `1630 och 1930` när inget
 * av dem finns.
 */
function saknarrad(v: Verifikation): VyRadData {
  const konton = v.missing_statement_accounts ?? [];
  const vad = konton.length > 0 ? `kontoutdrag ${konton.join(" och ")}` : "kvitto";
  // En verifikation daterad framåt (en AGI på förfallodagen) saknar ingenting
  // ännu: underlaget kan inte finnas före dagen.
  const framtid = (v.age_days ?? 0) < 0;
  return {
    id: v.id,
    titel: v.description,
    meta: `${nummerAv(v)} · ${underlagAlder(vad, v.age_days)}${andradAv(v)}`,
    hoger: formatBeloppHela(v.total_debit),
    variant: framtid ? undefined : "saknar",
    ageDays: framtid ? undefined : v.age_days,
    mal: { typ: "ver", id: v.id },
    underlagsval: { voucherId: v.id },
  };
}

/** ` · ändrad av B-2` på en rättad verifikation som ännu saknar underlag. */
function andradAv(v: Verifikation): string {
  const r = v.correction;
  return r && v.corrected_by && r.correction_status === "posted" ? ` · ändrad av ${nummerAv(r.correction)}` : "";
}

/**
 * `kvitto saknas sedan 12 dgr`, eller för en verifikation daterad framåt
 * `kontoutdrag 1630 väntas om 7 dgr` — aldrig `sedan -7 dgr`. Utan `vad`
 * bara tiden: `saknas sedan 3 dgr`.
 */
export function underlagAlder(vad: string, ageDays: number | undefined): string {
  const alder = ageDays ?? 0;
  const forst = vad ? `${vad} ` : "";
  return alder < 0 ? `${forst}väntas om ${-alder} dgr` : `${forst}saknas sedan ${alder} dgr`;
}

type KoppladVerifikation = Pick<
  Verifikation,
  "id" | "series" | "number" | "date" | "description" | "total_debit" | "referenced_by"
>;

/** `Nyss kopplad`: `{serie}-{nummer} · kvitto kopplat HH:MM` (+ korrigeringen), läget `ny`. */
function nyssKoppladRad(v: KoppladVerifikation, k: Koppling): VyRadData {
  return {
    id: v.id,
    titel: v.description,
    meta: `${nummerAv(v)} · kvitto kopplat ${k.klockslag}${korrigering(v)}`,
    hoger: formatBeloppHela(v.total_debit),
    variant: "ny",
    kvitto: { voucherId: v.id, nummer: nummerAv(v) },
    mal: { typ: "ver", id: v.id },
  };
}

/** `Kopplad`, efter markeringen: `{serie}-{nummer} · {datum} · kvitto kopplat`. */
function koppladRad(v: Verifikation): VyRadData {
  return {
    ...verifikationsrad({ ...v, status: "posted", missing_attachment: false }),
    meta: `${nummerAv(v)} · ${v.date} · kvitto kopplat${korrigering(v)}`,
  };
}

/** Vyns trådhändelser: öppna beslut, förslag och de optimistiska raderna. */
export interface VantarUnderlag {
  /** `GET /decisions?view_key=bocker.verifikationer&status=all`; bara `open` visas. */
  beslut: readonly BeslutSvar[];
  /** `GET /drafts?view_key=bocker.verifikationer&status=all`. */
  forslag: readonly ForslagStatusSvar[];
  /** §11.2, ur `POSTNINGAR_NYCKEL`. */
  postningar?: readonly Postning[];
  /**
   * `GET /vouchers?missing_attachment=true&sort_by=age`.
   * Utelämnad: ingen sektion, och Postade märker `saknar` som förut.
   */
  saknar?: Verifikationslista;
  /** `Nyss kopplad`, ur `KOPPLINGAR_NYCKEL` (§10.4). */
  kopplingar?: readonly Koppling[];
  /**
   * Det som väntar i andra vyer och blir en verifikation där: lönekort och
   * fakturaförslag (`betalaVantar`). Raderna är färdiga; vyn ställer dem
   * sist i Väntar på beslut och räknar dem.
   */
  andraVyer?: readonly VyRadData[];
  /**
   * Kontoutdragens rader som ingen verifikation står för, i året
   * (`GET /bank-inputs/transactions/open`). Utelämnad: ingen sektion.
   */
  bank?: readonly OppenBanktransaktion[];
  /** Kontoutdragens saldon mot bokföringen, i samma svar som `bank`. */
  avstamning?: readonly Bankavstamning[];
}

export type Ordning = "fallande" | "stigande";

/** Hur Postade (och kontoutdragens rader) ordnas. Standard: datum, senaste först. */
export interface Sortering {
  falt: "datum" | "nummer";
  ordning: Ordning;
}

export const STANDARDSORTERING: Sortering = { falt: "datum", ordning: "fallande" };

export function arStandardsortering(s: Sortering): boolean {
  return s.falt === STANDARDSORTERING.falt && s.ordning === STANDARDSORTERING.ordning;
}

/** En rad i Postade med det den sorteras på. En rad som postas har inget nummer än. */
interface PostadRad {
  rad: VyRadData;
  datum?: string;
  nummer?: { series: string; number: number | null };
}

/**
 * Raderna i `sortering`s ordning. Standardordningen är serverns (och de
 * optimistiska överst), så den lämnas orörd. Annars sorteras stabilt; en
 * rad utan nyckel — en som postas just nu — står först.
 */
function sorteraPostade(rader: readonly PostadRad[], sortering: Sortering): PostadRad[] {
  if (arStandardsortering(sortering)) return [...rader];
  const riktning = sortering.ordning === "stigande" ? 1 : -1;
  const jamfor = (a: PostadRad, b: PostadRad): number => {
    if (sortering.falt === "nummer") {
      const na = a.nummer?.number ?? null;
      const nb = b.nummer?.number ?? null;
      if (na === null || nb === null) return na === nb ? 0 : na === null ? -1 : 1;
      const serie = a.nummer!.series.localeCompare(b.nummer!.series);
      if (serie !== 0) return riktning * serie;
      if (na !== nb) return riktning * (na - nb);
      return riktning * (a.datum ?? "").localeCompare(b.datum ?? "");
    }
    if (!a.datum || !b.datum) return a.datum === b.datum ? 0 : !a.datum ? -1 : 1;
    const datum = a.datum.localeCompare(b.datum);
    if (datum !== 0) return riktning * datum;
    const serie = (a.nummer?.series ?? "").localeCompare(b.nummer?.series ?? "");
    return serie !== 0 ? riktning * serie : riktning * ((a.nummer?.number ?? 0) - (b.nummer?.number ?? 0));
  };
  return [...rader].sort(jamfor);
}

/**
 * Postade, en sektion per månad med månadens lås i rubriken. Utan den står
 * de postade i en enda sektion, `Postade` — som när perioderna inte gick att
 * hämta.
 */
export interface Manader {
  /** Räkenskapsårets perioder, `GET /periods?fiscal_year_id=`. */
  perioder: readonly Period[];
  las: (p: Period) => LasData;
  /** Dagens datum, `YYYY-MM-DD`: en tom månad efter i dag visas inte. */
  idag: string;
  /**
   * Postade har fler sidor på servern. Då visas en tom månad bara om den
   * ligger efter den äldsta hämtade verifikationen — annars vet vyn inte om
   * den är tom.
   */
  harFler: boolean;
}

/**
 * En sektion per period, senaste först (`ordning` stigande: äldsta först). En månad visas när den har rader,
 * eller när den har börjat och vyn vet att den är tom — den kan ju behöva
 * låsas ändå. En rad utan datum i någon period står i dagens månad, annars
 * i den senaste.
 */
function manadssektioner(
  rader: readonly { rad: VyRadData; datum?: string }[],
  aldstaHamtade: string | undefined,
  m: Manader,
  ordning: Ordning = "fallande"
): VySektionData[] {
  const perioder = [...m.perioder].sort((a, b) => b.start_date.localeCompare(a.start_date));
  const iPeriod = (datum: string | undefined) =>
    datum ? perioder.find((p) => p.start_date <= datum && datum <= p.end_date) : undefined;
  const reserv = iPeriod(m.idag) ?? perioder[0];

  const perPeriod = new Map<string, VyRadData[]>(perioder.map((p) => [p.id, []]));
  for (const { rad, datum } of rader) {
    perPeriod.get((iPeriod(datum) ?? reserv).id)!.push(rad);
  }

  const visade = ordning === "stigande" ? [...perioder].reverse() : perioder;
  return visade.flatMap((p) => {
    const periodRader = perPeriod.get(p.id)!;
    const kand = p.start_date <= m.idag && (!m.harFler || (aldstaHamtade !== undefined && p.end_date >= aldstaHamtade));
    if (periodRader.length === 0 && !kand) return [];
    const namn = periodnamn(p);
    return [
      {
        titel: namn.charAt(0).toUpperCase() + namn.slice(1),
        rader: periodRader,
        las: m.las(p),
        tom: "inga postade verifikationer",
      },
    ];
  });
}

export const BANK_TITEL = "Kontoutdrag mot bokföringen";

const VY_VERIFIKATIONER = "bocker.verifikationer";

function bankrad(t: OppenBanktransaktion): VyRadData {
  const text = t.description?.trim() || "Banktransaktion";
  const belopp = formatBelopp(t.amount_ore);
  const kandidat = t.candidates[0];
  return {
    id: `bank:${t.bank_transaction_id}`,
    titel: text,
    meta: `${t.date} · konto ${t.account_code} · ${kandidat ? "ej kopplad" : "ingen verifikation"}`,
    hoger: belopp,
    variant: "saknar",
    lankar: kandidat
      ? t.candidates.map((c) => ({ text: `kanske ${c.voucher_number}`, mal: { typ: "ver" as const, id: c.voucher_id } }))
      : undefined,
    fraga: {
      viewKey: VY_VERIFIKATIONER,
      text: kandidat
        ? `Bankhändelsen ${t.date} "${text}" ${belopp} kr på ${t.account_code} har ingen koppling. Är det ${kandidat.voucher_number}? `
        : `Bankhändelsen ${t.date} "${text}" ${belopp} kr på ${t.account_code} saknar verifikation. `,
    },
  };
}

function avstamningsrad(a: Bankavstamning): VyRadData {
  const stammer = a.difference_ore === 0;
  return {
    id: `avstamning:${a.account_code}`,
    titel: `Saldo ${a.account_code} enligt kontoutdraget`,
    meta: stammer
      ? `${a.date} · stämmer med bokföringen`
      : `${a.date} · bokfört ${formatBelopp(a.ledger_balance_ore)} · differens ${formatBelopp(a.difference_ore)}`,
    hoger: formatBelopp(a.statement_balance_ore),
    variant: stammer ? undefined : "saknar",
    mal: { typ: "konto", kod: a.account_code },
  };
}

/**
 * Kontoutdragen mot bokföringen: först varje kontos saldo enligt det
 * senaste utdraget, sedan alla raderna utan verifikation i datumordning —
 * senaste först om inte `ordning` säger stigande.
 */
export function banksektion(
  bank: readonly OppenBanktransaktion[] | undefined,
  avstamning: readonly Bankavstamning[] = [],
  ordning: Ordning = "fallande"
): VySektionData | null {
  if ((!bank || bank.length === 0) && avstamning.length === 0) return null;
  const riktning = ordning === "stigande" ? 1 : -1;
  const sorterade = [...(bank ?? [])].sort((a, b) => riktning * a.date.localeCompare(b.date));
  return { titel: BANK_TITEL, rader: [...avstamning.map(avstamningsrad), ...sorterade.map(bankrad)] };
}

/** Vyns fot, panelens ord. */
export const FOT_UNDERLAG =
  "Underlag kan släppas i chatten när som helst. Agenten kopplar det till rätt verifikation och säger till om något inte stämmer.";

const INGET_UNDERLAG: VantarUnderlag = { beslut: [], forslag: [] };

/**
 * Det beslut ett väntande förslag svarar på, som vyn och `count_waiting`
 * (§11.3) grupperar på: `decision_id`, annars noteringens syntetiska
 * `correction:{id}`, annars förslaget självt.
 */
function vantarPa(f: ForslagStatusSvar): string {
  if (f.decision_id) return f.decision_id;
  if (f.correction_note_id) return `correction:${f.correction_note_id}`;
  return `draft:${f.draft_id}`;
}

function beslutsrad(b: BeslutSvar): VyRadData {
  const datum = b.source?.date;
  if (b.kind === "intake" && b.source) {
    return {
      id: b.id,
      titel: b.title,
      meta: datum ? `agenten avstod · ${datum}` : "agenten avstod",
      hoger: "",
      variant: "vantar",
      ageDays: b.age_days,
      forsokIgen: { sourceId: b.source.id },
      beslut: b,
    };
  }
  return {
    id: b.id,
    titel: b.title,
    meta: datum ? `väntar på dig · ${datum}` : "väntar på dig",
    hoger: b.amount_ore === null ? "" : formatBeloppHela(b.amount_ore),
    variant: "vantar",
    ageDays: b.age_days,
    beslut: b,
  };
}

function forslagsrad(f: ForslagStatusSvar, u: Verifikation): VyRadData {
  // `svara`: chatten skrollar till förslagskortet och fältet får en
  // inledning som säger vilket förslag svaret gäller. Inget skickas.
  const rad = {
    id: f.draft_id,
    titel: u.description,
    hoger: formatBeloppHela(u.total_debit),
    fraga: {
      viewKey: VY_VERIFIKATIONER,
      text: `Om förslaget "${u.description}" ${u.date}: `,
      etikett: "svara",
      postId: f.post_id,
    },
  };
  if (f.last_error_code) {
    // `period_locked` kan sättas av låsningen själv (F16) utan att någon
    // tryckt `Posta` — då har ingen postning misslyckats.
    const orsak =
      f.last_error_code === "period_locked" ? "perioden låst" : "postning misslyckades";
    return { ...rad, meta: `${orsak} · ligger kvar`, variant: "fel" };
  }
  if (f.correction_of) {
    const av = u.corrects ? ` av ${nummerAv(u.corrects)}` : "";
    return { ...rad, meta: `rättelse${av} väntar`, variant: "vantar" };
  }
  return { ...rad, meta: `förslag väntar · ${u.date}`, variant: "vantar" };
}

/** Den optimistiska raden (§11.2) när serverns lista inte har verifikationen än. */
function postningsrad(p: Postning): VyRadData {
  const titel = p.utkast?.titel ?? (p.lage === "postad" ? p.verifikation?.description : undefined) ?? "";
  const belopp = p.utkast?.belopp ?? (p.lage === "postad" ? p.verifikation?.total_debit : undefined);
  const hoger = belopp === undefined ? "" : formatBeloppHela(belopp);
  if (p.lage === "pagaende") {
    // Inget nummer: det finns inte än (§11.2).
    return { id: p.draftId, titel, meta: `${p.utkast?.serie ?? ""} · postas…`, hoger, variant: "pagaende" };
  }
  const v = p.verifikation;
  const nummer = v ? nummerAv(v) : (p.utkast?.serie ?? "");
  // Postningen byter bara utkastets status: verifikationen har utkastets id.
  return {
    id: p.draftId,
    titel,
    meta: nyMeta(nummer, klockslag(v?.posted_at)),
    hoger,
    variant: "ny",
    mal: { typ: "ver", id: v?.id ?? p.draftId },
  };
}

/**
 * Fyra sektioner (flode-verifikationer §11.1, flode-underlag §10.4):
 * **Väntar på beslut** (öppna beslut och väntande trådförslag), **Saknar
 * underlag** (postade utan underlag, äldst först), **Utkast** (utkast som
 * inte är trådens) och **Postade** (senast först, med de optimistiska
 * raderna och `Nyss kopplad` överst, §11.2). Det som är ogjort står överst. En verifikation visas på ett
 * enda ställe; en tom sektion visas inte.
 *
 * Ett väntande förslag som svarar på ett öppet beslut står i beslutets
 * ställe. Statusens tal räknas som `count_waiting` (§11.3): en gång per
 * beslut, per notering och per fristående förslag — två förslag på samma
 * besvarade beslut är två rader men en sak som väntar.
 */
export function verifikationerVy(
  ar: OverviewFiscalYear,
  postade: Verifikationslista,
  utkast: Verifikationslista,
  underlag: VantarUnderlag = INGET_UNDERLAG,
  manader?: Manader,
  sortering: Sortering = STANDARDSORTERING
): VyData {
  const postningar = underlag.postningar ?? [];
  const postas = new Set(postningar.map((p) => p.draftId));
  const tradens = new Set(underlag.forslag.map((f) => f.draft_id));
  const utkastPerId = new Map(utkast.vouchers.map((u) => [u.id, u]));

  // Väntar på beslut.
  const oppna = underlag.beslut.filter((b) => b.status === "open");
  const oppnaIds = new Set(oppna.map((b) => b.id));
  // Bara förslag vars utkast hör till året (utkastlistan är årets), eller
  // som postas just nu: ett förslag från ett annat år varken visas, räknas
  // eller står i stället för ett av årets beslut.
  const vantande = underlag.forslag.filter(
    (f) => f.status === "pending" && (utkastPerId.has(f.draft_id) || postas.has(f.draft_id))
  );
  // Beslut som ett förslag står i stället för — också medan förslaget postas,
  // annars dyker beslutet upp i Väntar under postningen.
  const ersatta = new Set(vantande.map(vantarPa).filter((k) => oppnaIds.has(k)));
  const synligaForslag = vantande.filter((f) => !postas.has(f.draft_id));
  // Det som väntar i andra vyer och blir verifikationer där (lön, faktura):
  // sist, märkt med varifrån det kommer. En sak var, som de egna besluten.
  const andraVyer = underlag.andraVyer ?? [];
  const vantarRader: VyRadData[] = [
    ...oppna.filter((b) => !ersatta.has(b.id)).map(beslutsrad),
    ...synligaForslag.map((f) => forslagsrad(f, utkastPerId.get(f.draft_id)!)),
    ...andraVyer,
  ];
  const antalVantar =
    new Set([...oppna.filter((b) => !ersatta.has(b.id)).map((b) => b.id), ...synligaForslag.map(vantarPa)]).size +
    andraVyer.length;

  // Saknar underlag: utan dem som nyss kopplats (listan kan vara gammal
  // tills omhämtningen svarat) och utan dem som postas.
  const kopplingar = underlag.kopplingar ?? [];
  const kopplade = new Map(kopplingar.map((k) => [k.voucherId, k]));
  const saknarLista = underlag.saknar?.vouchers ?? [];
  const saknarPerId = new Map(saknarLista.map((v) => [v.id, v]));
  const saknarRader = saknarLista
    .filter((v) => !kopplade.has(v.id) && !postas.has(v.id))
    .map(saknarrad);
  const iSaknar = new Set(saknarRader.map((r) => r.id));

  // Postade: de optimistiska överst, sedan de nyss kopplade, sedan serverns lista.
  const postadePerId = new Map(postade.vouchers.map((v) => [v.id, v]));
  const nyss = new Set(postningar.filter((p) => p.lage === "postad").map((p) => p.draftId));
  const optimistiska = postningar.map((p): PostadRad => {
    const v = postadePerId.get(p.draftId);
    if (p.lage === "postad" && v) {
      return {
        rad: { ...verifikationsrad(v), variant: "ny", meta: nyMeta(nummerAv(v), klockslag(v.posted_at)) },
        datum: v.date,
        nummer: v,
      };
    }
    const postad = p.lage === "postad" ? p.verifikation : undefined;
    const datum = postad?.date ?? utkastPerId.get(p.draftId)?.date;
    return { rad: postningsrad(p), datum, nummer: postad ?? undefined };
  });
  const nyssKopplade = kopplingar.filter((k) => k.ny && !postas.has(k.voucherId));
  const nyssKoppladeIds = new Set(nyssKopplade.map((k) => k.voucherId));
  const koppladeRader = nyssKopplade.flatMap((k) => {
    const v = postadePerId.get(k.voucherId) ?? saknarPerId.get(k.voucherId) ?? k.verifikation;
    return v ? [{ rad: nyssKoppladRad(v, k), datum: v.date, nummer: v }] : [];
  });
  const postadeMedDatum = sorteraPostade([
    ...optimistiska,
    ...koppladeRader,
    ...postade.vouchers
      .filter((v) => !postas.has(v.id) && !nyss.has(v.id) && !nyssKoppladeIds.has(v.id) && !iSaknar.has(v.id))
      .map((v) => ({ rad: kopplade.has(v.id) ? koppladRad(v) : verifikationsrad(v), datum: v.date, nummer: v })),
  ], sortering);
  const postadeRader = postadeMedDatum.map((r) => r.rad);

  // Utkast: bara de som inte är trådens (och inte postas just nu).
  const egnaUtkast = utkast.vouchers.filter((u) => !tradens.has(u.id) && !postas.has(u.id));

  const sektioner: VySektionData[] = [];
  if (vantarRader.length > 0) sektioner.push({ titel: "Väntar på beslut", rader: vantarRader });
  if (saknarRader.length > 0) sektioner.push({ titel: "Saknar underlag", rader: saknarRader });
  // Utkast är ogjort arbete, som det ovan: överst, inte under alla månader.
  if (egnaUtkast.length > 0) {
    sektioner.push({ titel: "Utkast", rader: egnaUtkast.map(verifikationsrad) });
  }
  const bank = banksektion(underlag.bank, underlag.avstamning, sortering.ordning);
  if (bank) sektioner.push(bank);
  if (manader && manader.perioder.length > 0) {
    const aldsta = postade.vouchers.reduce<string | undefined>(
      (min, v) => (min === undefined || v.date < min ? v.date : min),
      undefined
    );
    sektioner.push(...manadssektioner(postadeMedDatum, aldsta, manader, sortering.ordning));
  } else if (postadeRader.length > 0) {
    sektioner.push({ titel: "Postade", rader: postadeRader });
  }

  // Tomma månader räknas inte: de står där för låsets skull.
  const tomt = sektioner.every((s) => s.rader.length === 0);
  // Serverns tal, inte raderna: `total` räknar också dem utanför sidan.
  // Nyss kopplade dras inte av — omhämtningen ger rätt tal strax.
  const antalSaknar = saknarRader.length > 0 ? (underlag.saknar?.total ?? 0) : 0;
  const antalBank = underlag.bank?.length ?? 0;
  return {
    lage: tomt
      ? "tomt"
      : antalVantar > 0 || antalSaknar > 0 || antalBank > 0 || egnaUtkast.length > 0
        ? "vantar"
        : "normal",
    status: tomt
      ? "inga verifikationer"
      : antalVantar > 0
        ? `${antalVantar} väntar på dig`
        : antalSaknar > 0
          ? `${antalSaknar} saknar underlag`
          : antalBank > 0
            ? `${antalBank} i banken utan verifikation`
            : egnaUtkast.length > 0
              ? `${egnaUtkast.length} utkast`
              : `${postade.total} postade`,
    // Panelen: "Kompletteringar först · postade nedan".
    period:
      saknarRader.length > 0
        ? `${arsrubrik(ar)} · kompletteringar först · postade nedan`
        : `${arsrubrik(ar)} · ${postade.total} postade verifikationer`,
    sektioner: parBelopp(sektioner),
    fot: FOT_UNDERLAG,
  };
}
