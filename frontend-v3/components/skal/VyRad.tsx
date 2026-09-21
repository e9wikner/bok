"use client";

import { useEffect, useState } from "react";
import type { RadVariant } from "@/lib/skal/mock";

/**
 * `VyRad` (komponenter.md): padding 9/8, margin 0 -8, radius 6,
 * border-bottom 1px #f4f4f5. Vänster titel 14 + metarad mono 11.
 * Höger mono 14 tabular.
 *
 * OBS namnkrock: det här är EN RAD I VYN. Raden AV VYER heter `VySvep`.
 * Mappningen står i SPEC-skal.md §6.
 */

/**
 * `ny`-markeringen är kortvarig. Annars färgas listan grön över tiden och
 * grönt slutar betyda "postat och låst" — en av de två toner som bär
 * betydelse. Varaktigheten står på ETT ställe.
 *
 * Talet självt är inte taget: designen säger "kortvarig" och inget mer
 * (SPEC-skal.md öppen fråga 3).
 */
export const NY_MARKERING_MS = 6000;

const META_FARG: Record<RadVariant, string> = {
  normal: "var(--bok-meta)",
  saknar: "var(--bok-vantar-meta)",
  vantar: "var(--bok-vantar-meta)",
  pagaende: "var(--bok-meta)",
  ny: "var(--bok-klart-meta)",
  fel: "var(--bok-fel-meta)",
  paverkad: "var(--bok-vantar-meta)",
};

export function VyRad({
  titel,
  meta,
  hoger,
  variant = "normal",
  summa = false,
  storlek = "desktop",
}: {
  titel: string;
  meta?: string;
  hoger: string;
  variant?: RadVariant;
  summa?: boolean;
  storlek?: "desktop" | "mobil";
}) {
  // Markeringen tas bort av sig själv; raden ligger kvar.
  const [nyAktiv, setNyAktiv] = useState(variant === "ny");
  useEffect(() => {
    if (variant !== "ny") return;
    setNyAktiv(true);
    const t = setTimeout(() => setNyAktiv(false), NY_MARKERING_MS);
    return () => clearTimeout(t);
  }, [variant]);

  const pagaende = variant === "pagaende";
  const yta = nyAktiv ? "var(--bok-klart-yta)" : pagaende ? "var(--bok-yta-svag)" : undefined;
  const textFarg = pagaende ? "var(--bok-meta)" : undefined;

  return (
    <div
      data-variant={variant}
      data-ny={nyAktiv ? "true" : undefined}
      className={`flex items-baseline justify-between gap-[14px] border-b border-bok-linje-svagast ${
        storlek === "desktop" ? "-mx-2 rounded-md px-2 py-[9px]" : "py-[11px]"
      }`}
      style={{ background: yta }}
    >
      <span className="flex min-w-0 flex-col gap-[2px]">
        <span
          className={storlek === "desktop" ? "text-[14px]" : "text-[15px]"}
          style={{ color: textFarg, fontWeight: summa ? 500 : undefined }}
        >
          {titel}
        </span>
        {meta && (
          <span
            className={`bok-mono ${storlek === "desktop" ? "text-[11px]" : "text-[12px]"}`}
            style={{ color: META_FARG[variant] }}
          >
            {meta}
          </span>
        )}
      </span>
      <span
        className={`bok-mono bok-tal whitespace-nowrap ${
          storlek === "desktop" ? "text-[14px]" : "text-[15px]"
        }`}
        style={{ color: textFarg, fontWeight: summa ? 500 : undefined }}
      >
        {hoger}
      </span>
    </div>
  );
}

/**
 * Laddning är skelettrader med SAMMA radhöjd, aldrig en spinner över hela
 * ytan (README.md §Tillstånd). Samma höjd gör att listan inte hoppar när
 * data landar.
 */
export function VyRadSkelett({ antal = 4 }: { antal?: number }) {
  return (
    <div aria-hidden="true" data-testid="vyrad-skelett">
      {Array.from({ length: antal }).map((_, i) => (
        <div
          key={i}
          className="-mx-2 flex items-baseline justify-between gap-[14px] border-b border-bok-linje-svagast px-2 py-[9px]"
        >
          <span className="flex min-w-0 flex-col gap-[2px]">
            <span className="block h-[14px] w-[160px] rounded bg-bok-linje-svagast" />
            <span className="block h-[11px] w-[90px] rounded bg-bok-linje-svagast" />
          </span>
          <span className="block h-[14px] w-[70px] rounded bg-bok-linje-svagast" />
        </div>
      ))}
    </div>
  );
}
