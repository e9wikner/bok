"use client";

import { useEffect, useRef } from "react";
import { VyBanner } from "@/components/skal/VyBanner";
import { VyHeaderStatus } from "@/components/skal/VyHeaderStatus";
import { VyRad, VyRadSkelett } from "@/components/skal/VyRad";
import { VySektion } from "@/components/skal/VySektion";
import { lageFarg } from "@/lib/skal/lage";
import type { VyData } from "@/lib/skal/vydata";
import type { Vy } from "@/lib/skal/vyer";

/**
 * Läskolumnen: rubrikrad, period, eventuell banner, sektioner med rader och
 * en fottext som säger vad agenten gör härnäst.
 *
 * Fakturering och Löner är LÄSVYER UTAN SKRIVFLÖDE (SPEC-skal.md §11).
 * De får ingen primärknapp i foten — och ingen avstängd knapp och ingen
 * "kommer snart"-text heller. En yta som lovar en funktion som inte finns
 * är sämre än en yta som inte lovar den. Skrivning sker tills vidare via
 * /invoices och /payroll, som står kvar enligt §3.
 */
export function VyInnehall({
  vy,
  data,
  laddar = false,
  variant = "desktop",
}: {
  vy: Vy;
  data: VyData;
  laddar?: boolean;
  variant?: "desktop" | "mobil";
}) {
  const fg = lageFarg(data.lage);

  return (
    <div
      className={
        variant === "desktop"
          ? "flex min-h-0 flex-col bg-bok-yta"
          : "bok-dold-skroll flex min-h-0 flex-1 flex-col overflow-auto"
      }
    >
      <VyHeaderStatus titel={vy.titel} status={data.status} fg={fg} variant={variant} />

      <div
        className={
          variant === "desktop"
            ? "bok-dold-skroll flex min-h-0 flex-1 flex-col overflow-auto px-6 pb-[18px] pt-1"
            : "flex flex-col px-[18px] pb-5"
        }
      >
        <div className="bok-mono pt-[14px] text-[12px] text-bok-meta">{data.period}</div>

        {data.banner && (
          <div className="mt-[14px]">
            <VyBanner ton={data.banner.ton} text={data.banner.text} />
          </div>
        )}

        {laddar ? (
          <div className="pt-5">
            <VyRadSkelett />
          </div>
        ) : (
          data.sektioner.map((sektion) => (
            <VySektion
              key={sektion.titel}
              titel={sektion.titel}
              antalRader={sektion.rader.length}
              variant={variant}
              las={sektion.las}
              tom={sektion.tom}
            >
              {sektion.rader.map((rad) => (
                <VyRad
                  key={rad.id}
                  titel={rad.titel}
                  meta={rad.meta}
                  hoger={rad.hoger}
                  variant={rad.variant}
                  summa={rad.summa}
                  ageDays={rad.ageDays}
                  kvitto={rad.kvitto}
                  las={rad.las}
                  storlek={variant}
                />
              ))}
            </VySektion>
          ))
        )}

        {!laddar && data.harFler && data.hamtaFler && <LaddarFler hamtaFler={data.hamtaFler} />}

        <div className="pt-5 text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">
          {data.fot}
        </div>
      </div>
    </div>
  );
}

/**
 * Vakten sist i listan (SPEC-lasbarhet.md §4.5): när raden syns hämtas
 * nästa sida. Observatören görs om när `hamtaFler` byts — efter varje
 * hämtad sida — så att en vakt som fortfarande syns ber om nästa.
 */
function LaddarFler({ hamtaFler }: { hamtaFler: () => void }) {
  const vakt = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = vakt.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const observator = new IntersectionObserver(
      (poster) => {
        if (poster.some((p) => p.isIntersecting)) hamtaFler();
      },
      { rootMargin: "200px 0px" }
    );
    observator.observe(el);
    return () => observator.disconnect();
  }, [hamtaFler]);

  return (
    <div ref={vakt} className="bok-mono pt-4 text-[12px] text-bok-meta" aria-live="polite">
      Laddar fler…
    </div>
  );
}
