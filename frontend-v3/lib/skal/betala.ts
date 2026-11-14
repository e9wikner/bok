/**
 * Fakturering och Löner ur riktiga data (modul `skal`).
 *
 * Fakturering är en skrivvy sedan fakturering F1:
 * agenten lägger fram fakturan i tråden och människan utfärdar den i
 * kortet. Löner skriver på samma sätt: agenten lägger fram bokföringen av ett
 * lönebesked som ett beslutskort (`foresla_lonebokforing`), och människan
 * bokför med ett tryck i kortet. En AGI bokför agenten själv när kvittensen
 * kommer in (`bokfor_agi`). Vyn själv har ingen knapp.
 */

import apiClient from "@/lib/api";
import type { BeslutSvar, ForslagStatusSvar } from "@/lib/chattyta/api";
import type { Utfardande } from "@/lib/chattyta/utfardanden";
import { formatBeloppHela } from "@/lib/skal/format";
import type { VyData, VyRadData, VySektionData } from "@/lib/skal/vydata";

// ─── API-svaren ───────────────────────────────────────────────────────────

export interface Faktura {
  id: string;
  invoice_number: string | number | null;
  customer_name: string | null;
  invoice_date: string;
  due_date: string;
  amount_inc_vat: number;
  remaining_amount: number;
  /** Valfri i äldre testdata; summeringen räknar moms bara när den finns. */
  vat_amount?: number;
  status: string;
  is_overdue: boolean;
  /** Verifikationen som bokförde fakturan. Valfri: en äldre server skickar den inte. */
  voucher_id?: string | null;
  /** Betalningarnas verifikationer, nyast först. */
  payment_voucher_ids?: string[];
}

/**
 * En utgående faktura som bokförts utanför BokAI: bara en verifikation
 * (debet kundfordringar, kredit intäkt), ingen faktura här
 * (`services/ledger_bookings.py`). Betald när en senare verifikation minskar
 * kundfordringarna med exakt beloppet.
 */
export interface HuvudboksFaktura {
  voucher_id: string;
  voucher_number: string | null;
  date: string;
  description: string;
  amount_inc_vat: number;
  vat_amount: number;
  paid: boolean;
  payment_voucher_id: string | null;
  payment_date: string | null;
}

export interface Fakturalista {
  total: number;
  invoices: Faktura[];
  /** Valfri: en äldre server skickar den inte. */
  ledger_invoices?: HuvudboksFaktura[];
}

/** En rad ur `GET /invoice-drafts` (`api/routes/invoice_drafts.py`). */
export interface Fakturautkast {
  id: string;
  invoice_number: string | null;
  customer_name: string;
  invoice_date: string;
  due_date: string;
  status: string;
  amount_inc_vat: number;
}

export interface Fakturautkastlista {
  drafts: Fakturautkast[];
}

/** Ett lönebesked i `GET /payroll/runs` (`_payslip_to_dict`). */
export interface Lonebesked {
  id: string;
  employee_name: string | null;
  payment_date: string;
  gross_salary: number;
  net_salary: number;
  status: string;
  voucher_id: string | null;
  /** Det öppna kortet som bokför lönebeskedet. Valfritt: en äldre server skickar det inte. */
  pending_decision_id?: string | null;
  /** Lönebeskedets PDF är underlag till verifikationen (migration 050). */
  underlag_linked?: boolean;
  /** PDF:en sparades när lönebeskedet skapades (migration 050). */
  pdf_stored?: boolean;
  /** När lönebeskedet markerades som skickat. */
  pdf_sent_at?: string | null;
  /** Verifikationen lönebeskedet ännu kan kopplas till som underlag. */
  attach_voucher?: { id: string; number: string } | null;
  /** Utbetalningen som lönen kan bokföras mot med ett tryck; saknas när den inte är entydig. */
  payment_transaction_id?: string | null;
}

/** Månadens AGI, för månaden lönen betalades ut (`_agi_summary`). */
export interface LoneAgi {
  year: number;
  month: number;
  due_date: string;
  total_to_pay: number;
  unbooked_payslips: number;
  /** Delarnas verifikationer: `tax` och `employer_fee`. */
  voucher_ids: Record<string, string>;
  booked: boolean;
}

export interface Lonekorning {
  id: string;
  year: number;
  month: number;
  payment_date: string | null;
  status: string;
  payslip_count: number;
  total_gross_salary: number;
  total_net_salary: number;
  /** Valfria: en server från före `/v4`-lönerna skickar dem inte. */
  payslips?: Lonebesked[];
  agi?: LoneAgi | null;
}

/** En lön som bokförts utanför BokAI: bara en verifikation, inget lönebesked. */
export interface HuvudboksLon {
  voucher_id: string;
  voucher_number: string | null;
  date: string;
  description: string;
  /** Debet på lönekontona; inte bruttolönen när semesterlön tas ur skulden. */
  gross_salary: number;
  preliminary_tax: number;
  /** Krediterat bankkonto, annars skuld till den anställde; null utan någotdera. */
  net_salary: number | null;
}

/**
 * Årets löner, skatt och sociala avgifter ur huvudboken, i öre
 * (`LedgerBookingService.payroll_summary`). Avdraget och påfört ur lönerna,
 * betalt ur AGI:erna — decembers AGI betalas i januari, och räknas dit.
 */
export interface LoneSummering {
  gross_salary: number;
  tax_withheld: number;
  tax_paid: number;
  employer_fee_charged: number;
  employer_fee_paid: number;
}

export interface Lonekorningar {
  payroll_runs: Lonekorning[];
  /** Valfri: en äldre server skickar den inte. */
  ledger_payouts?: HuvudboksLon[];
  /** Bara med ett räkenskapsår; en äldre server skickar den inte. */
  summary?: LoneSummering | null;
}

/** Rubriken för det som bokförts utanför BokAI, i båda vyerna. */
export const UTANFOR_RUBRIK = "Bokförda utanför BokAI";

/** Rubriken för årets summor, i båda vyerna. */
export const SUMMERING_RUBRIK = "Summering";

/**
 * Fakturorna och lönekörningarna gäller årsväljarens år (`fiscal_year_id`):
 * en faktura hör till året för sitt fakturadatum, en lönekörning till året
 * för sin utbetalning — samma år som deras verifikationer.
 */
export const betalaApi = {
  getFakturor: async (arId: string): Promise<Fakturalista> => {
    const { data } = await apiClient.get<Fakturalista>("/api/v1/invoices", {
      params: { fiscal_year_id: arId },
    });
    return data;
  },

  getFakturautkast: async (): Promise<Fakturautkastlista> => {
    const { data } = await apiClient.get<Fakturautkastlista>("/api/v1/invoice-drafts");
    return data;
  },

  getLonekorningar: async (arId: string): Promise<Lonekorningar> => {
    const { data } = await apiClient.get<Lonekorningar>("/api/v1/payroll/runs", {
      params: { fiscal_year_id: arId },
    });
    return data;
  },
};

/** Räkenskapsåret vyn visar, som `OverviewFiscalYear`. */
export interface BetalaAr {
  start: string;
  end: string;
}

/** Ligger datumet i året? Utan år eller datum: ja, raden står kvar hellre än försvinner. */
function iAret(ar: BetalaAr | undefined, datum: string | undefined): boolean {
  return !ar || !datum || (ar.start <= datum && datum <= ar.end);
}

// ─── Fakturering ──────────────────────────────────────────────────────────

/** Så många betalda fakturor visas. */
export const BETALDA_ANTAL = 10;

const OBETALD = new Set(["sent", "partially_paid", "overdue"]);

function fakturarad(f: Faktura): VyRadData {
  const nummer = f.invoice_number ?? "utan nummer";
  const forfallen = f.status !== "paid" && f.is_overdue;
  let meta: string;
  if (f.status === "draft") meta = `${nummer} · utkast`;
  else if (f.status === "paid") meta = `${nummer} · betald`;
  else if (forfallen) meta = `${nummer} · förföll ${f.due_date}`;
  else meta = `${nummer} · förfaller ${f.due_date}`;
  return {
    id: f.id,
    titel: f.customer_name ?? "Okänd kund",
    meta,
    hoger: formatBeloppHela(f.status === "paid" ? f.amount_inc_vat : f.remaining_amount),
    variant: forfallen ? "fel" : f.status === "draft" ? "vantar" : undefined,
    // Kedjan: titeln öppnar verifikationen som bokförde fakturan, och
    // `betalning` den som bokförde betalningen.
    mal: f.voucher_id ? { typ: "ver", id: f.voucher_id } : undefined,
    lankar: betalningslankar(f.payment_voucher_ids ?? []),
    betalning: OBETALD.has(f.status) && f.remaining_amount > 0 ? { invoiceId: f.id, kvar: f.remaining_amount } : undefined,
  };
}

function huvudboksFakturarad(f: HuvudboksFaktura): VyRadData {
  const status = f.paid ? `betald ${f.payment_date}` : "ingen matchande betalning";
  return {
    id: `huvudbok:${f.voucher_id}`,
    titel: f.description || "Faktura",
    meta: [f.voucher_number, f.date, status].filter(Boolean).join(" · "),
    hoger: formatBeloppHela(f.amount_inc_vat),
    mal: { typ: "ver", id: f.voucher_id },
    lankar: f.payment_voucher_id ? betalningslankar([f.payment_voucher_id]) : undefined,
  };
}

function betalningslankar(ids: string[]): VyRadData["lankar"] {
  if (ids.length === 0) return undefined;
  // Äldst först i metaraden, så att numren följer betalningarna.
  return [...ids].reverse().map((id, i) => ({
    text: ids.length === 1 ? "betalning" : `betalning ${i + 1}`,
    mal: { typ: "ver", id },
  }));
}

/**
 * Det som vyn läser utöver fakturorna. Utan
 * det är vyn den gamla läsvyn, som i skalets tester.
 */
export interface FaktureringExtra {
  /** `GET /invoice-drafts`, alla. */
  utkast: Fakturautkast[];
  /** `GET /drafts?view_key=betala.fakturering`. */
  forslag: ForslagStatusSvar[];
  /** `GET /decisions?view_key=betala.fakturering`. */
  beslut: BeslutSvar[];
  /** Klientens optimistiska rader (`utfardanden.ts`). */
  utfardanden: readonly Utfardande[];
  /**
   * Årsväljarens år. Fakturorna och besluten filtrerar servern; utkasten och
   * förslagen hämtas för alla år och visas här bara om fakturadatumet ligger
   * i året, med samma regel som `betalaVantar`.
   */
  ar?: BetalaAr;
}

const OPPNA_UTKAST = new Set(["draft", "needs_review"]);

/** Fakturor som inte gäller: utkast och makulerade. */
const EJ_FAKTURERAD = new Set(["draft", "cancelled"]);

/**
 * Årets fakturering: BokAI:s utfärdade fakturor och de bokförda utanför,
 * fakturerat, betalt, obetalt och förfallet, inklusive moms.
 */
export function faktureringSummering(lista: Fakturalista): VySektionData | null {
  const fakturor = lista.invoices.filter((f) => !EJ_FAKTURERAD.has(f.status));
  const utanfor = lista.ledger_invoices ?? [];
  if (fakturor.length + utanfor.length === 0) return null;
  const summa = (tal: number[]) => tal.reduce((a, b) => a + b, 0);

  const fakturerat = summa([...fakturor, ...utanfor].map((f) => f.amount_inc_vat));
  const moms = summa([...fakturor.map((f) => f.vat_amount ?? 0), ...utanfor.map((f) => f.vat_amount)]);
  const obetalda = [
    ...fakturor
      .filter((f) => f.remaining_amount > 0)
      .map((f) => ({ belopp: f.remaining_amount, forfallen: f.is_overdue })),
    ...utanfor.filter((f) => !f.paid).map((f) => ({ belopp: f.amount_inc_vat, forfallen: false })),
  ];
  const obetalt = summa(obetalda.map((o) => o.belopp));
  const forfallna = obetalda.filter((o) => o.forfallen);
  const forfallet = summa(forfallna.map((o) => o.belopp));
  const antal = (n: number) => `${n} faktur${n === 1 ? "a" : "or"}`;

  const rader: VyRadData[] = [
    {
      id: "summering:fakturerat",
      titel: "Fakturerat",
      meta: [antal(fakturor.length + utanfor.length), moms > 0 ? `varav moms ${formatBeloppHela(moms)}` : null]
        .filter(Boolean)
        .join(" · "),
      hoger: formatBeloppHela(fakturerat),
    },
    { id: "summering:betalt", titel: "Betalt", hoger: formatBeloppHela(fakturerat - obetalt) },
    {
      id: "summering:obetalt",
      titel: "Obetalt",
      meta: obetalda.length > 0 ? antal(obetalda.length) : undefined,
      hoger: formatBeloppHela(obetalt),
    },
  ];
  if (forfallet > 0) {
    rader.push({
      id: "summering:forfallet",
      titel: "Varav förfallet",
      meta: antal(forfallna.length),
      hoger: formatBeloppHela(forfallet),
      variant: "fel",
    });
  }
  return { titel: SUMMERING_RUBRIK, rader };
}

export function faktureringVy(lista: Fakturalista, extra?: FaktureringExtra): VyData {
  const nyast = (a: Faktura, b: Faktura) => b.invoice_date.localeCompare(a.invoice_date);
  const utfardanden = extra?.utfardanden ?? [];
  const utfardas = new Map(utfardanden.map((u) => [u.draftId, u]));

  const obetalda = lista.invoices.filter((f) => OBETALD.has(f.status));
  const gamlaUtkast = lista.invoices.filter((f) => f.status === "draft");
  const betalda = lista.invoices
    .filter((f) => f.status === "paid")
    .sort(nyast)
    .slice(0, BETALDA_ANTAL);
  const forfallna = obetalda.filter((f) => f.is_overdue).length;

  // Väntar på dig: väntande fakturaförslag och öppna beslut i vyn. Ett
  // förslag som utfärdas just nu står inte här utan som raden `utfärdas…`.
  const utkastPerId = new Map((extra?.utkast ?? []).map((u) => [u.id, u]));
  const ar = extra?.ar;
  const vantande = (extra?.forslag ?? []).filter(
    (f) =>
      (f.kind ?? "voucher") === "invoice" &&
      f.status === "pending" &&
      !utfardas.has(f.draft_id) &&
      iAret(ar, utkastPerId.get(f.draft_id)?.invoice_date)
  );
  const medForslag = new Set(vantande.map((f) => f.decision_id).filter(Boolean));
  const oppnaBeslut = (extra?.beslut ?? []).filter((b) => b.status === "open" && !medForslag.has(b.id));
  const vantarRader: VyRadData[] = [
    ...oppnaBeslut.map(
      (b): VyRadData => ({
        id: `beslut:${b.id}`,
        titel: b.title,
        meta: "väntar på dig",
        hoger: b.amount_ore !== null ? formatBeloppHela(b.amount_ore) : "",
        variant: "vantar",
        ageDays: b.age_days,
      })
    ),
    ...vantande.map((f): VyRadData => {
      const u = utkastPerId.get(f.draft_id);
      const nummer = u?.invoice_number ?? "utan nummer";
      return {
        id: `forslag:${f.draft_id}`,
        titel: u?.customer_name ?? "Fakturaförslag",
        meta: f.last_error_code
          ? "utfärdandet misslyckades · ligger kvar"
          : `förslag ${nummer} · fakturadatum ${u?.invoice_date ?? ""}`.trim(),
        hoger: u ? formatBeloppHela(u.amount_inc_vat) : "",
        variant: f.last_error_code ? "fel" : "vantar",
      };
    }),
  ];

  // Den optimistiska raden (§10.2): `utfärdas…` grå, sedan `ny` i Obetalda.
  const utfardadeIds = new Set(
    utfardanden.flatMap((u) => (u.lage === "utfardad" && u.invoiceId ? [u.invoiceId] : []))
  );
  const optimistiska: VyRadData[] = utfardanden.map((u) =>
    u.lage === "pagaende"
      ? {
          id: `utfardas:${u.draftId}`,
          titel: u.forslag?.kund ?? "Faktura",
          meta: `${u.forslag?.nummer ?? ""} · utfärdas…`.trim(),
          hoger: u.forslag ? formatBeloppHela(u.forslag.belopp) : "",
          variant: "pagaende",
        }
      : {
          id: u.invoiceId ?? `utfardad:${u.draftId}`,
          titel: u.forslag?.kund ?? "Faktura",
          meta: `${u.forslag?.nummer ?? ""} · utfärdad ${u.klockslag}${
            u.forslag?.forfaller ? ` · förfaller ${u.forslag.forfaller}` : ""
          }`.trim(),
          hoger: u.forslag ? formatBeloppHela(u.forslag.belopp) : "",
          variant: "ny",
        }
  );

  // Utkast utanför tråden: de gamla sidornas, som inte har ett väntande kort.
  const vantandeIds = new Set((extra?.forslag ?? []).filter((f) => f.status === "pending").map((f) => f.draft_id));
  const nyaUtkast = (extra?.utkast ?? []).filter(
    (u) => OPPNA_UTKAST.has(u.status) && !vantandeIds.has(u.id) && iAret(ar, u.invoice_date)
  );

  const sektioner: VySektionData[] = [];
  if (vantarRader.length > 0) sektioner.push({ titel: "Väntar på dig", rader: vantarRader });
  const summering = faktureringSummering(lista);
  if (summering) sektioner.push(summering);
  const obetaldaRader = [
    ...optimistiska,
    ...obetalda
      .filter((f) => !utfardadeIds.has(f.id))
      .sort((a, b) => a.due_date.localeCompare(b.due_date))
      .map(fakturarad),
  ];
  if (obetaldaRader.length > 0) sektioner.push({ titel: "Obetalda", rader: obetaldaRader });
  const utkastRader: VyRadData[] = [
    ...nyaUtkast.map(
      (u): VyRadData => ({
        id: `utkast:${u.id}`,
        titel: u.customer_name,
        meta: `utkast ${u.invoice_number ?? "utan nummer"}`,
        hoger: formatBeloppHela(u.amount_inc_vat),
      })
    ),
    ...gamlaUtkast.sort(nyast).map(fakturarad),
  ];
  if (utkastRader.length > 0) sektioner.push({ titel: "Utkast", rader: utkastRader });
  if (betalda.length > 0) sektioner.push({ titel: "Senast betalda", rader: betalda.map(fakturarad) });
  // Fakturor från ett annat system, bokförda som verifikationer. Serverns
  // ordning: nyast först.
  const utanfor = lista.ledger_invoices ?? [];
  if (utanfor.length > 0) sektioner.push({ titel: UTANFOR_RUBRIK, rader: utanfor.map(huvudboksFakturarad) });
  const obetaldaTotalt = obetalda.length + utanfor.filter((f) => !f.paid).length;
  const antal = lista.total + utanfor.length;

  const vantar = vantarRader.length;
  const tomt = sektioner.length === 0;
  return {
    lage: tomt ? "tomt" : vantar > 0 || forfallna > 0 ? "vantar" : "normal",
    status: tomt
      ? "inga fakturor"
      : vantar > 0
        ? `${vantar} väntar på dig`
        : forfallna > 0
          ? `${forfallna} förfallen${forfallna > 1 ? "a" : ""}`
          : `${obetaldaTotalt} obetald${obetaldaTotalt === 1 ? "" : "a"}`,
    period: ar ? `${ar.start} – ${ar.end} · ${antal} fakturor` : `${antal} fakturor i systemet`,
    sektioner,
    fot: extra
      ? "Beskriv vad som ska faktureras, så lägger agenten fram fakturan. Du utfärdar den, och PDF:en skickar du själv."
      : "Agenten svarar på frågor om fakturorna. Skicka och kreditera görs tills vidare i den gamla fakturavyn.",
  };
}

// ─── Löner ────────────────────────────────────────────────────────────────

/** Så många lönekörningar visas. */
export const LONEKORNINGAR_ANTAL = 12;

const LONESTATUS: Record<string, string> = {
  draft: "utkast",
  generated: "lönebesked skapade",
  booked: "bokförd",
};

const MANAD = [
  "januari", "februari", "mars", "april", "maj", "juni",
  "juli", "augusti", "september", "oktober", "november", "december",
];

/** Det vyn läser utöver körningarna: besluten i Löners tråd. */
export interface LonerExtra {
  /** `GET /decisions?view_key=betala.loner`. */
  beslut: BeslutSvar[];
  /** Årsväljarens år; körningarna och besluten filtrerar servern. */
  ar?: BetalaAr;
}

const LONER_VY = "betala.loner";
const FAKTURERING_VY = "betala.fakturering";

/**
 * Ett obokat lönebesked leder alltid någonstans: till sitt kort när agenten
 * lagt fram ett, annars till chattfältet (`be agenten`). En rad i väntar-ton
 * som inte går att trycka på är det som ska bort här.
 */
function lonebeskedRad(p: Lonebesked, manad: string, kort: BeslutSvar | undefined): VyRadData {
  const titel = p.employee_name ?? "Lönebesked";
  const koppla = p.attach_voucher
    ? { kopplaLonebesked: { payslipId: p.id, voucherId: p.attach_voucher.id, nummer: p.attach_voucher.number } }
    : {};
  const rad = { id: p.id, titel, hoger: formatBeloppHela(p.net_salary), ...koppla };
  if (p.voucher_id !== null) {
    return { ...rad, meta: `bokförd · utbetald ${p.payment_date}`, mal: { typ: "ver", id: p.voucher_id } };
  }
  if (p.attach_voucher) {
    // Lönen är redan bokförd från kontoutdraget: lönebeskedet ska bara kopplas.
    return { ...rad, meta: `bokförd från kontoutdraget · utbetald ${p.payment_date}`, variant: "saknar" };
  }
  if (kort) {
    return {
      ...rad,
      meta: `förslag väntar · utbetalning ${p.payment_date}`,
      variant: "vantar",
      ageDays: kort.age_days,
      beslut: kort,
    };
  }
  return {
    ...rad,
    meta: `ej bokförd · utbetalning ${p.payment_date}`,
    variant: "vantar",
    ...(p.payment_transaction_id
      ? { bokforLon: { payslipId: p.id, transactionId: p.payment_transaction_id } }
      : {}),
    fraga: { viewKey: LONER_VY, text: `Om lönen för ${titel}, ${manad}: ` },
  };
}

function agiRad(k: Lonekorning, agi: LoneAgi): VyRadData {
  const ver = agi.voucher_ids.tax ?? agi.voucher_ids.employer_fee;
  const manad = `${MANAD[agi.month - 1]} ${agi.year}`;
  const rad = { id: `agi:${k.id}`, titel: "Arbetsgivardeklaration", hoger: formatBeloppHela(agi.total_to_pay) };
  if (agi.booked) return { ...rad, meta: `bokförd · ${manad}`, mal: ver ? { typ: "ver", id: ver } : undefined };
  // Väntar på lönerna, inte på människan: raden är neutral tills de är bokförda.
  if (agi.unbooked_payslips > 0) return { ...rad, meta: `väntar på lönerna · senast ${agi.due_date}` };
  // Bokförs av agenten när kvittensen kommer in (`bokfor_agi`).
  return {
    ...rad,
    meta: `väntar på kvittensen · senast ${agi.due_date}`,
    variant: "vantar",
    fraga: { viewKey: LONER_VY, text: `Om arbetsgivardeklarationen för ${manad}: ` },
  };
}

/** En körning utan lönebesked (eller från en äldre server): en rad om körningen. */
function korningRad(k: Lonekorning): VyRadData {
  return {
    id: k.id,
    titel: "Lönekörning",
    meta: [
      LONESTATUS[k.status] ?? k.status,
      `${k.payslip_count} lönebesked`,
      k.payment_date ? `utbetalning ${k.payment_date}` : null,
    ]
      .filter(Boolean)
      .join(" · "),
    hoger: formatBeloppHela(k.total_net_salary),
    variant: k.status === "booked" ? undefined : "vantar",
  };
}

function huvudboksLonRad(l: HuvudboksLon): VyRadData {
  return {
    id: `huvudbok:${l.voucher_id}`,
    titel: l.description || "Lön",
    meta: [
      l.voucher_number,
      l.date,
      l.preliminary_tax > 0 ? `skatt ${formatBeloppHela(l.preliminary_tax)}` : null,
    ]
      .filter(Boolean)
      .join(" · "),
    // Nettolön som lönebeskeden; lönekontona när nettot inte står i verifikationen.
    hoger: formatBeloppHela(l.net_salary ?? l.gross_salary),
    mal: { typ: "ver", id: l.voucher_id },
  };
}

/**
 * Årets löner ur huvudboken: lönekostnaden, och skatten och de sociala
 * avgifterna som betalts — med det som dragits av och påförts under året i
 * metaraden. Summan är det som betalts till Skatteverket.
 */
export function lonerSummering(s: LoneSummering | null | undefined): VySektionData | null {
  if (!s || Object.values(s).every((v) => v === 0)) return null;
  return {
    titel: SUMMERING_RUBRIK,
    rader: [
      { id: "summering:lon", titel: "Löner", meta: "bokfört på lönekontona", hoger: formatBeloppHela(s.gross_salary) },
      {
        id: "summering:skatt",
        titel: "Skatt betald",
        meta: `avdragen under året ${formatBeloppHela(s.tax_withheld)}`,
        hoger: formatBeloppHela(s.tax_paid),
      },
      {
        id: "summering:avgifter",
        titel: "Sociala avgifter betalda",
        meta: `påförda under året ${formatBeloppHela(s.employer_fee_charged)}`,
        hoger: formatBeloppHela(s.employer_fee_paid),
      },
      {
        id: "summering:skatteverket",
        titel: "Betalt till Skatteverket",
        hoger: formatBeloppHela(s.tax_paid + s.employer_fee_paid),
        summa: true,
      },
    ],
  };
}

/** Bokförd hel: alla lönebesked och AGI:n. Utan AGI-uppgift räknas körningens status. */
function helBokford(k: Lonekorning): boolean {
  if (k.status !== "booked") return false;
  return k.agi ? k.agi.booked : true;
}

export function lonerVy(lista: Lonekorningar, extra?: LonerExtra): VyData {
  // Ett år har sina körningar, alla; utan år de senaste.
  const sorterade = [...lista.payroll_runs].sort((a, b) => b.year - a.year || b.month - a.month);
  const korningar = extra?.ar ? sorterade : sorterade.slice(0, LONEKORNINGAR_ANTAL);
  const oklara = korningar.filter((k) => !helBokford(k)).length;

  // Väntar på beslut: korten agenten lagt fram. Titeln tar upp kortet i
  // chatten (`BeslutFokus`), som en väntande verifikation i Verifikationer.
  const oppna = (extra?.beslut ?? []).filter((b) => b.status === "open");
  const vantarRader: VyRadData[] = oppna.map((b) => ({
    id: `beslut:${b.id}`,
    titel: b.title,
    meta: "väntar på dig",
    hoger: b.amount_ore !== null ? formatBeloppHela(b.amount_ore) : "",
    variant: "vantar",
    ageDays: b.age_days,
    beslut: b,
  }));

  const sektioner: VySektionData[] = [];
  if (vantarRader.length > 0) sektioner.push({ titel: "Väntar på beslut", rader: vantarRader });
  const summering = lonerSummering(lista.summary);
  if (summering) sektioner.push(summering);
  const kort = (id: string | null | undefined) => (id ? oppna.find((b) => b.id === id) : undefined);
  for (const k of korningar) {
    const besked = k.payslips ?? [];
    const manad = `${MANAD[k.month - 1] ?? k.month} ${k.year}`;
    const rader =
      besked.length > 0 ? besked.map((p) => lonebeskedRad(p, manad, kort(p.pending_decision_id))) : [korningRad(k)];
    if (k.agi) rader.push(agiRad(k, k.agi));
    sektioner.push({ titel: `${MANAD[k.month - 1] ?? k.month} ${k.year}`, rader });
  }
  // Löner från ett annat lönesystem, bokförda som verifikationer. Ett år har
  // alla sina; utan år de senaste.
  const utanforAlla = lista.ledger_payouts ?? [];
  const utanfor = extra?.ar ? utanforAlla : utanforAlla.slice(0, LONEKORNINGAR_ANTAL);
  if (utanfor.length > 0) sektioner.push({ titel: UTANFOR_RUBRIK, rader: utanfor.map(huvudboksLonRad) });

  const vantar = vantarRader.length;
  const tomt = korningar.length === 0 && vantar === 0 && utanfor.length === 0 && !summering;
  const antal = [
    korningar.length > 0 ? `${lista.payroll_runs.length} lönekörningar` : null,
    utanforAlla.length > 0 ? `${utanforAlla.length} bokförda utanför BokAI` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return {
    lage: tomt ? "tomt" : vantar > 0 || oklara > 0 ? "vantar" : "normal",
    status: tomt
      ? "inga lönekörningar"
      : vantar > 0
        ? `${vantar} väntar på dig`
        : oklara > 0
          ? `${oklara} ej bokförd${oklara > 1 ? "a" : ""}`
          : "alla bokförda",
    period: extra?.ar
      ? `${extra.ar.start} – ${extra.ar.end} · ${antal ? `${antal} · nettolön` : "inga lönekörningar"}`
      : tomt
        ? "Nettolön per lönebesked"
        : `${antal} · nettolön`,
    sektioner,
    fot: "Lönerna ställs in och månadens lönebesked skapas under Inställningar → Anställda. Be agenten bokföra lönen, så lägger den fram ett kort. Du bokför med ett tryck i kortet. Arbetsgivardeklarationen bokför agenten själv när kvittensen kommer in.",
  };
}

// ─── Det som väntar i Betala, sett från Verifikationer ────────────────────

/** Det Verifikationer läser ur Betala-sidans vyer. Samma frågor som vyerna själva. */
export interface BetalaVantarKallor {
  /** `GET /decisions?view_key=betala.loner`. */
  lonerBeslut: BeslutSvar[];
  /** `GET /drafts?view_key=betala.fakturering`. */
  faktureringForslag: ForslagStatusSvar[];
  /** `GET /invoice-drafts`: namn, nummer och belopp till förslagen. */
  fakturautkast: Fakturautkast[];
  /**
   * Räkenskapsåret Verifikationer visar: bara fakturor med fakturadatum i
   * året står med. Lönekorten filtreras av servern (`fiscal_year_id`).
   */
  ar?: BetalaAr;
}

/**
 * Det som håller på att bli en verifikation i Betala: ett lönekort som
 * väntar och ett fakturaförslag som väntar. Verifikationer visar dem under
 * Väntar på beslut, märkta med varifrån de kommer; raden leder till vyn
 * och tar upp kortet i dess tråd, där det besvaras.
 *
 * Faktureringens andra beslut (bolagsuppgifterna) bokför ingenting och står
 * inte här.
 */
export function betalaVantar(k: BetalaVantarKallor): VyRadData[] {
  const loner: VyRadData[] = k.lonerBeslut
    .filter((b) => b.status === "open")
    .map((b) => ({
      id: `betala.loner:${b.id}`,
      titel: b.title,
      meta: "lön · väntar i Löner",
      hoger: b.amount_ore !== null ? formatBeloppHela(b.amount_ore) : "",
      variant: "vantar",
      ageDays: b.age_days,
      beslut: b,
      mal: { typ: "vy", key: LONER_VY },
    }));
  const utkast = new Map(k.fakturautkast.map((u) => [u.id, u]));
  const fakturor: VyRadData[] = k.faktureringForslag
    .filter((f) => (f.kind ?? "voucher") === "invoice" && f.status === "pending")
    // Utan utkastet vet vyn inte året; raden står kvar hellre än försvinner.
    .filter((f) => iAret(k.ar, utkast.get(f.draft_id)?.invoice_date))
    .map((f) => {
      const u = utkast.get(f.draft_id);
      const titel = u ? `Faktura ${u.invoice_number ?? "utan nummer"} · ${u.customer_name}` : "Fakturaförslag";
      return {
        id: `betala.fakturering:${f.draft_id}`,
        titel,
        meta: f.last_error_code ? "faktura · utfärdandet misslyckades" : "faktura · väntar i Fakturor",
        hoger: u ? formatBeloppHela(u.amount_inc_vat) : "",
        variant: f.last_error_code ? "fel" : "vantar",
        mal: { typ: "vy", key: FAKTURERING_VY },
        inlagg: { viewKey: FAKTURERING_VY, postId: f.post_id },
      };
    });
  return [...loner, ...fakturor];
}
