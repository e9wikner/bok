"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { BeslutFokusProvider } from "@/components/skal/BeslutFokus";
import { ChattKolumn } from "@/components/skal/ChattKolumn";
import { ChattList } from "@/components/skal/ChattList";
import { DetaljLager } from "@/components/skal/Detalj";
import { DetaljProvider, useDetaljHistorik } from "@/components/skal/DetaljKontext";
import { Header } from "@/components/skal/Header";
import { PrickNav } from "@/components/skal/PrickNav";
import type { SidMeta } from "@/components/skal/SidVaeljare";
import { VyInnehall } from "@/components/skal/VyInnehall";
import { VySvep } from "@/components/skal/VySvep";
import { useAgentStatus, useOverview } from "@/hooks/useSkal";
import { useVyer } from "@/hooks/useVyer";
import { useVantandeBeslut } from "@/hooks/useVantandeBeslut";
import { useBredSkarm } from "@/hooks/useBredSkarm";
import { bokslutApi } from "@/lib/skal/bokslut";
import { arsalternativ, arsrad, somOverviewAr } from "@/lib/skal/header";
import { lageFarg } from "@/lib/skal/lage";
import type { Detalj } from "@/lib/skal/detalj";
import { lasDetalj, lasPosition, positionsUrl } from "@/lib/skal/rutt";
import {
  type Sidnyckel,
  type ViewKey,
  type Vy,
  forstaVyn,
  sidan,
  vyAt,
  vyIndex as indexForVy,
} from "@/lib/skal/vyer";

/**
 * Skalet: tre sidor, sju vyer, en rutt.
 *
 * Vyn är ett skrolläge och sidan är en navigering. Vypositionen skrivs med
 * history.replaceState så att ett svep inte kostar en post i historiken och
 * bakåtknappen förblir användbar; sidbytet går genom samma mekanism men är
 * ett riktigt byte som landar på sidans FÖRSTA vy. SPEC-skal.md §4, §5.
 */
export function Skal() {
  const params = useSearchParams();
  const start = useMemo(
    () => ({
      ...lasPosition(params?.get("sida"), params?.get("vy")),
      detalj: lasDetalj(params?.get("konto"), params?.get("ver")),
    }),
    // Bara startvärdet; därefter äger komponenten positionen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const [sidnyckel, setSidnyckel] = useState<Sidnyckel>(start.sida);
  const [vyIndex, setVyIndex] = useState<number>(
    sidan(start.sida).vyer.findIndex((v) => v.key === start.vy.key)
  );

  const sida = sidan(sidnyckel);
  const aktivVy: Vy = vyAt(sidnyckel, vyIndex) ?? forstaVyn(sidnyckel);

  // Detaljlagret (huvudbok, verifikation) står ovanpå den aktiva vyn.
  const detaljUrl = useCallback(
    (stack: readonly Detalj[]) => positionsUrl(sidnyckel, aktivVy, stack[stack.length - 1]),
    [sidnyckel, aktivVy]
  );
  const gaTillVy = useCallback(
    (key: ViewKey) => {
      const i = indexForVy(sidnyckel, key);
      if (i !== -1) setVyIndex(i);
    },
    [sidnyckel]
  );
  const detalj = useDetaljHistorik({ start: start.detalj, url: detaljUrl, gaTillVy });
  const { stack: detaljer, stang: stangDetalj } = detalj;

  // Ett vybyte eller sidbyte stänger lagret: det hör till vyn det öppnades i.
  const forraVyn = useRef(aktivVy.key);
  useEffect(() => {
    if (forraVyn.current === aktivVy.key) return;
    forraVyn.current = aktivVy.key;
    stangDetalj();
  }, [aktivVy.key, stangDetalj]);

  // Positionen speglas i URL:en utan att gå genom routern.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = positionsUrl(sidnyckel, aktivVy, detaljer[detaljer.length - 1]);
    window.history.replaceState({ ...window.history.state, bokDetalj: detaljer }, "", url);
  }, [sidnyckel, aktivVy, detaljer]);
  const lagerOppet = detaljer.length > 0;

  const bred = useBredSkarm();
  const { data: overview } = useOverview();
  const { data: agent } = useAgentStatus();
  // Märket läses för den aktiva vyn och bara på mobil, där det finns
  // (SPEC-chattyta.md §10). Inte beroende av om chatten är minimerad: det
  // är då märket behövs (komponenter.md). Grannvyerna i svepraden får 0,
  // som de får en oläst tråd (C5) — de ligger utanför skärmen.
  const vantandeBeslut = useVantandeBeslut(aktivVy.key, { aktiv: !bred });

  const metaPerSida = useMemo<Partial<Record<Sidnyckel, SidMeta>>>(() => {
    const ut: Partial<Record<Sidnyckel, SidMeta>> = {};
    for (const s of overview?.pages ?? []) {
      // Serverns beslut och serverns formulering, ordagrant.
      ut[s.key] = { waiting: s.waiting, meta: s.meta };
    }
    return ut;
  }, [overview]);

  const valjSida = useCallback((ny: Sidnyckel) => {
    setSidnyckel(ny);
    setVyIndex(0); // Byte av sida landar alltid på sidans första vy.
  }, []);

  // Årsväljaren. Utan val gäller översiktens år (det aktuella); ett valt år
  // som inte längre finns i listan faller tillbaka dit.
  const { data: arslista } = useQuery({
    queryKey: ["skal", "rakenskapsar"],
    queryFn: bokslutApi.getRakenskapsar,
    staleTime: 60 * 1000,
  });
  const [valtArId, setValtArId] = useState<string | null>(null);
  const valtAr = arslista?.fiscal_years.find((a) => a.id === valtArId);
  const ar = valtAr ? somOverviewAr(valtAr) : overview === undefined ? undefined : overview.fiscal_year;

  const vyer = useVyer(ar, sidnyckel);

  const { data } = vyer[aktivVy.key];
  const vyStatus = { text: data.status, fg: lageFarg(data.lage) };

  return (
    // h-dvh, inte h-screen: 100vh är i iOS Safari höjden med adressraden
    // indragen, så chattlisten längst ner hamnade bakom den.
    // `overflow-hidden`: skalet är exakt en skärm. Allt som skrollar gör det
    // i sin egen yta, aldrig dokumentet.
    <BeslutFokusProvider>
    <DetaljProvider value={detalj}>
    <div className="flex h-screen h-dvh min-h-0 flex-col overflow-hidden bg-bok-app">
      <Header
        variant={bred ? "desktop" : "mobil"}
        sida={sida}
        aktivVy={aktivVy}
        aktivIndex={vyIndex}
        metaPerSida={metaPerSida}
        arsrad={arsrad(overview)}
        arsval={
          arslista && ar
            ? {
                alternativ: arsalternativ(arslista.fiscal_years, overview),
                valt: ar.id,
                onValj: setValtArId,
              }
            : undefined
        }
        vyStatus={vyStatus}
        agent={agent}
        onValjSida={valjSida}
        onValjVy={setVyIndex}
      />

      <VySvep
        // Ny sida = ny sverprad. Utan nyckeln ligger skrollpositionen kvar
        // från förra sidan medan innehållet redan har bytts.
        key={sida.key}
        sida={sida}
        aktivIndex={vyIndex}
        onIndexChange={setVyIndex}
        renderVy={(vy, i) => {
          const { data: innehall, laddar } = vyer[vy.key];
          // Bara den aktiva vyns tråd läses och strömmas: svepraden renderar
          // sidans alla vyer, och SPEC-chattyta.md §6.2 punkt 5 säger en
          // ström per flik.
          const aktiv = i === vyIndex;
          if (bred) {
            return (
              <div
                className="grid min-h-0 flex-1"
                // `minmax(0, 1fr)`, inte `1fr`: en bred tabell eller ett
                // kodblock i tråden gör annars chattkolumnen lika bred som
                // innehållet och trycker ut läskolumnen ur skärmen.
                style={{ gridTemplateColumns: "minmax(0, 1fr) var(--bok-vykolumn)" }}
              >
                <ChattKolumn vyTitel={vy.titel} viewKey={vy.key} aktiv={aktiv} />
                {aktiv && lagerOppet ? (
                  <DetaljLager vyTitel={vy.titel} ar={ar} />
                ) : (
                  <VyInnehall vy={vy} data={innehall} laddar={laddar} />
                )}
              </div>
            );
          }
          return (
            <div className="flex min-h-0 flex-1 flex-col">
              {aktiv && lagerOppet ? (
                <DetaljLager vyTitel={vy.titel} ar={ar} variant="mobil" />
              ) : (
                <VyInnehall vy={vy} data={innehall} laddar={laddar} variant="mobil" />
              )}
              <ChattList
                vyTitel={vy.titel}
                viewKey={vy.key}
                aktiv={aktiv}
                vantandeBeslut={aktiv ? vantandeBeslut : 0}
              />
            </div>
          );
        }}
      />

      {bred && (
        <div className="flex h-[48px] shrink-0 items-center justify-center border-t border-bok-linje bg-bok-yta px-5">
          {/* Foten bär bara prickarna. "dra i sidled" och lägesräknaren i
              v10 är dokumentationskrom och byggs inte (SPEC-skal.md §2.3). */}
          <PrickNav vyer={sida.vyer} aktivIndex={vyIndex} onValj={setVyIndex} />
        </div>
      )}
    </div>
    </DetaljProvider>
    </BeslutFokusProvider>
  );
}
