"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { FALT, Knapp } from "@/components/skal/Formular";
import { VyBanner } from "@/components/skal/VyBanner";
import { VyHeaderStatus } from "@/components/skal/VyHeaderStatus";
import { VyRadSkelett } from "@/components/skal/VyRad";
import { VySektion } from "@/components/skal/VySektion";
import { felText } from "@/lib/skal/anstallda";
import { bokslutNyckel } from "@/lib/skal/bokslut";
import { KONTOPLAN_NYCKEL, type Konto, kontoklasser, kontoplanApi } from "@/lib/skal/kontoplan";
import { lageFarg } from "@/lib/skal/lage";
import {
  type SruData,
  arAnpassad,
  faltText,
  filtreraKonton,
  rorelseNyckel,
  sruApi,
  sruNyckel,
  sruStatus,
} from "@/lib/skal/sru";

/**
 * SRU-koppling (`bokslut.sru`): vilket INK2R-fält varje konto summeras till,
 * för året i headern. En ändring sparas direkt och räknar om INK2. Chattar
 * i Översiktens tråd, som bokslutets andra delar.
 */
export function SruVy({
  titel,
  arId,
  variant,
}: {
  titel: string;
  arId: string | null | undefined;
  variant: "desktop" | "mobil";
}) {
  const sru = useQuery({
    queryKey: sruNyckel(arId ?? ""),
    queryFn: () => sruApi.hamta(arId ?? ""),
    enabled: !!arId,
    staleTime: 60 * 1000,
  });
  const konton = useQuery({ queryKey: KONTOPLAN_NYCKEL, queryFn: kontoplanApi.lista, staleTime: 10 * 60 * 1000 });
  const [sok, setSok] = useState("");
  const [baraAnpassade, setBaraAnpassade] = useState(false);
  const [baraMedTransaktioner, setBaraMedTransaktioner] = useState(false);
  // Frågan går först när rutan kryssas i.
  const rorelse = useQuery({
    queryKey: rorelseNyckel(arId ?? ""),
    queryFn: () => sruApi.kontonMedTransaktioner(arId ?? ""),
    enabled: !!arId && baraMedTransaktioner,
    staleTime: 60 * 1000,
  });
  const medTransaktioner = baraMedTransaktioner && rorelse.data ? new Set(rorelse.data) : null;
  const isError = sru.isError || konton.isError || (baraMedTransaktioner && rorelse.isError);
  const status = sruStatus(sru.data, isError, arId);
  const pad = variant === "desktop" ? "px-6" : "px-[18px]";
  const klasser =
    konton.data && sru.data && !(baraMedTransaktioner && !rorelse.data)
      ? kontoklasser(filtreraKonton(konton.data, sru.data, baraAnpassade, medTransaktioner), sok)
      : [];

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
          <div className="pt-5 text-[13px] text-bok-text-svag">Det finns inget räkenskapsår att koppla.</div>
        ) : isError ? (
          <div className="mt-[14px]">
            <VyBanner ton="fel" text="SRU-kopplingen kunde inte läsas. Ladda om sidan." />
          </div>
        ) : !sru.data || !konton.data || !arId ? (
          <div className="pt-5">
            <VyRadSkelett />
          </div>
        ) : (
          <>
            <Arsatgarder arId={arId} />
            <div className="flex flex-wrap items-center gap-3 pt-[14px]">
              <input
                type="search"
                value={sok}
                onChange={(e) => setSok(e.target.value)}
                placeholder="Sök på nummer eller namn"
                aria-label="Sök konto"
                className={`${FALT} max-w-[320px]`}
              />
              <label className="flex items-center gap-2 text-[13px] text-bok-text-2">
                <input type="checkbox" checked={baraAnpassade} onChange={(e) => setBaraAnpassade(e.target.checked)} />
                Bara anpassade
              </label>
              <label className="flex items-center gap-2 text-[13px] text-bok-text-2">
                <input
                  type="checkbox"
                  checked={baraMedTransaktioner}
                  onChange={(e) => setBaraMedTransaktioner(e.target.checked)}
                />
                Bara konton med transaktioner under året
              </label>
            </div>
            {baraMedTransaktioner && !rorelse.data ? (
              <div className="pt-5">
                <VyRadSkelett />
              </div>
            ) : klasser.length === 0 ? (
              <div className="bok-mono pt-5 text-[12px] text-bok-meta">Inga konton matchar.</div>
            ) : null}
            {klasser.map((g) => (
              <VySektion key={g.klass} titel={`${g.klass} · ${g.titel}`} antalRader={g.konton.length} variant={variant}>
                {g.konton.map((k) => (
                  <KontoRad key={k.code} k={k} data={sru.data!} arId={arId} />
                ))}
              </VySektion>
            ))}
          </>
        )}

        <div className="pt-5 text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">
          Varje konto summeras till ett fält i INK2R. Standarden kommer ur BAS kopplingstabell; en koppling som sparas för
          året går före den. SRU-filerna laddas ner under INK2.
        </div>
      </div>
    </div>
  );
}

/** Det som påverkas av en ändrad koppling: kopplingen och årets INK2. */
function useEfterAndring(arId: string) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: sruNyckel(arId) });
    void queryClient.invalidateQueries({ queryKey: bokslutNyckel(arId) });
  };
}

function Arsatgarder({ arId }: { arId: string }) {
  const efter = useEfterAndring(arId);
  const [fel, setFel] = useState<string | null>(null);
  const atgard = useMutation({
    mutationFn: (vad: "arv" | "standard") =>
      vad === "arv" ? sruApi.arvFranForegaende(arId) : sruApi.aterstallStandard(arId),
    onMutate: () => setFel(null),
    onError: (e) => setFel(felText(e, "Kopplingen kunde inte ändras.")),
    onSettled: efter,
  });
  const fraga = (vad: "arv" | "standard", text: string) => {
    if (window.confirm(text)) atgard.mutate(vad);
  };
  return (
    <div className="flex flex-col pt-[14px]">
      <div className="flex flex-wrap gap-3">
        <Knapp
          type="button"
          sekundar
          disabled={atgard.isPending}
          onClick={() => fraga("arv", "Ersätta årets kopplingar med föregående års?")}
        >
          Ärv från föregående år
        </Knapp>
        <Knapp
          type="button"
          sekundar
          disabled={atgard.isPending}
          onClick={() => fraga("standard", "Ta bort årets kopplingar, så att standarden gäller för alla konton?")}
        >
          Återställ standard
        </Knapp>
      </div>
      {fel && (
        <div className="mt-[14px]">
          <VyBanner ton="fel" text={fel} />
        </div>
      )}
    </div>
  );
}

function KontoRad({ k, data, arId }: { k: Konto; data: SruData; arId: string }) {
  const koppling = data.kopplingar[k.code];
  const anpassad = arAnpassad(koppling);
  const [oppen, setOppen] = useState(false);
  const [fel, setFel] = useState<string | null>(null);
  const efter = useEfterAndring(arId);

  const andra = useMutation({
    mutationFn: async (val: string) => {
      if (val === "") {
        if (koppling?.sparad) await sruApi.anvandStandard(arId, koppling.sparad.id);
      } else {
        await sruApi.koppla(arId, k.code, val);
      }
    },
    onMutate: () => setFel(null),
    onSuccess: () => setOppen(false),
    onError: (e) => setFel(felText(e, "Kopplingen kunde inte sparas.")),
    onSettled: efter,
  });

  return (
    <div data-testid="sru-konto" className="border-b border-bok-linje-svagast">
      <button
        type="button"
        onClick={() => setOppen(!oppen)}
        aria-expanded={oppen}
        className="-mx-2 flex w-[calc(100%+16px)] flex-wrap items-baseline gap-x-3 gap-y-[2px] px-2 py-[7px] text-left hover:bg-bok-yta-svag"
      >
        <span className="bok-mono bok-tal w-[44px] shrink-0 text-[13px] text-bok-text">{k.code}</span>
        <span className="min-w-0 flex-1 text-[14px] leading-[1.35] text-bok-text">{k.name}</span>
        {/* Fältet på en egen rad under namnet: det är långt och ska få radbryta,
            inte skjuta in över namnet på en smal skärm. */}
        <span
          className={`bok-mono basis-full break-words pl-[56px] text-[11px] leading-[1.45] ${
            anpassad ? "text-bok-vantar-meta" : "text-bok-meta"
          }`}
        >
          {faltText(data.falt, koppling?.galler ?? null)}
          {anpassad ? " · anpassad" : ""}
        </span>
      </button>
      {oppen && (
        <div className="flex flex-col gap-2 pb-3 pt-1">
          <select
            aria-label={`SRU-fält för ${k.code}`}
            value={koppling?.sparad ? koppling.sparad.falt : ""}
            disabled={andra.isPending}
            onChange={(e) => andra.mutate(e.target.value)}
            className={FALT}
          >
            <option value="">
              {koppling?.standard ? `Standard: ${faltText(data.falt, koppling.standard)}` : "Ingen koppling (standard)"}
            </option>
            {data.falt.map((f) => (
              <option key={f.code} value={f.code}>
                {f.row} {f.label} (BAS {f.accounts})
              </option>
            ))}
          </select>
          {fel && <VyBanner ton="fel" text={fel} />}
        </div>
      )}
    </div>
  );
}
