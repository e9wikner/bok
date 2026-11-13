/**
 * Sid- och vykartan (modul `skal`).
 *
 * Skalets enda sanning om vad som finns: tre sidor och deras vyer, i designens
 * ordning (design_handoff_bokai/README.md §Informationsarkitektur).
 *
 * `view_key` är samma sju nycklar som servern validerar mot i
 * Listan är SLUTEN: en okänd nyckel ger 404 på servern,
 * inte en tom tråd. En åttonde vy kräver att specen ändras först.
 *
 * Kartan ligger som data, inte utspridd i JSX, så att ett stavfel blir ett
 * typfel.
 */

export type Sidnyckel = "bocker" | "betala" | "bokslut";

export type ViewKey =
  | "bocker.balans"
  | "bocker.resultat"
  | "bocker.verifikationer"
  | "betala.fakturering"
  | "betala.loner"
  | "bokslut.rapporter"
  | "bokslut.atgarder";

/**
 * Bokslutets delar för det valda räkenskapsåret. De är egna vyer i
 * navigeringen men inga egna trådar: de delar Översiktens tråd
 * (`bokslut.rapporter`), så att samtalet om ett års bokslut är ett samtal
 * oavsett vilken del som står framme. Servern känner inte nycklarna.
 */
export type BokslutDel = "bokslut.ink2" | "bokslut.moms" | "bokslut.arsredovisning" | "bokslut.uppgifter";

/**
 * Dropzonen: samma mappar som SMB-utdelningen, i webben. Ingen egen tråd —
 * den chattar i Verifikationers, där underlagen bokförs. Servern känner
 * inte nyckeln.
 */
export type Dropzonevy = "bocker.dropzone";

/**
 * Anställda: där lönerna ställs in (anställda, lön, skatt, avgift) och
 * månadens lönebesked skapas. Ingen egen tråd — den chattar i Löners, där
 * lönebeskeden bokförs. Servern känner inte nyckeln.
 */
export type Anstalldavy = "betala.anstallda";

/**
 * Företaget: företagets uppgifter och det som står på fakturan. Ingen egen
 * tråd — den chattar i Fakturerings. Servern känner inte nyckeln.
 */
export type Foretagsvy = "betala.foretaget";

/**
 * SRU-kopplingen för året i headern: vilket INK2R-fält varje konto summeras
 * till. Ingen egen tråd — den chattar i Översiktens, som bokslutsdelarna.
 * Servern känner inte nyckeln.
 */
export type Sruvy = "bokslut.sru";

/**
 * Böckernas register: kontoplanen och revisionsloggen. Ingen egen tråd —
 * de chattar i Verifikationers. Servern känner inte nycklarna.
 */
export type Registervy = "bocker.kontoplan" | "bocker.revisionslogg";

/** En vy i navigeringen: en trådvy, en bokslutsdel eller en vy med egen komponent. */
export type Vynyckel = ViewKey | BokslutDel | Dropzonevy | Anstalldavy | Registervy | Foretagsvy | Sruvy;

export interface Vy {
  readonly key: Vynyckel;
  /** Tråden vyn chattar i, mot servern. Samma som `key` utom för bokslutsdelarna. */
  readonly trad: ViewKey;
  /** Kort nyckel i URL:en, t.ex. "balans". */
  readonly slug: string;
  readonly titel: string;
  readonly sida: Sidnyckel;
  /**
   * Läsvy utan skrivflöde: rader och tråd, ingen
   * primärknapp, inget godkännandekort och ingen avstängd knapp. Ingen vy är
   * det längre: Fakturering skriver sedan fakturering F1 och Löner sedan
   * lönebokföringen i tråden. Fältet står kvar för en vy som kommer utan
   * skrivflöde.
   */
  readonly lasvy: boolean;
}

export interface Sida {
  readonly key: Sidnyckel;
  readonly titel: string;
  readonly vyer: readonly Vy[];
}

export const SIDOR: readonly Sida[] = Object.freeze([
  Object.freeze({
    key: "bocker" as const,
    titel: "Böcker",
    vyer: Object.freeze([
      { key: "bocker.balans", trad: "bocker.balans", slug: "balans", titel: "Balansräkning", sida: "bocker", lasvy: false },
      { key: "bocker.resultat", trad: "bocker.resultat", slug: "resultat", titel: "Resultaträkning", sida: "bocker", lasvy: false },
      {
        key: "bocker.verifikationer",
        trad: "bocker.verifikationer",
        slug: "verifikationer",
        titel: "Verifikationer",
        sida: "bocker",
        lasvy: false,
      },
      {
        key: "bocker.dropzone",
        trad: "bocker.verifikationer",
        slug: "dropzone",
        titel: "Dropzone",
        sida: "bocker",
        lasvy: false,
      },
      {
        key: "bocker.kontoplan",
        trad: "bocker.verifikationer",
        slug: "kontoplan",
        titel: "Kontoplan",
        sida: "bocker",
        lasvy: false,
      },
      {
        key: "bocker.revisionslogg",
        trad: "bocker.verifikationer",
        slug: "revisionslogg",
        titel: "Revisionslogg",
        sida: "bocker",
        lasvy: false,
      },
    ] as const),
  }),
  Object.freeze({
    key: "betala" as const,
    titel: "Fakturering och löner",
    vyer: Object.freeze([
      {
        key: "betala.fakturering",
        trad: "betala.fakturering",
        slug: "fakturering",
        titel: "Fakturering",
        sida: "betala",
        // Skrivvy sedan fakturering F1.
        lasvy: false,
      },
      { key: "betala.loner", trad: "betala.loner", slug: "loner", titel: "Löner", sida: "betala", lasvy: false },
      {
        key: "betala.anstallda",
        trad: "betala.loner",
        slug: "anstallda",
        titel: "Anställda",
        sida: "betala",
        lasvy: false,
      },
      {
        key: "betala.foretaget",
        trad: "betala.fakturering",
        slug: "foretaget",
        titel: "Företaget",
        sida: "betala",
        lasvy: false,
      },
    ] as const),
  }),
  Object.freeze({
    key: "bokslut" as const,
    titel: "Bokslut",
    vyer: Object.freeze([
      // Översikt till Uppgifter gäller året i årsväljaren och delar tråd.
      {
        key: "bokslut.rapporter",
        trad: "bokslut.rapporter",
        slug: "oversikt",
        titel: "Översikt",
        sida: "bokslut",
        lasvy: false,
      },
      { key: "bokslut.ink2", trad: "bokslut.rapporter", slug: "ink2", titel: "INK2", sida: "bokslut", lasvy: false },
      {
        key: "bokslut.sru",
        trad: "bokslut.rapporter",
        slug: "sru",
        titel: "SRU-koppling",
        sida: "bokslut",
        lasvy: false,
      },
      { key: "bokslut.moms", trad: "bokslut.rapporter", slug: "moms", titel: "Moms", sida: "bokslut", lasvy: false },
      {
        key: "bokslut.arsredovisning",
        trad: "bokslut.rapporter",
        slug: "arsredovisning",
        titel: "Årsredovisning",
        sida: "bokslut",
        lasvy: false,
      },
      {
        key: "bokslut.uppgifter",
        trad: "bokslut.rapporter",
        slug: "uppgifter",
        titel: "Uppgifter",
        sida: "bokslut",
        lasvy: false,
      },
      {
        key: "bokslut.atgarder",
        trad: "bokslut.atgarder",
        slug: "atgarder",
        titel: "Åtgärder och nyckeltal",
        sida: "bokslut",
        lasvy: false,
      },
    ] as const),
  }),
]);

export const SIDNYCKLAR: readonly Sidnyckel[] = SIDOR.map((s) => s.key);

export function arSidnyckel(v: string | null | undefined): v is Sidnyckel {
  return SIDNYCKLAR.includes(v as Sidnyckel);
}

export function sidan(key: Sidnyckel): Sida {
  const s = SIDOR.find((x) => x.key === key);
  if (!s) throw new Error(`Okänd sidnyckel: ${key}`);
  return s;
}

/**
 * Byte av sida landar ALLTID på sidans första vy — aldrig på den vy man var
 * på sist. Det står i README.md §Informationsarkitektur och är en regel, inte
 * en bekvämlighet: "senast besökta" gör navigeringen oförutsägbar.
 */
export function forstaVyn(sida: Sidnyckel): Vy {
  return sidan(sida).vyer[0];
}

export function vyAt(sida: Sidnyckel, index: number): Vy | undefined {
  return sidan(sida).vyer[index];
}

export function vyMedSlug(sida: Sidnyckel, slug: string | null | undefined): Vy | undefined {
  if (!slug) return undefined;
  return sidan(sida).vyer.find((v) => v.slug === slug);
}

export function vyIndex(sida: Sidnyckel, key: Vynyckel): number {
  return sidan(sida).vyer.findIndex((v) => v.key === key);
}

/** view_key härleds ur kartan, aldrig ur en sträng som klistras ihop. */
export function viewKeyOf(sida: Sidnyckel, index: number): ViewKey | undefined {
  return vyAt(sida, index)?.trad;
}

export function arBokslutsdel(key: Vynyckel): key is BokslutDel | "bokslut.rapporter" {
  return key === "bokslut.rapporter" || BOKSLUTSDELAR.includes(key as BokslutDel);
}
const BOKSLUTSDELAR: readonly BokslutDel[] = [
  "bokslut.ink2",
  "bokslut.moms",
  "bokslut.arsredovisning",
  "bokslut.uppgifter",
];

export function allaVyer(): readonly Vy[] {
  return SIDOR.flatMap((s) => s.vyer);
}
