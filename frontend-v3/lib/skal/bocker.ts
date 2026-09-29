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
import { formatBeloppHela } from "@/lib/skal/format";
import { formatVerifikationsnummer } from "@/lib/utils";
import type { VyData, VyRadData, VySektionData } from "@/lib/skal/vydata";
import type { OverviewFiscalYear } from "@/lib/skal/api";
import { oppnaUnderlag, type BeslutSvar, type ForslagStatusSvar } from "@/lib/chattyta/api";
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
  posted_at?: string | null;
  /** Den postade rättelsen av den här (flode-verifikationer §7.5). */
  corrected_by?: VerifikationRef | null;
  /** Verifikationen den här rättar. */
  corrects?: VerifikationRef | null;
  /**
   * Den postade verifikation som hänvisar till den här verifikationens
   * kvitto (SPEC-flode-underlag.md §5, D2): A-121 för A-118. Valfri: en
   * server från före FU16 skickar den inte.
   */
  referenced_by?: VerifikationRef | null;
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
  return oppnaUnderlag(async () => kvittoKalla(await bockerApi.getKallkontext(voucherId)));
}

/** Postade hämtas så många i taget; nästa sida när listans slut syns (SPEC-lasbarhet.md §4.5). */
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

export const bockerApi = {
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
   * `missingAttachment` (SPEC-flode-underlag.md §10.4): `false` ger Postade
   * utan dem som saknar underlag, så att en verifikation står på ett ställe.
   * Utelämnad skickas den inte. `offset` sidar Postade (SPEC-lasbarhet.md §4.5).
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

export function kontorad(k: { code: string; name: string }, belopp: number): VyRadData {
  return { id: k.code, titel: k.name, meta: k.code, hoger: formatBeloppHela(belopp) };
}

export function summarad(id: string, titel: string, belopp: number): VyRadData {
  return { id, titel, hoger: formatBeloppHela(belopp), summa: true };
}

function sorterade(...listor: BalansKonto[][]): BalansKonto[] {
  return listor
    .flat()
    .filter((k) => k.closing_balance !== 0)
    .sort((a, b) => a.code.localeCompare(b.code));
}

/** Varifrån årets ingående balans kommer — IB är ingen verifikation. */
const IB_FOT: Record<Balansrakning["opening_balance_source"], string> = {
  derived: "Ingående balanser framräknade ur föregående räkenskapsårs utgående balans.",
  stated: "Ingående balanser angivna för första räkenskapsåret i böckerna.",
  none: "Räkenskapsåret saknar ingående balans.",
};

/**
 * Balansräkningen per räkenskapsårets utgång, med årets resultat.
 *
 * Serverns summa för eget kapital och skulder omfattar bara klass 2. Förrän
 * årets resultat är bokat mot 2099 ligger det i resultatkontona, så det
 * läggs till som en egen rad ur resultaträkningen. Då ska summorna mötas;
 * gör de inte det är vyn i felläge.
 */
export function balansVy(
  ar: OverviewFiscalYear,
  b: Balansrakning,
  r: Resultatrakning
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

  const skuldrader = skulder.map((k) => kontorad(k, k.closing_balance));
  if (r.profit !== 0) {
    // Efter det sista eget kapital-kontot, före skulderna.
    const index = skulder.findIndex((k) => Number(k.code) >= 2100);
    const rad: VyRadData = {
      id: "arets-resultat",
      titel: "Årets resultat, ej bokfört",
      meta: "resultaträkningen",
      hoger: formatBeloppHela(r.profit),
    };
    skuldrader.splice(index === -1 ? skuldrader.length : index, 0, rad);
  }

  const vy: VyData = {
    lage: differens === 0 ? "normal" : "fel",
    status: differens === 0 ? "balanserar" : `differens ${formatBeloppHela(differens)}`,
    period: `${arsrubrik(ar)} · utgående balans`,
    sektioner: [
      {
        titel: "Tillgångar",
        rader: [
          ...tillgangar.map((k) => kontorad(k, k.closing_balance)),
          summarad("sum-t", "Summa tillgångar", b.closing_assets),
        ],
      },
      {
        titel: "Eget kapital och skulder",
        rader: [...skuldrader, summarad("sum-s", "Summa eget kapital och skulder", summaSkulder)],
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

function verifikationsrad(v: Verifikation): VyRadData {
  const nummer = nummerAv(v);
  const saknar = v.status === "posted" && v.missing_attachment === true;
  const rattadAv = v.corrected_by ? ` · rättad av ${nummerAv(v.corrected_by)}` : "";
  const rattar = v.status === "posted" && v.corrects ? ` · rättar ${nummerAv(v.corrects)}` : "";
  const korr = v.status === "posted" ? korrigering(v) : "";
  const rad: VyRadData = {
    id: v.id,
    titel: v.description,
    meta: `${nummer} · ${v.date}${saknar ? " · saknar underlag" : ""}${rattadAv}${rattar}${korr}`,
    hoger: formatBeloppHela(v.total_debit),
    variant: v.status === "draft" ? "vantar" : saknar ? "saknar" : undefined,
  };
  if (harUnderlag(v)) rad.kvitto = { voucherId: v.id, nummer };
  return rad;
}

/**
 * Raden får kvittolänken (FU23) när den är postad och inte saknar underlag.
 * En rättelse får den inte: dess underlag är originalet (D3). Om underlaget
 * är ett kvitto vet klienten först när länken används.
 */
function harUnderlag(v: Pick<Verifikation, "status" | "missing_attachment" | "corrects">): boolean {
  return v.status === "posted" && v.missing_attachment === false && !v.corrects;
}

/** `Saknar underlag` (§10.4): `{serie}-{nummer} · kvitto saknas sedan {n} dgr`, `n` = serverns `age_days`. */
function saknarrad(v: Verifikation): VyRadData {
  const alder = v.age_days ?? 0;
  return {
    id: v.id,
    titel: v.description,
    meta: `${nummerAv(v)} · kvitto saknas sedan ${alder} dgr`,
    hoger: formatBeloppHela(v.total_debit),
    variant: "saknar",
    ageDays: v.age_days,
  };
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
   * `GET /vouchers?missing_attachment=true&sort_by=age` (SPEC-flode-underlag.md
   * §10.4). Utelämnad: ingen sektion, och Postade märker `saknar` som förut.
   */
  saknar?: Verifikationslista;
  /** `Nyss kopplad`, ur `KOPPLINGAR_NYCKEL` (§10.4). */
  kopplingar?: readonly Koppling[];
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
 * En sektion per period, senaste först. En månad visas när den har rader,
 * eller när den har börjat och vyn vet att den är tom — den kan ju behöva
 * låsas ändå. En rad utan datum i någon period står i dagens månad, annars
 * i den senaste.
 */
function manadssektioner(
  rader: readonly { rad: VyRadData; datum?: string }[],
  aldstaHamtade: string | undefined,
  m: Manader
): VySektionData[] {
  const perioder = [...m.perioder].sort((a, b) => b.start_date.localeCompare(a.start_date));
  const iPeriod = (datum: string | undefined) =>
    datum ? perioder.find((p) => p.start_date <= datum && datum <= p.end_date) : undefined;
  const reserv = iPeriod(m.idag) ?? perioder[0];

  const perPeriod = new Map<string, VyRadData[]>(perioder.map((p) => [p.id, []]));
  for (const { rad, datum } of rader) {
    perPeriod.get((iPeriod(datum) ?? reserv).id)!.push(rad);
  }

  return perioder.flatMap((p) => {
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

/** Vyns fot, panelens ord (SPEC-flode-underlag.md §10.4). */
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
  return {
    id: b.id,
    titel: b.title,
    meta: datum ? `väntar på dig · ${datum}` : "väntar på dig",
    hoger: b.amount_ore === null ? "" : formatBeloppHela(b.amount_ore),
    variant: "vantar",
    ageDays: b.age_days,
  };
}

function forslagsrad(f: ForslagStatusSvar, u: Verifikation): VyRadData {
  const rad = { id: f.draft_id, titel: u.description, hoger: formatBeloppHela(u.total_debit) };
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
  return { id: p.draftId, titel, meta: nyMeta(nummer, klockslag(v?.posted_at)), hoger, variant: "ny" };
}

/**
 * Fyra sektioner (flode-verifikationer §11.1, flode-underlag §10.4):
 * **Väntar på beslut** (öppna beslut och väntande trådförslag), **Saknar
 * underlag** (postade utan underlag, äldst först), **Postade** (senast
 * först, med de optimistiska raderna och `Nyss kopplad` överst, §11.2) och
 * **Utkast** (utkast som inte är trådens). En verifikation visas på ett
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
  manader?: Manader
): VyData {
  const postningar = underlag.postningar ?? [];
  const postas = new Set(postningar.map((p) => p.draftId));
  const tradens = new Set(underlag.forslag.map((f) => f.draft_id));
  const utkastPerId = new Map(utkast.vouchers.map((u) => [u.id, u]));

  // Väntar på beslut.
  const oppna = underlag.beslut.filter((b) => b.status === "open");
  const oppnaIds = new Set(oppna.map((b) => b.id));
  const vantande = underlag.forslag.filter((f) => f.status === "pending");
  // Beslut som ett förslag står i stället för — också medan förslaget postas,
  // annars dyker beslutet upp i Väntar under postningen.
  const ersatta = new Set(vantande.map(vantarPa).filter((k) => oppnaIds.has(k)));
  const synligaForslag = vantande.filter((f) => !postas.has(f.draft_id));
  const vantarRader: VyRadData[] = [
    ...oppna.filter((b) => !ersatta.has(b.id)).map(beslutsrad),
    ...synligaForslag.flatMap((f) => {
      const u = utkastPerId.get(f.draft_id);
      return u ? [forslagsrad(f, u)] : [];
    }),
  ];
  const antalVantar = new Set([
    ...oppna.filter((b) => !ersatta.has(b.id)).map((b) => b.id),
    ...synligaForslag.map(vantarPa),
  ]).size;

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
  const optimistiska = postningar.map((p): { rad: VyRadData; datum?: string } => {
    const v = postadePerId.get(p.draftId);
    if (p.lage === "postad" && v) {
      return {
        rad: { ...verifikationsrad(v), variant: "ny", meta: nyMeta(nummerAv(v), klockslag(v.posted_at)) },
        datum: v.date,
      };
    }
    const datum = (p.lage === "postad" ? p.verifikation?.date : undefined) ?? utkastPerId.get(p.draftId)?.date;
    return { rad: postningsrad(p), datum };
  });
  const nyssKopplade = kopplingar.filter((k) => k.ny && !postas.has(k.voucherId));
  const nyssKoppladeIds = new Set(nyssKopplade.map((k) => k.voucherId));
  const koppladeRader = nyssKopplade.flatMap((k) => {
    const v = postadePerId.get(k.voucherId) ?? saknarPerId.get(k.voucherId) ?? k.verifikation;
    return v ? [{ rad: nyssKoppladRad(v, k), datum: v.date }] : [];
  });
  const postadeMedDatum = [
    ...optimistiska,
    ...koppladeRader,
    ...postade.vouchers
      .filter((v) => !postas.has(v.id) && !nyss.has(v.id) && !nyssKoppladeIds.has(v.id) && !iSaknar.has(v.id))
      .map((v) => ({ rad: kopplade.has(v.id) ? koppladRad(v) : verifikationsrad(v), datum: v.date })),
  ];
  const postadeRader = postadeMedDatum.map((r) => r.rad);

  // Utkast: bara de som inte är trådens (och inte postas just nu).
  const egnaUtkast = utkast.vouchers.filter((u) => !tradens.has(u.id) && !postas.has(u.id));

  const sektioner: VySektionData[] = [];
  if (vantarRader.length > 0) sektioner.push({ titel: "Väntar på beslut", rader: vantarRader });
  if (saknarRader.length > 0) sektioner.push({ titel: "Saknar underlag", rader: saknarRader });
  if (manader && manader.perioder.length > 0) {
    const aldsta = postade.vouchers.reduce<string | undefined>(
      (min, v) => (min === undefined || v.date < min ? v.date : min),
      undefined
    );
    sektioner.push(...manadssektioner(postadeMedDatum, aldsta, manader));
  } else if (postadeRader.length > 0) {
    sektioner.push({ titel: "Postade", rader: postadeRader });
  }
  if (egnaUtkast.length > 0) {
    sektioner.push({ titel: "Utkast", rader: egnaUtkast.map(verifikationsrad) });
  }

  // Tomma månader räknas inte: de står där för låsets skull.
  const tomt = sektioner.every((s) => s.rader.length === 0);
  // Serverns tal, inte raderna: `total` räknar också dem utanför sidan.
  // Nyss kopplade dras inte av — omhämtningen ger rätt tal strax.
  const antalSaknar = saknarRader.length > 0 ? (underlag.saknar?.total ?? 0) : 0;
  return {
    lage: tomt ? "tomt" : antalVantar > 0 || antalSaknar > 0 || egnaUtkast.length > 0 ? "vantar" : "normal",
    status: tomt
      ? "inga verifikationer"
      : antalVantar > 0
        ? `${antalVantar} väntar på dig`
        : antalSaknar > 0
          ? `${antalSaknar} saknar underlag`
          : egnaUtkast.length > 0
            ? `${egnaUtkast.length} utkast`
            : `${postade.total} postade`,
    // Panelen: "Kompletteringar först · postade nedan".
    period:
      saknarRader.length > 0
        ? `${arsrubrik(ar)} · kompletteringar först · postade nedan`
        : `${arsrubrik(ar)} · ${postade.total} postade verifikationer`,
    sektioner,
    fot: FOT_UNDERLAG,
  };
}
