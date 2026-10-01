/**
 * Hur gammalt ett väntande ärende får bli innan det blir rött
 * (SPEC-chattyta.md §10, §12.2).
 *
 * Två toner, inte en skala: `vantar` (bärnsten) säger "det här väntar på
 * dig", `forfallen` (rött) säger "det här har väntat för länge". Rött är
 * en av de få toner som bär betydelse, så gränsen står på ETT ställe — här —
 * och läses av både `VyRad` (`saknar`, `vantar`) och `BeslutKort`s källrad
 * (C6). Två tal på två ställen hade glidit isär.
 */

/**
 * Samma dag som beslutspåminnelsen går (SPEC-beslut.md §6.5): när agenten
 * påminner har ärendet också bytt färg, så att texten och tonen inte säger
 * olika saker. Beslutat 2026-09-23, SPEC-chattyta.md §12.2.
 */
export const ROD_FRAN_DAGAR = 7;

export type AldersTon = "vantar" | "forfallen";

/** `age_days` ur servern (`DecisionResponse.age_days`) → ton. */
export function aldersTon(ageDays: number): AldersTon {
  return ageDays >= ROD_FRAN_DAGAR ? "forfallen" : "vantar";
}
