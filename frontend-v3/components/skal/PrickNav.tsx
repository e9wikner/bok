"use client";

import type { Vy } from "@/lib/skal/vyer";

/**
 * `PrickNav` (komponenter.md): vyer inom sidan.
 *
 * Prickar 7 px, aktiv 20×7, radius 999, aktiv #0a0f1a, inaktiv #d4d4d8,
 * gap 9, i en pillerram. Riktiga knappar med aria-label för vyns namn —
 * README.md §Tillgänglighet kräver det, och svepet måste ha en
 * tangentbordsekvivalent (piltangenterna bor i `VySvep`).
 *
 * Pricken är 7 px hög VISUELLT men knappen har träffyta 44 via padding.
 * En större prick hade brutit designen; en mindre träffyta hade brutit
 * tillgängligheten.
 */
export function PrickNav({
  vyer,
  aktivIndex,
  onValj,
  storlek = "desktop",
}: {
  vyer: readonly Vy[];
  aktivIndex: number;
  onValj: (index: number) => void;
  storlek?: "desktop" | "mobil";
}) {
  return (
    <div
      className={`flex items-center rounded-full border border-bok-linje ${
        storlek === "desktop" ? "gap-[9px] px-3 py-2" : "gap-[7px] px-[10px] py-[7px]"
      }`}
    >
      {vyer.map((vy, i) => {
        const aktiv = i === aktivIndex;
        return (
          <button
            key={vy.key}
            type="button"
            aria-label={vy.titel}
            aria-current={aktiv ? "true" : undefined}
            onClick={() => onValj(i)}
            className="group flex items-center justify-center"
            // Träffytan är 44 hög; pricken inuti är 7. Padding, inte storlek.
            style={{ height: 44, paddingLeft: 2, paddingRight: 2, marginTop: -18, marginBottom: -18 }}
          >
            <span
              aria-hidden="true"
              className="block rounded-full transition-[width,background-color] duration-150"
              style={{
                width: aktiv ? 20 : 7,
                height: 7,
                background: aktiv ? "var(--bok-black)" : "var(--bok-kant)",
              }}
            />
          </button>
        );
      })}
    </div>
  );
}
