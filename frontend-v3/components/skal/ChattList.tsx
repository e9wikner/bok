"use client";

import { useState } from "react";
import { ChattFalt } from "@/components/skal/ChattFalt";
import { ChattKolumn } from "@/components/skal/ChattKolumn";
import type { TradInlaggData } from "@/lib/skal/mock";

/**
 * `ChattList` (komponenter.md), mobilens chatt.
 *
 * Knapp min-height 50, padding 11/16: `Chatt` 14/500 + vyns namn 14 #9ca3af
 * + märke + ▼/▲. Uppfälld tråd 260 px med egen skroll, därunder `ChattFalt`.
 * box-shadow 0 -8px 20px rgba(10,15,26,0.06) skiljer listen från vyn.
 *
 * "Väntar ett beslut syns det som ett märke på listen ÄVEN NÄR CHATTEN ÄR
 * MINIMERAD." Det är hela poängen med märket — kön ligger i tråden och det
 * finns inga notiser.
 */
export function ChattList({
  vyTitel,
  inlagg,
  vantandeBeslut,
}: {
  vyTitel: string;
  inlagg: TradInlaggData[];
  vantandeBeslut: number;
}) {
  const [oppen, setOppen] = useState(true);

  const marke =
    vantandeBeslut > 0
      ? { text: `${vantandeBeslut} väntar`, vantar: true }
      : { text: `${inlagg.length} inlägg`, vantar: false };

  return (
    <div className="flex shrink-0 flex-col border-t border-bok-linje bg-bok-yta shadow-bok-chattlist">
      <button
        type="button"
        aria-label="Visa eller minimera chatten"
        aria-expanded={oppen}
        onClick={() => setOppen((v) => !v)}
        className="flex min-h-[50px] items-center gap-[10px] px-4 py-[11px] text-left"
      >
        <span className="flex min-w-0 flex-1 items-baseline gap-2">
          <span className="text-[14px] font-medium text-bok-text">Chatt</span>
          <span className="truncate text-[14px] text-bok-meta">{vyTitel}</span>
        </span>
        <span
          data-testid="chattlist-marke"
          className="bok-mono whitespace-nowrap rounded-full border px-[9px] py-[3px] text-[11px]"
          style={
            marke.vantar
              ? {
                  color: "var(--bok-vantar-meta)",
                  background: "var(--bok-vantar-yta)",
                  borderColor: "var(--bok-vantar-kant)",
                }
              : {
                  color: "var(--bok-meta)",
                  background: "transparent",
                  borderColor: "transparent",
                }
          }
        >
          {marke.text}
        </span>
        <span aria-hidden="true" className="text-[10px] text-bok-text-svag">
          {oppen ? "▼" : "▲"}
        </span>
      </button>

      {oppen && (
        <div className="flex flex-col">
          <ChattKolumn vyTitel={vyTitel} inlagg={inlagg} variant="mobil" />
          <ChattFalt vyTitel={vyTitel} variant="mobil" />
        </div>
      )}
    </div>
  );
}
