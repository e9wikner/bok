/**
 * Talformat för skalet (modul `skal`).
 *
 * Designen (design_handoff_bokai/README.md §Typografi) kräver:
 *   - mellanslag som tusentalsavgränsare
 *   - minustecken − (U+2212), inte bindestreck
 *   - tabulära siffror (klassen `bok-tal`)
 *   - inget valutasuffix i vyraderna
 *
 * `lib/utils.ts::formatCurrency` gör något annat (Intl med style: "currency",
 * alltså "−400 720,00 kr") och anropas av 24 befintliga sidor. Den rörs inte.
 * SPEC-skal.md §7.
 */

const MINUS = "−"; // U+2212 MINUS SIGN

function medDesignensTecken(s: string): string {
  // Intl sv-SE ger U+2212 i moderna runtime:er men U+002D i äldre.
  // Normalisera, så att utdata inte beror på ICU-versionen.
  return s.replace(/^-/, MINUS);
}

/** Belopp i öre → "400 720,00". Aldrig med valutasuffix. */
export function formatBelopp(beloppIOre: number, decimaler = 2): string {
  const s = new Intl.NumberFormat("sv-SE", {
    minimumFractionDigits: decimaler,
    maximumFractionDigits: decimaler,
    useGrouping: true,
  }).format(beloppIOre / 100);
  return medDesignensTecken(s);
}

/** Belopp i öre → "400 720". Vyraderna visar hela kronor. */
export function formatBeloppHela(beloppIOre: number): string {
  return formatBelopp(Math.round(beloppIOre / 100) * 100, 0);
}

export const MINUSTECKEN = MINUS;
