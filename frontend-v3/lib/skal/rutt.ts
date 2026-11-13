/**
 * Rutt och flagga för skalet (modul `skal`).
 *
 * Hela skalet är EN rutt, `/`, med två sökparametrar: ?sida=&vy=.
 * Skälet är scroll-snap: vyn är ett skrolläge, sidan är en navigering.
 * Ett svep får inte kosta en post i historiken.
 */

import type { Detalj } from "@/lib/skal/detalj";
import {
  type Sidnyckel,
  type Vy,
  arSidnyckel,
  forstaVyn,
  vyMedSlug,
} from "@/lib/skal/vyer";

export const SKAL_RUTT = "/";

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
 * tyst skapar en tråd ingen hittar tillbaka till.
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
 * Detaljlagret i URL:en: `&konto=1930` eller `&ver=<id>`.
 * Ett värde som inte går att läsa ger inget lager — länken landar då i vyn,
 * inte i ett fel.
 */
export function lasDetalj(
  konto?: string | null,
  ver?: string | null
): Detalj | null {
  if (konto && /^\d{1,10}$/.test(konto)) return { typ: "konto", kod: konto };
  if (ver && ver.trim() !== "") return { typ: "ver", id: ver };
  return null;
}

export function positionsUrl(sida: Sidnyckel, vy: Vy, detalj?: Detalj | null): string {
  const bas = `${SKAL_RUTT}?sida=${sida}&vy=${vy.slug}`;
  if (!detalj) return bas;
  if (detalj.typ === "konto") return `${bas}&konto=${encodeURIComponent(detalj.kod)}`;
  return `${bas}&ver=${encodeURIComponent(detalj.id)}`;
}
