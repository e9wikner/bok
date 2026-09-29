"use client";

import { LasKnapp } from "@/components/skal/LasKnapp";
import type { LasData } from "@/lib/skal/las";

/**
 * `VySektion` (komponenter.md): rubrik mono 10 versalt, padding 20/0/6.
 *
 * "Tom sektion visas inte alls." Det är en regel, inte en stil: en rubrik
 * utan rader är en lögn om att något saknas. Tomt läge i README.md
 * §Tillstånd säger samma sak — "sektionen utgår helt, inte tom rubrik".
 * Undantaget är en sektion som säger vad tomheten betyder (`tom`), som en
 * månad utan verifikationer som ändå kan låsas.
 */
export function VySektion({
  titel,
  children,
  antalRader,
  variant = "desktop",
  las,
  tom,
}: {
  titel: string;
  children: React.ReactNode;
  antalRader: number;
  variant?: "desktop" | "mobil";
  /** Sektionens lås, till höger i rubrikraden. */
  las?: LasData;
  /** Texten som står i stället för rader när sektionen är tom. */
  tom?: string;
}) {
  if (antalRader === 0 && !tom) return null;

  return (
    <div className="flex flex-col">
      <div
        className={`flex items-center justify-between gap-[14px] ${
          variant === "desktop" ? "pb-[6px] pt-5" : "pb-[6px] pt-[18px]"
        }`}
      >
        <span className="bok-etikett text-[10px] text-bok-meta">{titel}</span>
        {las && <LasKnapp {...las} />}
      </div>
      {antalRader === 0 ? (
        <div className="bok-mono border-b border-bok-linje-svagast py-[9px] text-[11px] text-bok-meta">
          {tom}
        </div>
      ) : (
        children
      )}
    </div>
  );
}
