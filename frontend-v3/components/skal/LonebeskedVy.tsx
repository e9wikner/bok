"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Knapp, Rubrik } from "@/components/skal/Formular";
import { VyBanner } from "@/components/skal/VyBanner";
import { VyHeaderStatus } from "@/components/skal/VyHeaderStatus";
import { VyRadSkelett } from "@/components/skal/VyRad";
import { LONER_NYCKEL, oppnaFil } from "@/lib/chattyta/api";
import { felText } from "@/lib/skal/anstallda";
import { type Lonebesked, type Lonekorning, betalaApi } from "@/lib/skal/betala";
import { formatBeloppHela } from "@/lib/skal/format";
import { lageFarg } from "@/lib/skal/lage";
import {
  agiNyckel,
  beskedLage,
  kanTasBort,
  lonebeskedApi,
  lonebeskedStatus,
  manadText,
  pdfVag,
} from "@/lib/skal/lonebesked";

/**
 * Lönebesked (`betala.lonebesked`): årets lönebesked att skicka, och
 * arbetsgivardeklarationens fält per månad. Ingen egen tråd — den chattar
 * i Löners, där lönebeskeden bokförs.
 */
export function LonebeskedVy({
  titel,
  arId,
  variant,
}: {
  titel: string;
  arId: string | null | undefined;
  variant: "desktop" | "mobil";
}) {
  // Samma fråga som Löner (`useVyer`), så att en bokföring där syns här.
  const { data, isError } = useQuery({
    queryKey: [...LONER_NYCKEL, "skal", arId ?? ""],
    queryFn: () => betalaApi.getLonekorningar(arId ?? ""),
    enabled: !!arId,
    staleTime: 30 * 1000,
  });
  const korningar = data
    ? [...data.payroll_runs].sort((a, b) => b.year - a.year || b.month - a.month)
    : undefined;
  const status = lonebeskedStatus(korningar, isError, arId);
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
        {arId === null ? (
          <div className="pt-5 text-[13px] text-bok-text-svag">Det finns inget räkenskapsår.</div>
        ) : isError ? (
          <div className="mt-[14px]">
            <VyBanner ton="fel" text="Lönebeskeden kunde inte läsas. Ladda om sidan." />
          </div>
        ) : !korningar ? (
          <div className="pt-5">
            <VyRadSkelett />
          </div>
        ) : korningar.length === 0 ? (
          <div className="pt-5 text-[13px] text-bok-text-svag">
            Inga lönekörningar i året. Månadens lönebesked skapas under Anställda.
          </div>
        ) : (
          korningar.map((k) => <Korning key={k.id} k={k} />)
        )}

        <div className="pt-5 text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">
          Lönebeskeden bokförs i Löner, med ett tryck i kortet agenten lägger fram. Arbetsgivardeklarationen lämnar du i
          Skatteverkets e-tjänst; agenten bokför den när kvittensen kommer in.
        </div>
      </div>
    </div>
  );
}

function useUppdatera() {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: LONER_NYCKEL });
}

function Korning({ k }: { k: Lonekorning }) {
  const uppdatera = useUppdatera();
  const [fel, setFel] = useState<string | null>(null);
  const taBort = useMutation({
    mutationFn: () => lonebeskedApi.taBortKorning(k.id),
    onMutate: () => setFel(null),
    onError: (e) => setFel(felText(e, "Lönekörningen kunde inte tas bort.")),
    onSettled: uppdatera,
  });
  const manad = manadText(k.year, k.month);

  return (
    <div className="flex flex-col">
      <div className="flex items-end justify-between gap-3 border-b border-bok-kant pb-[6px] pt-6">
        <div className="min-w-0">
          <h3 className="text-[16px] font-medium leading-tight text-bok-text first-letter:uppercase">{manad}</h3>
          <div className="bok-mono pt-[2px] text-[11px] text-bok-meta">
            {[k.payment_date ? `utbetalning ${k.payment_date}` : null, `netto ${formatBeloppHela(k.total_net_salary)}`]
              .filter(Boolean)
              .join(" · ")}
          </div>
        </div>
        {kanTasBort(k) && (
          <Knapp
            type="button"
            sekundar
            disabled={taBort.isPending}
            onClick={() => {
              if (window.confirm(`Ta bort lönekörningen för ${manad} med dess lönebesked?`)) taBort.mutate();
            }}
          >
            Ta bort
          </Knapp>
        )}
      </div>
      {fel && (
        <div className="mt-2">
          <VyBanner ton="fel" text={fel} />
        </div>
      )}
      {(k.payslips ?? []).map((b) => (
        <BeskedRad key={b.id} b={b} />
      ))}
      {k.agi && <Agi ar={k.agi.year} manad={k.agi.month} />}
    </div>
  );
}

function BeskedRad({ b }: { b: Lonebesked }) {
  const uppdatera = useUppdatera();
  const [fel, setFel] = useState<string | null>(null);
  const markera = useMutation({
    mutationFn: () => lonebeskedApi.markeraSkickat(b.id),
    onMutate: () => setFel(null),
    onError: (e) => setFel(felText(e, "Kunde inte markera lönebeskedet som skickat.")),
    onSettled: uppdatera,
  });
  const lage = beskedLage(b);

  return (
    <div data-testid="lonebesked" className="border-b border-bok-linje-svagast py-[7px]">
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-[14px] leading-[1.35] text-bok-text">{b.employee_name ?? "Anställd"}</div>
          <div
            className={`bok-mono pt-[2px] text-[11px] leading-[1.45] ${
              lage === "inte skickat" ? "text-bok-vantar-meta" : "text-bok-meta"
            }`}
          >
            {`netto ${formatBeloppHela(b.net_salary)} · ${lage}`}
          </div>
        </div>
        <button
          type="button"
          onClick={() => void oppnaFil(pdfVag(b))}
          className="bok-mono shrink-0 text-[12px] text-bok-lank hover:underline"
        >
          PDF
        </button>
        {lage === "inte skickat" && (
          <button
            type="button"
            disabled={markera.isPending}
            onClick={() => markera.mutate()}
            className="bok-mono shrink-0 text-[12px] text-bok-lank hover:underline disabled:opacity-60"
          >
            Markera skickat
          </button>
        )}
      </div>
      {fel && (
        <div className="mt-2">
          <VyBanner ton="fel" text={fel} />
        </div>
      )}
    </div>
  );
}

function Agi({ ar, manad }: { ar: number; manad: number }) {
  const [oppen, setOppen] = useState(false);
  const { data, isError } = useQuery({
    queryKey: agiNyckel(ar, manad),
    queryFn: () => lonebeskedApi.agi(ar, manad),
    enabled: oppen,
    staleTime: 60 * 1000,
  });
  return (
    <div className="flex flex-col pb-2">
      <button
        type="button"
        aria-expanded={oppen}
        onClick={() => setOppen(!oppen)}
        className="self-start pt-3 text-[13px] text-bok-lank hover:underline"
      >
        Arbetsgivardeklaration för {manadText(ar, manad)}
      </button>
      {oppen &&
        (isError ? (
          <div className="mt-2">
            <VyBanner ton="fel" text="Arbetsgivardeklarationen kunde inte läsas." />
          </div>
        ) : !data ? (
          <div className="bok-mono pt-2 text-[12px] text-bok-meta">Hämtar…</div>
        ) : (
          <div className="flex flex-col pt-1">
            <Rubrik>Lämnas och betalas senast {data.due_date}</Rubrik>
            {data.individuals.map((i) => (
              <div key={i.employee_id} className="border-b border-bok-linje-svagast py-[7px]">
                <div className="text-[14px] text-bok-text">{i.name}</div>
                <div className="bok-mono pt-[2px] text-[11px] text-bok-meta">
                  {[
                    `215: ${i.personal_number || "personnummer saknas"}`,
                    `011: ${formatBeloppHela(i.gross_salary)}`,
                    `001: ${formatBeloppHela(i.preliminary_tax)}`,
                  ].join(" · ")}
                </div>
              </div>
            ))}
            <div className="bok-mono pt-2 text-[12px] text-bok-text-2">
              {[
                `487 arbetsgivaravgifter ${formatBeloppHela(data.total_employer_fee)}`,
                `497 skatteavdrag ${formatBeloppHela(data.total_preliminary_tax)}`,
                `att betala ${formatBeloppHela(data.total_to_pay)}`,
              ].join(" · ")}
            </div>
            <div className="pt-2 text-[13px] text-bok-text-svag">
              {data.booked
                ? "Bokförd mot skattekontot: 2710 och 2730 mot 1630."
                : data.unbooked_payslips > 0
                  ? "Bokför månadens löner först, sedan arbetsgivardeklarationen."
                  : "Bokförs när kvittensen från Skatteverket kommer in. Lägg den i Dropzone eller i tråden."}
            </div>
          </div>
        ))}
    </div>
  );
}
