/**
 * Rutt och flagga för skalet (modul `skal`).
 *
 * Hela skalet är EN rutt, `/v4`, med två sökparametrar: ?sida=&vy=.
 * Skälet är scroll-snap: vyn är ett skrolläge, sidan är en navigering.
 * Ett svep får inte kosta en post i historiken. SPEC-skal.md §4.
 */

import type { Detalj } from "@/lib/skal/detalj";
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

/**
 * Detaljlagret i URL:en: `&konto=1930` eller `&ver=<id>`. Ett värde som
 * inte går att läsa ger inget lager — länken landar då i vyn, inte i ett fel.
 */
export function lasDetalj(konto?: string | null, ver?: string | null): Detalj | null {
  if (konto && /^\d{1,10}$/.test(konto)) return { typ: "konto", kod: konto };
  if (ver && ver.trim() !== "") return { typ: "ver", id: ver };
  return null;
}

export function positionsUrl(sida: Sidnyckel, vy: Vy, detalj?: Detalj | null): string {
  const bas = `${SKAL_RUTT}?sida=${sida}&vy=${vy.slug}`;
  if (!detalj) return bas;
  return detalj.typ === "konto"
    ? `${bas}&konto=${encodeURIComponent(detalj.kod)}`
    : `${bas}&ver=${encodeURIComponent(detalj.id)}`;
}
