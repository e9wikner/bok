/**
 * Fakturering och Löner ur riktiga data (modul `skal`).
 *
 * Fakturering är en skrivvy sedan fakturering F1 (SPEC-fakturering-f1.md
 * §10): agenten lägger fram fakturan i tråden och människan utfärdar den i
 * kortet. Löner är fortfarande en läsvy (SPEC-skal.md §11): skrivning sker
 * tills vidare i den gamla vyn, och det säger fottexten.
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
  status: string;
  is_overdue: boolean;
}

export interface Fakturalista {
  total: number;
  invoices: Faktura[];
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

export interface Lonekorning {
  id: string;
  year: number;
  month: number;
  payment_date: string | null;
  status: string;
  payslip_count: number;
  total_gross_salary: number;
  total_net_salary: number;
}

export interface Lonekorningar {
  payroll_runs: Lonekorning[];
}

export const betalaApi = {
  getFakturor: async (): Promise<Fakturalista> => {
    const { data } = await apiClient.get<Fakturalista>("/api/v1/invoices");
    return data;
  },

  getFakturautkast: async (): Promise<Fakturautkastlista> => {
    const { data } = await apiClient.get<Fakturautkastlista>("/api/v1/invoice-drafts");
    return data;
  },

  getLonekorningar: async (): Promise<Lonekorningar> => {
    const { data } = await apiClient.get<Lonekorningar>("/api/v1/payroll/runs");
    return data;
  },
};

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
  };
}

/**
 * Det som vyn läser utöver fakturorna (SPEC-fakturering-f1.md §10.2). Utan
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
}

const OPPNA_UTKAST = new Set(["draft", "needs_review"]);

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
  const vantande = (extra?.forslag ?? []).filter(
    (f) => (f.kind ?? "voucher") === "invoice" && f.status === "pending" && !utfardas.has(f.draft_id)
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
  const nyaUtkast = (extra?.utkast ?? []).filter((u) => OPPNA_UTKAST.has(u.status) && !vantandeIds.has(u.id));

  const sektioner: VySektionData[] = [];
  if (vantarRader.length > 0) sektioner.push({ titel: "Väntar på dig", rader: vantarRader });
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
          : `${obetalda.length} obetald${obetalda.length === 1 ? "" : "a"}`,
    period: `${lista.total} fakturor i systemet`,
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

export function lonerVy(lista: Lonekorningar): VyData {
  const korningar = [...lista.payroll_runs]
    .sort((a, b) => b.year - a.year || b.month - a.month)
    .slice(0, LONEKORNINGAR_ANTAL);
  const oklara = korningar.filter((k) => k.status !== "booked").length;

  const rader: VyRadData[] = korningar.map((k) => ({
    id: k.id,
    titel: `${MANAD[k.month - 1] ?? k.month} ${k.year}`,
    meta: [
      LONESTATUS[k.status] ?? k.status,
      `${k.payslip_count} lönebesked`,
      k.payment_date ? `utbetalning ${k.payment_date}` : null,
    ]
      .filter(Boolean)
      .join(" · "),
    hoger: formatBeloppHela(k.total_gross_salary),
    variant: k.status === "booked" ? undefined : "vantar",
  }));

  const tomt = rader.length === 0;
  return {
    lage: tomt ? "tomt" : oklara > 0 ? "vantar" : "normal",
    status: tomt ? "inga lönekörningar" : oklara > 0 ? `${oklara} ej bokförd${oklara > 1 ? "a" : ""}` : "alla bokförda",
    period: tomt ? "Bruttolön per körning" : `${lista.payroll_runs.length} lönekörningar · bruttolön`,
    sektioner: tomt ? [] : [{ titel: "Lönekörningar", rader }],
    fot: "Agenten svarar på frågor om lönerna. Godkännande görs tills vidare i den gamla lönevyn.",
  };
}
