/**
 * Mockad data för skalet (modul `skal`).
 *
 * ALLT påhittat innehåll ligger här, aldrig inline i en komponent och aldrig
 * som en `if (mock)`-gren. Komponenterna tar data som props och vet inte att
 * den är påhittad — annars blir bytet till riktiga källor en omskrivning i
 * stället för ett byte av källa. SPEC-skal.md §8.
 *
 * Varje export säger vilken modul som ersätter den.
 */

import type { ViewKey } from "@/lib/skal/vyer";

/** De sex lägena i README.md §Tillstånd. En vy ska kunna visa alla sex. */
export type VyLage = "normal" | "vantar" | "pagaende" | "klart" | "fel" | "tomt";

/** `VyRad`-varianterna i komponenter.md. */
export type RadVariant = "normal" | "saknar" | "vantar" | "pagaende" | "ny" | "fel" | "paverkad";

export type BannerTon = "varning" | "neutral" | "fel" | "klart";

export interface VyRadData {
  id: string;
  titel: string;
  meta?: string;
  hoger: string;
  variant?: RadVariant;
  /** Summarad: samma vikt som designens `r.vikt` 500. */
  summa?: boolean;
}

export interface VySektionData {
  titel: string;
  rader: VyRadData[];
}

export interface VyData {
  lage: VyLage;
  /** Kort status, samma sträng i headern och i vyns rubrikrad. */
  status: string;
  period: string;
  banner?: { ton: BannerTon; text: string };
  sektioner: VySektionData[];
  /** Fottexten säger vad agenten gör härnäst. Inget mer. */
  fot: string;
}

/** Två typer räcker för skalet. Korten är `chattyta`. */
export interface TradInlaggData {
  id: string;
  typ: "agent_text" | "user_text";
  /** Metarad i formatet `agenten · 06:41`. */
  meta: string;
  text: string;
}

// ─── Vyernas rader ────────────────────────────────────────────────────────
// ERSÄTTS AV: vyernas egna endpoints (balans-/resultaträkning, verifikations-
// listan, fakturor, lönekörningar, rapporter). Ingen av dem är skalets.

const BALANS: VyData = {
  lage: "vantar",
  status: "2 bankhändelser obokade",
  period: "Per 2026-06-01 · uppdaterad 06:41",
  banner: {
    ton: "varning",
    text: "2 bankhändelser är ännu inte bokförda. Saldona kan ändras när de är klara.",
  },
  sektioner: [
    {
      titel: "Tillgångar",
      rader: [
        { id: "1930", titel: "Företagskonto", meta: "1930", hoger: "400 720" },
        { id: "1510", titel: "Kundfordringar", meta: "1510", hoger: "148 500" },
        { id: "1250", titel: "Inventarier", meta: "1250", hoger: "62 000" },
        { id: "sum-t", titel: "Summa tillgångar", hoger: "611 220", summa: true },
      ],
    },
    {
      titel: "Eget kapital och skulder",
      rader: [
        { id: "2081", titel: "Aktiekapital", meta: "2081", hoger: "25 000" },
        { id: "2091", titel: "Balanserat resultat", meta: "2091", hoger: "318 400" },
        { id: "2099", titel: "Årets resultat", meta: "2099", hoger: "129 620" },
        { id: "2440", titel: "Leverantörsskulder", meta: "2440", hoger: "96 300" },
        { id: "2641", titel: "Moms", meta: "2641", hoger: "41 900" },
        { id: "sum-s", titel: "Summa", hoger: "611 220", summa: true },
      ],
    },
  ],
  fot: "Agenten stämmer av banken härnäst.",
};

const RESULTAT: VyData = {
  lage: "normal",
  status: "avstämd",
  period: "2026-01-01 – 2026-06-30 · uppdaterad 06:41",
  sektioner: [
    {
      titel: "Intäkter",
      rader: [
        { id: "3011", titel: "Försäljning", meta: "3011", hoger: "842 500" },
        { id: "3740", titel: "Öresutjämning", meta: "3740", hoger: "−12" },
      ],
    },
    {
      titel: "Kostnader",
      rader: [
        { id: "5010", titel: "Lokalhyra", meta: "5010", hoger: "−96 000" },
        { id: "6212", titel: "Mobiltelefoni", meta: "6212", hoger: "−7 184" },
        { id: "res", titel: "Resultat", hoger: "129 620", summa: true },
      ],
    },
  ],
  fot: "Agenten rapporterar när juni är avstämd.",
};

const VERIFIKATIONER: VyData = {
  lage: "pagaende",
  status: "postar A-118",
  period: "Juni 2026 · 34 verifikationer",
  banner: { ton: "neutral", text: "En verifikation postas just nu. Raden är grå tills den är klar." },
  sektioner: [
    {
      titel: "Väntar",
      rader: [
        {
          id: "A-118",
          titel: "Nordkraft AB · elnät",
          meta: "A-118 · postas…",
          hoger: "4 480",
          variant: "pagaende",
        },
        {
          id: "swish",
          titel: "Swish-inbetalning utan referens",
          meta: "väntar på ditt beslut",
          hoger: "4 500",
          variant: "vantar",
        },
      ],
    },
    {
      titel: "Senast postade",
      rader: [
        { id: "A-117", titel: "Sjöstad Fastigheter · hyra juli", meta: "A-117 · 2026-06-28", hoger: "36 250" },
        {
          id: "A-116",
          titel: "Atelié Vind · konsultarvode",
          meta: "A-116 · saknar underlag · 9 dagar",
          hoger: "18 500",
          variant: "saknar",
        },
      ],
    },
  ],
  fot: "Agenten fortsätter med de två obokade bankhändelserna.",
};

const FAKTURERING: VyData = {
  lage: "normal",
  status: "1 förfallen",
  period: "Juni 2026 · 6 fakturor",
  sektioner: [
    {
      titel: "Obetalda",
      rader: [
        {
          id: "1042",
          titel: "Nordkraft AB",
          meta: "1042 · förfallen sedan 6 dagar",
          hoger: "93 750",
          variant: "fel",
        },
        { id: "1043", titel: "Sjöstad Fastigheter", meta: "1043 · förfaller 28 juni", hoger: "36 250" },
        { id: "1044", titel: "Atelié Vind", meta: "1044 · förfaller 4 juli", hoger: "18 500" },
      ],
    },
  ],
  fot: "Agenten svarar på frågor om fakturorna. Skicka och kreditera görs tills vidare i den gamla fakturavyn.",
};

const LONER: VyData = {
  lage: "normal",
  status: "juni klar",
  period: "Juni 2026 · 3 anställda",
  sektioner: [
    {
      titel: "Juni",
      rader: [
        { id: "ap", titel: "Anna Pettersson", meta: "utbetald 2026-06-25", hoger: "38 400" },
        { id: "ml", titel: "Mats Lund", meta: "utbetald 2026-06-25", hoger: "34 900" },
        { id: "sn", titel: "Sara Nyström", meta: "utbetald 2026-06-25", hoger: "31 200" },
      ],
    },
  ],
  fot: "Agenten svarar på frågor om lönerna. Godkännande görs tills vidare i den gamla lönevyn.",
};

const RAPPORTER: VyData = {
  lage: "klart",
  status: "inlämnat",
  period: "Bokslut 2025 · inlämnat 14 mars",
  sektioner: [
    {
      titel: "Rapporter",
      rader: [
        { id: "ar", titel: "Årsredovisning 2025", meta: "inlämnad 2026-03-14", hoger: "PDF", variant: "ny" },
        { id: "ink2", titel: "Inkomstdeklaration 2", meta: "inlämnad 2026-04-02", hoger: "PDF" },
        { id: "hb", titel: "Huvudbok", meta: "komplett", hoger: "PDF" },
        { id: "bs", titel: "Balansspecifikationer", meta: "komplett", hoger: "PDF" },
        { id: "av", titel: "Avskrivningsunderlag", meta: "komplett", hoger: "PDF" },
        { id: "sie", titel: "Bokföring i SIE-format", meta: "komplett", hoger: "SIE" },
      ],
    },
  ],
  fot: "Agenten påminner när nästa bokslut närmar sig.",
};

/** Tomt läge: sektionen utgår helt, inte en tom rubrik. */
const ATGARDER: VyData = {
  lage: "tomt",
  status: "inget väntar",
  period: "Räkenskapsår 2026",
  sektioner: [],
  fot: "Agenten säger till när något behöver göras inför bokslutet.",
};

export const MOCK_VYER: Record<ViewKey, VyData> = {
  "bocker.balans": BALANS,
  "bocker.resultat": RESULTAT,
  "bocker.verifikationer": VERIFIKATIONER,
  "betala.fakturering": FAKTURERING,
  "betala.loner": LONER,
  "bokslut.rapporter": RAPPORTER,
  "bokslut.atgarder": ATGARDER,
};

// ─── Tråden ───────────────────────────────────────────────────────────────
// ERSÄTTS AV: `tradar` (GET /api/v1/threads/{view_key} + SSE) för datan, och
// `chattyta` för renderingen. Skalet kan bara två typer med flit: korten bär
// kontrakt (ingen förvald rekommendation, alltid en väg ut, båda talen) som
// skalet inte äger.

const TRAD: Record<ViewKey, TradInlaggData[]> = {
  "bocker.balans": [
    { id: "1", typ: "agent_text", meta: "agenten · 06:41", text: "Balansräkningen är uppdaterad per i morse. Två bankhändelser ligger kvar obokade — jag avstod från att gissa kontering på den ena." },
    { id: "2", typ: "user_text", meta: "du · 09:12", text: "Vad består kundfordringarna av?" },
    { id: "3", typ: "agent_text", meta: "agenten · 09:12", text: "148 500 kr i tre fakturor. Nordkraft är förfallen sedan sex dagar, de andra två har inte nått förfallodagen." },
  ],
  "bocker.resultat": [
    { id: "1", typ: "agent_text", meta: "agenten · 06:41", text: "Resultatet för första halvåret är 129 620 kr. Ingenting i perioden är obokat." },
  ],
  "bocker.verifikationer": [
    { id: "1", typ: "agent_text", meta: "agenten · 06:39", text: "Jag postar elnätsfakturan från Nordkraft nu. Den matchar bankhändelsen på öret." },
    { id: "2", typ: "agent_text", meta: "agenten · 06:41", text: "Swish-inbetalningen på 4 500 kr saknar referens. Beloppet stämmer med faktura 1044, men avsändaren är en privatperson — jag bokför den inte mot kundfordran på gissning." },
  ],
  "betala.fakturering": [
    { id: "1", typ: "agent_text", meta: "agenten · 06:40", text: "Faktura 1042 till Nordkraft är förfallen sedan sex dagar. Jag skickar ingen påminnelse av mig själv." },
  ],
  "betala.loner": [
    { id: "1", typ: "agent_text", meta: "agenten · 06:40", text: "Junilönerna är utbetalda och bokförda. Nästa körning är den 25 juli." },
  ],
  "bokslut.rapporter": [
    { id: "1", typ: "agent_text", meta: "agenten · 06:40", text: "Bokslutet för 2025 är inlämnat. Alla underlag ligger kvar och går att hämta." },
  ],
  "bokslut.atgarder": [
    { id: "1", typ: "agent_text", meta: "agenten · 06:40", text: "Ingenting väntar inför bokslutet just nu. Perioden är avstämd." },
  ],
};

export function mockTrad(key: ViewKey): TradInlaggData[] {
  return TRAD[key] ?? [];
}

/**
 * Väntande beslut per vy — driver märket på mobilens `ChattList`, som ska
 * synas även när chatten är minimerad (komponenter.md).
 * ERSÄTTS AV: `beslut` (GET /decisions?status=open).
 */
export function mockVantandeBeslut(key: ViewKey): number {
  return key === "bocker.verifikationer" ? 1 : 0;
}
