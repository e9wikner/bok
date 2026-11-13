"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { VyBanner } from "@/components/skal/VyBanner";
import { VyHeaderStatus } from "@/components/skal/VyHeaderStatus";
import { VyRadSkelett } from "@/components/skal/VyRad";
import { VySektion } from "@/components/skal/VySektion";
import {
  KONTOPLAN_NYCKEL,
  type Konto,
  kontoMeta,
  kontoklasser,
  kontoplanApi,
  kontoplanStatus,
} from "@/lib/skal/kontoplan";
import { lageFarg } from "@/lib/skal/lage";

/**
 * Kontoplanen (`bocker.kontoplan`): BAS-kontona per kontoklass. Ingen egen
 * tråd — den chattar i Verifikationers, där kontona används.
 */
export function KontoplanVy({ titel, variant }: { titel: string; variant: "desktop" | "mobil" }) {
  const { data, isError } = useQuery({
    queryKey: KONTOPLAN_NYCKEL,
    queryFn: kontoplanApi.lista,
    staleTime: 10 * 60 * 1000,
  });
  const [sok, setSok] = useState("");
  const status = kontoplanStatus(data, isError);
  const pad = variant === "desktop" ? "px-6" : "px-[18px]";
  const klasser = data ? kontoklasser(data, sok) : [];

  return (
    <div
      className={
        variant === "desktop"
          ? "flex min-h-0 flex-col bg-bok-yta"
          : "bok-dold-skroll flex min-h-0 flex-1 flex-col overflow-auto"
      }
    >
      <VyHeaderStatus titel={titel} status={status.text} fg={lageFarg(status.lage)} variant={variant} />

      <div
        className={
          variant === "desktop"
            ? `bok-dold-skroll flex min-h-0 flex-1 flex-col overflow-auto pb-[136px] pt-1 ${pad}`
            : `flex flex-col bok-mobil-botten ${pad}`
        }
      >
        <div className="pt-[14px]">
          <input
            type="search"
            value={sok}
            onChange={(e) => setSok(e.target.value)}
            placeholder="Sök på nummer eller namn"
            aria-label="Sök konto"
            className="bok-mono w-full rounded-md border border-bok-linje bg-bok-yta px-3 py-[7px] text-[13px] text-bok-text placeholder:text-bok-meta focus:border-bok-lank focus:outline-none"
          />
        </div>

        {isError ? (
          <div className="mt-[14px]">
            <VyBanner ton="fel" text="Kontoplanen kunde inte läsas. Ladda om sidan." />
          </div>
        ) : !data ? (
          <div className="pt-5">
            <VyRadSkelett />
          </div>
        ) : klasser.length === 0 ? (
          <div className="bok-mono pt-5 text-[12px] text-bok-meta">Inget konto matchar ”{sok.trim()}”.</div>
        ) : (
          klasser.map((g) => (
            <VySektion key={g.klass} titel={`${g.klass} · ${g.titel}`} antalRader={g.konton.length} variant={variant}>
              {g.konton.map((k) => (
                <KontoRad key={k.code} k={k} />
              ))}
            </VySektion>
          ))
        )}

        <div className="pt-5 text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">
          Ett konto som saknas läggs till av agenten eller kommer med en SIE4-import.
        </div>
      </div>
    </div>
  );
}

function KontoRad({ k }: { k: Konto }) {
  const meta = kontoMeta(k);
  return (
    <div data-testid="konto" className="flex items-baseline gap-3 border-b border-bok-linje-svagast py-[7px]">
      <span className="bok-mono bok-tal w-[44px] shrink-0 text-[13px] text-bok-text">{k.code}</span>
      <span className="min-w-0 flex-1 text-[14px] leading-[1.35] text-bok-text">{k.name}</span>
      {meta && <span className="bok-mono shrink-0 text-right text-[11px] text-bok-meta">{meta}</span>}
    </div>
  );
}
