"use client";

import { LasKnapp } from "@/components/skal/LasKnapp";
import type { LasData } from "@/lib/skal/las";

/** En beloppskolumns bredd, samma i rubriken och i raden (`VyRad`). */
export const KOLUMN_BREDD = "w-[124px]";

/**
 * `VySektion`: rubriken är en rubrik — sans 16 (mobil 17), medelvikt, full
 * textfärg och en linje under — så att den bär listan även på mobilen. Den
 * versala monoetiketten (10, metafärg) försvann mot raderna. Kolumnernas
 * rubriker står kvar i mono, på samma rad.
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
  kolumner,
}: {
  titel: string;
  children: React.ReactNode;
  antalRader: number;
  variant?: "desktop" | "mobil";
  /** Sektionens lås, till höger i rubrikraden. */
  las?: LasData;
  /** Texten som står i stället för rader när sektionen är tom. */
  tom?: string;
  /**
   * Beloppskolumnernas rubriker, i linje med radernas kolumner. Mobilen har
   * bara högerkolumnen, så där står bara den sista.
   */
  kolumner?: string[];
}) {
  if (antalRader === 0 && !tom) return null;
  const desktop = variant === "desktop";

  return (
    <div className="flex flex-col">
      <div
        data-testid="vysektion-rubrik"
        className={`flex items-end justify-between gap-[14px] border-b border-bok-kant pb-[6px] ${
          desktop ? "pt-6" : "pt-[22px]"
        }`}
      >
        <h3 className={`min-w-0 font-medium leading-tight text-bok-text ${desktop ? "text-[16px]" : "text-[17px]"}`}>
          {titel}
        </h3>
        {kolumner && desktop && (
          <span className="flex shrink-0">
            {kolumner.map((k) => (
              <KolumnRubrik key={k} text={k} />
            ))}
          </span>
        )}
        {kolumner && !desktop && <KolumnRubrik text={kolumner[kolumner.length - 1]} bredd="" />}
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

function KolumnRubrik({ text, bredd = KOLUMN_BREDD }: { text: string; bredd?: string }) {
  return <span className={`bok-mono shrink-0 text-right text-[11px] text-bok-text-svag ${bredd}`}>{text}</span>;
}

/**
 * En grupp inom sektionen (Kassa och bank, Personalkostnader): en
 * mellanrubrik, tydlig men ett steg under sektionens.
 */
export function VyGrupp({ titel, variant = "desktop" }: { titel: string; variant?: "desktop" | "mobil" }) {
  return (
    <div
      data-testid="vygrupp"
      className={`pb-[2px] font-medium text-bok-text-dampad ${
        variant === "desktop" ? "pt-3 text-[12px]" : "pt-[14px] text-[13px]"
      }`}
    >
      {titel}
    </div>
  );
}
