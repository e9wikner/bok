/**
 * Sid- och vykartan (modul `skal`).
 *
 * Skalets enda sanning om vad som finns: tre sidor, sju vyer, i designens
 * ordning (design_handoff_bokai/README.md §Informationsarkitektur).
 *
 * `view_key` är samma sju nycklar som servern validerar mot i
 * SPEC-tradar.md §5. Listan är SLUTEN: en okänd nyckel ger 404 på servern,
 * inte en tom tråd. En åttonde vy kräver att specen ändras först.
 *
 * Kartan ligger som data, inte utspridd i JSX, så att ett stavfel blir ett
 * typfel. SPEC-skal.md §5.
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

export interface Vy {
  readonly key: ViewKey;
  /** Kort nyckel i URL:en, t.ex. "balans". */
  readonly slug: string;
  readonly titel: string;
  readonly sida: Sidnyckel;
  /**
   * Läsvy utan skrivflöde. Flöde 2 och 3 är ur scope (ANALYS.md §8), så
   * Fakturering och Löner visar rader och tråd men har ingen primärknapp,
   * inget godkännandekort och ingen avstängd knapp. SPEC-skal.md §11.
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
      { key: "bocker.balans", slug: "balans", titel: "Balansräkning", sida: "bocker", lasvy: false },
      { key: "bocker.resultat", slug: "resultat", titel: "Resultaträkning", sida: "bocker", lasvy: false },
      {
        key: "bocker.verifikationer",
        slug: "verifikationer",
        titel: "Verifikationer",
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
        slug: "fakturering",
        titel: "Fakturering",
        sida: "betala",
        lasvy: true,
      },
      { key: "betala.loner", slug: "loner", titel: "Löner", sida: "betala", lasvy: true },
    ] as const),
  }),
  Object.freeze({
    key: "bokslut" as const,
    titel: "Bokslut",
    vyer: Object.freeze([
      {
        key: "bokslut.rapporter",
        slug: "rapporter",
        titel: "Rapporter",
        sida: "bokslut",
        lasvy: false,
      },
      {
        key: "bokslut.atgarder",
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

export function vyIndex(sida: Sidnyckel, key: ViewKey): number {
  return sidan(sida).vyer.findIndex((v) => v.key === key);
}

/** view_key härleds ur kartan, aldrig ur en sträng som klistras ihop. */
export function viewKeyOf(sida: Sidnyckel, index: number): ViewKey | undefined {
  return vyAt(sida, index)?.key;
}

export function allaVyer(): readonly Vy[] {
  return SIDOR.flatMap((s) => s.vyer);
}
