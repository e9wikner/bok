"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useDetalj } from "@/components/skal/DetaljKontext";
import { VyBanner } from "@/components/skal/VyBanner";
import { VyHeaderStatus } from "@/components/skal/VyHeaderStatus";
import { VyRadSkelett } from "@/components/skal/VyRad";
import { lageFarg } from "@/lib/skal/lage";
import {
  type Logghandelse,
  REVISIONSLOGG_NYCKEL,
  URVAL,
  handelseMeta,
  handelseText,
  perDag,
  revisionsloggApi,
  revisionsloggStatus,
  verifikationAv,
} from "@/lib/skal/revisionslogg";

/**
 * Revisionsloggen (`installningar.revisionslogg`): behandlingshistoriken, nyast
 * först och dag för dag. Ett urval i filterraden frågar servern om bara de
 * sakerna, så att en sida alltid är full. En händelse som gäller en
 * verifikation öppnar den. Ingen egen tråd — den chattar i Verifikationers.
 */
export function RevisionsloggVy({ titel, variant }: { titel: string; variant: "desktop" | "mobil" }) {
  const [urval, setUrval] = useState(URVAL[0]);
  const { data, isError, hasNextPage, isFetchingNextPage, fetchNextPage } = useInfiniteQuery({
    queryKey: [...REVISIONSLOGG_NYCKEL, urval.key],
    queryFn: ({ pageParam }) => revisionsloggApi.sida(urval.typer, pageParam),
    initialPageParam: 0,
    getNextPageParam: (sida) => (sida.has_more ? sida.offset + sida.entries.length : undefined),
    staleTime: 30 * 1000,
  });
  const status = revisionsloggStatus(data?.pages[0], isError);
  const handelser = data?.pages.flatMap((s) => s.entries) ?? [];
  const pad = variant === "desktop" ? "px-6" : "px-[18px]";

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
        <div role="group" aria-label="Visa" className="flex flex-wrap gap-[6px] pt-[14px]">
          {URVAL.map((u) => (
            <button
              key={u.key}
              type="button"
              aria-pressed={u.key === urval.key}
              onClick={() => setUrval(u)}
              className={`bok-mono rounded-full border px-[10px] py-[3px] text-[12px] ${
                u.key === urval.key
                  ? "border-bok-text bg-bok-text text-bok-yta"
                  : "border-bok-linje text-bok-text-2 hover:bg-bok-yta-svag"
              }`}
            >
              {u.titel}
            </button>
          ))}
        </div>

        {isError ? (
          <div className="mt-[14px]">
            <VyBanner ton="fel" text="Revisionsloggen kunde inte läsas. Ladda om sidan." />
          </div>
        ) : !data ? (
          <div className="pt-5">
            <VyRadSkelett />
          </div>
        ) : handelser.length === 0 ? (
          <div className="bok-mono pt-5 text-[12px] text-bok-meta">Inga händelser.</div>
        ) : (
          <>
            {perDag(handelser).map((d) => (
              <div key={d.dag} className="flex flex-col">
                <div className="border-b border-bok-kant pb-[6px] pt-5 text-[14px] font-medium first-letter:uppercase">
                  {d.dag}
                </div>
                {d.handelser.map((h) => (
                  <Handelse key={h.id} h={h} />
                ))}
              </div>
            ))}
            {hasNextPage && (
              <button
                type="button"
                onClick={() => void fetchNextPage()}
                disabled={isFetchingNextPage}
                className="bok-mono mt-4 self-start rounded-md border border-bok-linje px-3 py-[6px] text-[12px] text-bok-text-2 hover:bg-bok-yta-svag disabled:opacity-60"
              >
                {isFetchingNextPage ? "Hämtar…" : "Visa äldre"}
              </button>
            )}
          </>
        )}

        <div className="pt-5 text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">
          Loggen skrivs av servern vid varje ändring och kan inte ändras i efterhand.
        </div>
      </div>
    </div>
  );
}

function Handelse({ h }: { h: Logghandelse }) {
  const detalj = useDetalj();
  const ver = verifikationAv(h);
  const innehall = (
    <>
      <div className="text-[14px] leading-[1.35] text-bok-text">{handelseText(h)}</div>
      <div className="bok-mono pt-[2px] text-[11px] leading-[1.45] text-bok-meta">{handelseMeta(h)}</div>
    </>
  );
  if (ver && detalj) {
    return (
      <button
        type="button"
        data-testid="logghandelse"
        onClick={() => detalj.oppna({ typ: "ver", id: ver })}
        className="-mx-2 w-[calc(100%+16px)] border-b border-bok-linje-svagast px-2 py-[7px] text-left hover:bg-bok-yta-svag"
      >
        {innehall}
      </button>
    );
  }
  return (
    <div data-testid="logghandelse" className="border-b border-bok-linje-svagast py-[7px]">
      {innehall}
    </div>
  );
}
