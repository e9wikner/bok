"use client";

import { useEffect, useRef, useState } from "react";
import { SIDOR, type Sidnyckel } from "@/lib/skal/vyer";

/**
 * `SidVaeljare` (komponenter.md): sidtiteln ÄR knappen.
 *
 * `SidTabbar` byggs inte. Omgång 10 har väljaren på båda breddarna, och
 * kapabilitetskartan (ANALYS.md §8) räknar upp `SidVaeljare` men inte
 * tabbarna. Se SPEC-skal.md §2.2 — beslutet togs en gång, där.
 *
 * Tabbens informationsinnehåll finns kvar i väljaren: väntar-pricken och
 * sidans metarad, i samma färger.
 */

export interface SidMeta {
  waiting: boolean;
  meta: string;
}

export function SidVaeljare({
  aktiv,
  metaPerSida,
  onValj,
  variant,
}: {
  aktiv: Sidnyckel;
  /** Serverns `waiting`/`meta` per sida. Klienten räknar ingenting. */
  metaPerSida: Partial<Record<Sidnyckel, SidMeta>>;
  onValj: (sida: Sidnyckel) => void;
  variant: "desktop" | "mobil";
}) {
  const [oppen, setOppen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!oppen) return;
    const vidTangent = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOppen(false);
    };
    document.addEventListener("keydown", vidTangent);
    return () => document.removeEventListener("keydown", vidTangent);
  }, [oppen]);

  const aktivSida = SIDOR.find((s) => s.key === aktiv)!;
  const aktivMeta = metaPerSida[aktiv];

  const valj = (sida: Sidnyckel) => {
    setOppen(false);
    onValj(sida);
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={oppen}
        aria-label="Välj sida"
        onClick={() => setOppen((v) => !v)}
        className={
          variant === "desktop"
            ? "flex min-h-[44px] items-center gap-4 rounded-[10px] border border-bok-kant bg-bok-yta px-[14px] py-[6px] text-left hover:bg-bok-yta-svag"
            : "flex min-h-[44px] min-w-0 flex-1 items-center gap-2 rounded-[10px] px-2 text-left"
        }
      >
        <span className="flex min-w-0 flex-col gap-px">
          {variant === "desktop" && (
            <span className="bok-etikett text-[10px] text-bok-meta">Sida</span>
          )}
          <span className="truncate text-[15px] font-medium text-bok-text">{aktivSida.titel}</span>
          <span
            className={`bok-mono truncate text-[11px] ${
              aktivMeta?.waiting ? "text-bok-vantar-meta" : "text-bok-meta"
            }`}
          >
            {aktivMeta?.meta ?? ""}
          </span>
        </span>
        <span aria-hidden="true" className="shrink-0 text-[10px] text-bok-text-svag">
          {oppen ? "▲" : "▼"}
        </span>
      </button>

      {oppen && (
        <>
          {/* Klick utanför stänger. På mobilen är det dessutom ett överlägg. */}
          <div
            data-testid="sidvaljare-utanfor"
            onClick={() => setOppen(false)}
            className="fixed inset-0 z-[1]"
            style={variant === "mobil" ? { background: "rgba(10,15,26,0.28)" } : undefined}
          />
          <div
            role="menu"
            aria-label="Sidor"
            className={
              variant === "desktop"
                ? "absolute left-0 top-[52px] z-[2] flex w-[430px] flex-col gap-[2px] rounded-[12px] border border-bok-kant bg-bok-yta p-[6px] shadow-bok-meny"
                : "fixed left-2 right-2 top-[56px] z-[2] flex flex-col gap-[2px] rounded-b-[14px] border border-bok-kant bg-bok-yta p-[6px] shadow-bok-meny"
            }
          >
            {SIDOR.map((sida) => {
              const m = metaPerSida[sida.key];
              const arAktiv = sida.key === aktiv;
              return (
                <button
                  key={sida.key}
                  type="button"
                  role="menuitem"
                  onClick={() => valj(sida.key)}
                  className={`flex items-center justify-between gap-3 rounded-lg px-3 py-[9px] text-left hover:bg-bok-linje-svagast ${
                    variant === "mobil" ? "min-h-[52px]" : "min-h-[44px]"
                  } ${arAktiv ? "bg-bok-linje-svagast" : ""}`}
                >
                  <span className="flex min-w-0 flex-col gap-[2px]">
                    <span className="truncate text-[15px] text-bok-text">{sida.titel}</span>
                    <span
                      className={`bok-mono truncate text-[11px] ${
                        m?.waiting ? "text-bok-vantar-meta" : "text-bok-meta"
                      }`}
                    >
                      {m?.meta ?? ""}
                    </span>
                  </span>
                  <span className="bok-mono shrink-0 text-[12px] text-bok-text">
                    {arAktiv ? "✓" : ""}
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
