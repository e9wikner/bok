"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ChattKolumn } from "@/components/skal/ChattKolumn";
import { ChattList } from "@/components/skal/ChattList";
import { Header } from "@/components/skal/Header";
import { PrickNav } from "@/components/skal/PrickNav";
import type { SidMeta } from "@/components/skal/SidVaeljare";
import { VyInnehall } from "@/components/skal/VyInnehall";
import { VySvep } from "@/components/skal/VySvep";
import { useAgentStatus, useOverview } from "@/hooks/useSkal";
import { useBredSkarm } from "@/hooks/useBredSkarm";
import { arsrad } from "@/lib/skal/header";
import { lageFarg } from "@/lib/skal/lage";
import { MOCK_VYER, mockVantandeBeslut } from "@/lib/skal/mock";
import { SKAL_RUTT, lasPosition } from "@/lib/skal/rutt";
import { type Sidnyckel, type Vy, forstaVyn, sidan, vyAt } from "@/lib/skal/vyer";

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
    () => lasPosition(params?.get("sida"), params?.get("vy")),
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

  // Positionen speglas i URL:en utan att gå genom routern.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = `${SKAL_RUTT}?sida=${sidnyckel}&vy=${aktivVy.slug}`;
    window.history.replaceState(window.history.state, "", url);
  }, [sidnyckel, aktivVy.slug]);

  const bred = useBredSkarm();
  const { data: overview } = useOverview();
  const { data: agent } = useAgentStatus();

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

  const data = MOCK_VYER[aktivVy.key];
  const vyStatus = { text: data.status, fg: lageFarg(data.lage) };

  return (
    <div className="flex h-screen min-h-0 flex-col bg-bok-app">
      <Header
        variant={bred ? "desktop" : "mobil"}
        sida={sida}
        aktivVy={aktivVy}
        aktivIndex={vyIndex}
        metaPerSida={metaPerSida}
        arsrad={arsrad(overview)}
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
          const vyData = MOCK_VYER[vy.key];
          // Bara den aktiva vyns tråd läses och strömmas: svepraden renderar
          // sidans alla vyer, och SPEC-chattyta.md §6.2 punkt 5 säger en
          // ström per flik.
          const aktiv = i === vyIndex;
          if (bred) {
            return (
              <div
                className="grid min-h-0 flex-1"
                style={{ gridTemplateColumns: "1fr var(--bok-vykolumn)" }}
              >
                <ChattKolumn vyTitel={vy.titel} viewKey={vy.key} aktiv={aktiv} />
                <VyInnehall vy={vy} data={vyData} />
              </div>
            );
          }
          return (
            <div className="flex min-h-0 flex-1 flex-col">
              <VyInnehall vy={vy} data={vyData} variant="mobil" />
              <ChattList
                vyTitel={vy.titel}
                viewKey={vy.key}
                aktiv={aktiv}
                vantandeBeslut={mockVantandeBeslut(vy.key)}
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
  );
}
