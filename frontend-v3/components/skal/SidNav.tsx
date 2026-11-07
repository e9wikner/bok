"use client";

import type { SidMeta } from "@/components/skal/SidVaeljare";
import { SIDOR, type Sidnyckel, type ViewKey } from "@/lib/skal/vyer";

/**
 * Sidonavigeringen på desktop: alla sidor och deras vyer som flikar i en
 * vänsterkolumn, i stället för sidväljarens utfällbara lista.
 *
 * Varje vy är ett eget tryck, så att man når Verifikationer eller Löner
 * direkt utan att först byta sida och sedan svepa. Sidornas rubrik bär
 * serverns metarad (väntar-färgen) — samma fält som väljaren visade.
 * Mobilen behåller `SidVaeljare`: där finns inte plats för en kolumn.
 */
export function SidNav({
  aktivVy,
  metaPerSida,
  onValjVy,
}: {
  aktivVy: ViewKey;
  metaPerSida: Partial<Record<Sidnyckel, SidMeta>>;
  onValjVy: (key: ViewKey) => void;
}) {
  return (
    <nav
      aria-label="Sidor och vyer"
      className="bok-dold-skroll flex w-[232px] shrink-0 flex-col gap-5 overflow-y-auto border-r border-bok-linje bg-bok-yta px-3 py-5"
    >
      {SIDOR.map((sida) => {
        const m = metaPerSida[sida.key];
        return (
          <div key={sida.key} className="flex flex-col gap-[2px]">
            <div className="flex flex-col gap-[2px] px-3 pb-[6px]">
              <span className="flex items-center gap-[6px]">
                <span className="bok-etikett text-[10px] text-bok-meta">{sida.titel}</span>
                {m?.waiting && (
                  <span
                    data-testid={`sidnav-vantar-${sida.key}`}
                    aria-hidden="true"
                    className="h-[6px] w-[6px] shrink-0 rounded-full bg-bok-vantar-prick"
                  />
                )}
              </span>
              {m?.meta && (
                <span
                  className={`bok-mono truncate text-[11px] ${
                    m.waiting ? "text-bok-vantar-meta" : "text-bok-meta"
                  }`}
                  title={m.meta}
                >
                  {m.meta}
                </span>
              )}
            </div>
            {sida.vyer.map((vy) => {
              const aktiv = vy.key === aktivVy;
              return (
                <button
                  key={vy.key}
                  type="button"
                  aria-current={aktiv ? "page" : undefined}
                  onClick={() => onValjVy(vy.key)}
                  className={`flex min-h-[36px] items-center rounded-lg px-3 text-left text-[14px] transition-colors ${
                    aktiv
                      ? "bg-bok-linje-svagast font-medium text-bok-text"
                      : "text-bok-text-2 hover:bg-bok-yta-svag hover:text-bok-text"
                  }`}
                >
                  {vy.titel}
                </button>
              );
            })}
          </div>
        );
      })}
    </nav>
  );
}
