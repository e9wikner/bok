"use client";

import { ChattFalt } from "@/components/skal/ChattFalt";
import type { TradInlaggData } from "@/lib/skal/mock";

/**
 * Chattkolumnen som SKAL.
 *
 * Tråden är padding 26/38, gap 24 och BOTTENANKRAD (justify-content:
 * flex-end) så att det senaste ligger vid inmatningsfältet. Textrader max
 * 54ch, kort max-bredd 560.
 *
 * Renderaren nedan kan två typer: agenttext och egen replik. Korten —
 * `BeslutKort`, `AlternativLista`, `VerifikationsForslag`, `FelKort`,
 * `JamforelseRader` — byggs INTE här. De är `chattyta` och bär kontrakt som
 * skalet inte äger: ingen förvald rekommendation, alltid en väg ut, alltid
 * båda talen. Ett halvfärdigt kort som redan ser rätt ut är värre än inget.
 * SPEC-skal.md §13.
 */
export function ChattKolumn({
  vyTitel,
  inlagg,
  variant = "desktop",
}: {
  vyTitel: string;
  inlagg: TradInlaggData[];
  variant?: "desktop" | "mobil";
}) {
  const trad = (
    <div
      className={
        variant === "desktop"
          ? "flex flex-1 flex-col justify-end gap-6 overflow-hidden px-[38px] py-[26px]"
          : "bok-dold-skroll flex h-[260px] flex-col gap-[18px] overflow-auto border-t border-bok-linje-svagast px-[18px] pb-[18px] pt-4"
      }
      // Strömmande svar och postningar annonseras, inte bara som grå rader.
      aria-live="polite"
      aria-label={`Tråd för ${vyTitel}`}
    >
      {inlagg.map((m) =>
        m.typ === "agent_text" ? (
          <div key={m.id} className="flex flex-col gap-[13px]">
            <span className="bok-etikett text-[11px] text-bok-meta">{m.meta}</span>
            <p className="m-0 max-w-[54ch] text-[15px] leading-[1.6] [text-wrap:pretty]">{m.text}</p>
          </div>
        ) : (
          <div key={m.id} className="flex justify-end">
            <div className="max-w-[74%] rounded-[14px_14px_4px_14px] bg-bok-bubbla px-4 py-3 text-[15px] leading-[1.55] [text-wrap:pretty]">
              {m.text}
            </div>
          </div>
        )
      )}
    </div>
  );

  if (variant === "mobil") return trad;

  return (
    <div className="flex min-h-0 flex-col border-r border-bok-linje">
      {trad}
      <ChattFalt vyTitel={vyTitel} />
    </div>
  );
}
