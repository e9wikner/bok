import { AgentMeta } from "@/components/chattyta/TradInlagg";
import { skriverText } from "@/lib/chattyta/etiketter";

/**
 * `SkriverIndikator` (komponenter.md §Chatten, SPEC-chattyta.md §5,
 * testfall 11): det strömmande agentinlägget innan texten kommit.
 *
 * Texten är vad agenten gör just nu — senaste `message.delta {activity}`
 * översatt med samma etiketter som spåren (`lib/chattyta/etiketter.ts`).
 * Utan activity än: `Läser…`. Aldrig tom, aldrig en anonym spinner.
 *
 * komponenter.md: metarad `AGENTEN` ovanför; tre prickar 5×5 (#a1a1aa,
 * #c4c4c8, #e0e0e4, gap 4) + text 15 #52525b.
 *
 * Ingen egen live-region: tråden har redan `aria-live`, och SPEC §11 lägger
 * annonseringen av indikatorbyten i EN dold region (C14). Två regioner
 * vore samma ord två gånger.
 */

// Tonerna är designens, avtagande från vänster. De finns inte som
// `bok-*`-tokens och används ingen annanstans, så de står här.
const PRICKAR = ["#a1a1aa", "#c4c4c8", "#e0e0e4"] as const;

export function SkriverIndikator({ activity }: { activity?: string | null }) {
  return (
    <div className="flex flex-col gap-[13px]">
      <AgentMeta />
      <div className="flex items-center gap-[10px]">
        <span data-testid="skriver-prickar" aria-hidden="true" className="flex gap-1">
          {PRICKAR.map((farg) => (
            <span key={farg} className="block h-[5px] w-[5px] rounded-full" style={{ background: farg }} />
          ))}
        </span>
        <span data-testid="skriver-text" className="text-[15px] text-bok-text-dampad">
          {skriverText(activity)}
        </span>
      </div>
    </div>
  );
}
