"use client";

import Link from "next/link";
import type { SidMeta } from "@/components/skal/SidVaeljare";
import type { OverviewAnnatAr } from "@/lib/skal/api";
import { SIDOR, type Sidnyckel, type ViewKey, type Vynyckel } from "@/lib/skal/vyer";

/**
 * Sidonavigeringen på desktop: alla sidor och deras vyer som flikar i en
 * vänsterkolumn, i stället för sidväljarens utfällbara lista.
 *
 * Varje vy är ett eget tryck, så att man når Verifikationer eller Löner
 * direkt utan att först byta sida och sedan svepa. Sidornas rubrik bär
 * serverns metarad (väntar-färgen) — samma fält som väljaren visade.
 * Mobilen behåller `SidVaeljare`: där finns inte plats för en kolumn.
 *
 * Varje flik där något väntar bär antalet (serverns, per vy och valt år), så
 * att det syns vilken flik sidans rad gäller. Bokslutets kontroller står som
 * en rad under vyn där de åtgärdas (Uppgifter, INK2 …), inte under sidan;
 * då upprepar sidans rubrik dem inte. Väntar något i ett annat
 * räkenskapsår står det överst, som en knapp som byter till det året.
 */
export function SidNav({
  aktivVy,
  metaPerSida,
  antalPerVy = {},
  metaPerVy = {},
  andraAr = [],
  onValjVy,
  onValjAr,
}: {
  aktivVy: Vynyckel;
  metaPerSida: Partial<Record<Sidnyckel, SidMeta>>;
  /** Serverns antal som väntar per vy, i året som visas. */
  antalPerVy?: Partial<Record<ViewKey, number>>;
  /** Serverns rad under en vy: bokslutets kontroller som är kvar där. */
  metaPerVy?: Partial<Record<Vynyckel, SidMeta>>;
  /** Andra räkenskapsår där något väntar (serverns `other_years`). */
  andraAr?: OverviewAnnatAr[];
  onValjVy: (key: Vynyckel) => void;
  onValjAr?: (id: string) => void;
}) {
  return (
    <nav
      aria-label="Sidor och vyer"
      className="bok-dold-skroll flex w-[232px] shrink-0 flex-col gap-5 overflow-y-auto border-r border-bok-linje bg-bok-yta px-3 py-5"
    >
      {andraAr.length > 0 && (
        <div className="flex flex-col gap-[2px]">
          {andraAr.map((ar) => (
            <button
              key={ar.id}
              type="button"
              data-testid={`sidnav-annat-ar-${ar.id}`}
              onClick={() => onValjAr?.(ar.id)}
              className="flex flex-col items-start gap-[2px] rounded-lg border px-3 py-2 text-left"
              style={{
                background: "var(--bok-vantar-yta)",
                borderColor: "var(--bok-vantar-kant)",
              }}
            >
              <span className="text-[13px] font-medium text-bok-text">Räkenskapsår {ar.label}</span>
              <span className="bok-mono text-[11px]" style={{ color: "var(--bok-vantar-meta)" }}>
                {ar.meta} · byt år →
              </span>
            </button>
          ))}
        </div>
      )}
      {SIDOR.map((sida) => {
        const m = metaPerSida[sida.key];
        const vyernaHarRader = sida.vyer.some((vy) => metaPerVy[vy.key]?.meta);
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
              {m?.meta && !vyernaHarRader && (
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
              // Antalet är trådens; en bokslutsdel som delar Rapporters tråd
              // bär det inte, bara vyn som äger tråden.
              const antal = vy.key === vy.trad ? (antalPerVy[vy.trad] ?? 0) : 0;
              const rad = metaPerVy[vy.key];
              return (
                <button
                  key={vy.key}
                  type="button"
                  aria-current={aktiv ? "page" : undefined}
                  onClick={() => onValjVy(vy.key)}
                  aria-label={
                    antal > 0
                      ? [vy.titel, `${antal} väntar på dig`, rad?.meta].filter(Boolean).join(", ")
                      : undefined
                  }
                  className={`flex min-h-[36px] items-center justify-between gap-2 rounded-lg px-3 text-left text-[14px] transition-colors ${
                    aktiv
                      ? "bg-bok-linje-svagast font-medium text-bok-text"
                      : "text-bok-text-2 hover:bg-bok-yta-svag hover:text-bok-text"
                  }`}
                >
                  <span className="flex min-w-0 flex-col py-[6px]">
                    <span className="truncate">{vy.titel}</span>
                    {rad?.meta && (
                      <span
                        data-testid={`sidnav-rad-${vy.key}`}
                        className={`bok-mono truncate text-[11px] font-normal ${
                          rad.waiting ? "text-bok-vantar-meta" : "text-bok-meta"
                        }`}
                        title={rad.meta}
                      >
                        {rad.meta}
                      </span>
                    )}
                  </span>
                  {antal > 0 && (
                    <span
                      data-testid={`sidnav-antal-${vy.key}`}
                      aria-hidden="true"
                      className="bok-mono flex h-[20px] min-w-[20px] shrink-0 items-center justify-center rounded-full border px-[6px] text-[11px]"
                      style={{
                        color: "var(--bok-vantar-meta)",
                        background: "var(--bok-vantar-yta)",
                        borderColor: "var(--bok-vantar-kant)",
                      }}
                    >
                      {antal}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        );
      })}
      {/* Det som ännu bara finns på de gamla sidorna (oppna-beslut, Städning):
          företagets uppgifter, kontoplanen och revisionsspåret. */}
      <div className="mt-auto flex flex-col gap-[2px] border-t border-bok-linje-svag pt-4">
        <span className="bok-etikett px-3 pb-[6px] text-[10px] text-bok-meta">Fler sidor</span>
        {FLER_SIDOR.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className="flex min-h-[32px] items-center rounded-lg px-3 text-[13px] text-bok-text-2 transition-colors hover:bg-bok-yta-svag hover:text-bok-text"
          >
            {l.titel}
          </Link>
        ))}
      </div>
    </nav>
  );
}

const FLER_SIDOR = [
  { href: "/settings", titel: "Inställningar" },
  { href: "/accounts", titel: "Kontoplan" },
  { href: "/audit", titel: "Revisionslogg" },
  { href: "/", titel: "Klassiska vyn" },
] as const;
