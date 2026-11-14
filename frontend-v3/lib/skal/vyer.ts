/**
 * Sid- och vykartan (modul `skal`).
 *
 * Skalets enda sanning om vad som finns: fyra sidor och deras vyer.
 *
 * `view_key` är samma sju nycklar som servern validerar mot i
 * Listan är SLUTEN: en okänd nyckel ger 404 på servern,
 * inte en tom tråd. En åttonde vy kräver att specen ändras först.
 *
 * Kartan ligger som data, inte utspridd i JSX, så att ett stavfel blir ett
 * typfel.
 */

export type Sidnyckel = "bocker" | "betala" | "bokslut" | "installningar";

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
 * Årsredovisningens uppgifter fylls i på Översikten.
 */
export type BokslutDel = "bokslut.ink2" | "bokslut.moms" | "bokslut.arsredovisning";

/**
 * Underlag: dropzonens mappar (samma som SMB-utdelningen), i webben. Ingen
 * egen tråd — den chattar i Verifikationers, där underlagen bokförs.
 * Servern känner inte nyckeln.
 */
export type Dropzonevy = "bocker.dropzone";

/**
 * Inställningar: register och regler som arbetet läser ur men som sällan
 * ändras. Ingen har egen tråd — var och en chattar i tråden för arbetet den
 * hör till (`trad`). Servern känner inte nycklarna.
 *
 * - Företaget: företagets uppgifter och det som står på fakturan.
 * - Kunder och artiklar: registren fakturorna skrivs ur.
 * - Anställda: lön, skatt och avgift, och där månadens lönebesked skapas.
 * - Kontoplan, och SRU-kopplingen (vilket INK2R-fält varje konto summeras till).
 * - Instruktioner: företagets regler till agenten, för bokföringen och för
 *   faktureringen.
 * - Revisionslogg: behandlingshistoriken.
 */
export type Installningsvy =
  | "installningar.foretaget"
  | "installningar.kunder"
  | "installningar.anstallda"
  | "installningar.kontoplan"
  | "installningar.sru"
  | "installningar.instruktioner"
  | "installningar.revisionslogg";

/** En vy i navigeringen: en trådvy, en bokslutsdel eller en vy med egen komponent. */
export type Vynyckel = ViewKey | BokslutDel | Dropzonevy | Installningsvy;

export interface Vy {
  readonly key: Vynyckel;
  /** Tråden vyn chattar i, mot servern. Samma som `key` för de sju trådvyerna. */
  readonly trad: ViewKey;
  /** Kort nyckel i URL:en, t.ex. "balans". */
  readonly slug: string;
  readonly titel: string;
  readonly sida: Sidnyckel;
}

export interface Sida {
  readonly key: Sidnyckel;
  readonly titel: string;
  readonly vyer: readonly Vy[];
}

const vy = (sida: Sidnyckel, slug: string, titel: string, trad?: ViewKey, key?: Vynyckel): Vy => {
  const k = key ?? (`${sida}.${slug}` as Vynyckel);
  return { key: k, trad: trad ?? (k as ViewKey), slug, titel, sida };
};

/**
 * Fyra sidor. De tre första är arbetet, i den ordning det görs: bokföra,
 * fakturera och betala lön, göra bokslut. Den fjärde är det som ställs in en
 * gång. Sidnycklarna `bocker`, `betala` och `bokslut` är serverns
 * (`GET /overview`); `installningar` finns bara här.
 */
export const SIDOR: readonly Sida[] = Object.freeze([
  Object.freeze({
    key: "bocker" as const,
    titel: "Bokföring",
    vyer: Object.freeze([
      vy("bocker", "verifikationer", "Verifikationer"),
      vy("bocker", "underlag", "Underlag", "bocker.verifikationer", "bocker.dropzone"),
      vy("bocker", "balans", "Balansräkning"),
      vy("bocker", "resultat", "Resultaträkning"),
    ]),
  }),
  Object.freeze({
    key: "betala" as const,
    titel: "Fakturor och löner",
    vyer: Object.freeze([
      vy("betala", "fakturor", "Fakturor", "betala.fakturering", "betala.fakturering"),
      vy("betala", "loner", "Löner"),
    ]),
  }),
  Object.freeze({
    key: "bokslut" as const,
    titel: "Bokslut",
    vyer: Object.freeze([
      // Översikt till Årsredovisning gäller året i årsväljaren och delar tråd.
      vy("bokslut", "oversikt", "Översikt", "bokslut.rapporter", "bokslut.rapporter"),
      vy("bokslut", "moms", "Moms", "bokslut.rapporter"),
      vy("bokslut", "ink2", "INK2", "bokslut.rapporter"),
      vy("bokslut", "arsredovisning", "Årsredovisning", "bokslut.rapporter"),
      vy("bokslut", "atgarder", "Åtgärder och nyckeltal"),
    ]),
  }),
  Object.freeze({
    key: "installningar" as const,
    titel: "Inställningar",
    vyer: Object.freeze([
      vy("installningar", "foretaget", "Företaget", "betala.fakturering"),
      vy("installningar", "kunder", "Kunder och artiklar", "betala.fakturering"),
      vy("installningar", "anstallda", "Anställda", "betala.loner"),
      vy("installningar", "kontoplan", "Kontoplan", "bocker.verifikationer"),
      vy("installningar", "sru", "SRU-koppling", "bokslut.rapporter"),
      vy("installningar", "instruktioner", "Instruktioner", "bocker.verifikationer"),
      vy("installningar", "revisionslogg", "Revisionslogg", "bocker.verifikationer"),
    ]),
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
const BOKSLUTSDELAR: readonly BokslutDel[] = ["bokslut.ink2", "bokslut.moms", "bokslut.arsredovisning"];

export function allaVyer(): readonly Vy[] {
  return SIDOR.flatMap((s) => s.vyer);
}
