/**
 * Rutt och flagga för skalet (modul `skal`).
 *
 * Hela skalet är EN rutt, `/v4`, med två sökparametrar: ?sida=&vy=.
 * Skälet är scroll-snap: vyn är ett skrolläge, sidan är en navigering.
 * Ett svep får inte kosta en post i historiken. SPEC-skal.md §4.
 */

import {
  type Sidnyckel,
  type Vy,
  arSidnyckel,
  forstaVyn,
  vyMedSlug,
} from "@/lib/skal/vyer";

export const SKAL_RUTT = "/v4";

/**
 * Flaggan är en byggtidsvariabel, inte en växel i gränssnittet. Saknas den
 * svarar /v4 med notFound(). ANALYS.md §7 ber om en flagga för att kunna
 * bygga vidare utan att störa drift — inte om en A/B-mekanism.
 */
export function skalArPa(varde: string | undefined = process.env.NEXT_PUBLIC_SKAL): boolean {
  return varde === "1" || varde === "true";
}

export interface Position {
  sida: Sidnyckel;
  vy: Vy;
}

/**
 * Läser ?sida=&vy= och faller tillbaka på `bocker` respektive sidans första
 * vy vid okänt värde.
 *
 * Asymmetrin mot servern är avsiktlig: en trasig länk ska landa någonstans,
 * medan en okänd view_key mot servern ger 404 så att en trasig klient inte
 * tyst skapar en tråd ingen hittar tillbaka till (SPEC-tradar.md §5).
 */
export function lasPosition(
  sidaParam?: string | null,
  vyParam?: string | null
): Position {
  const sida: Sidnyckel = arSidnyckel(sidaParam) ? sidaParam : "bocker";
  const vy = vyMedSlug(sida, vyParam) ?? forstaVyn(sida);
  return { sida, vy };
}

export function positionsUrl(sida: Sidnyckel, vy: Vy): string {
  return `${SKAL_RUTT}?sida=${sida}&vy=${vy.slug}`;
}
