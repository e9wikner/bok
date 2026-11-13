"use client";

import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AnstalldaVy } from "@/components/skal/AnstalldaVy";
import { BeslutFokusProvider } from "@/components/skal/BeslutFokus";
import { BokslutVy } from "@/components/skal/BokslutVy";
import { ChattBubbla } from "@/components/skal/ChattBubbla";
import { DropzoneVy } from "@/components/skal/DropzoneVy";
import { KontoplanVy } from "@/components/skal/KontoplanVy";
import { RevisionsloggVy } from "@/components/skal/RevisionsloggVy";
import { DetaljLager } from "@/components/skal/Detalj";
import { DetaljProvider, useDetaljHistorik } from "@/components/skal/DetaljKontext";
import { Header } from "@/components/skal/Header";
import { SidNav } from "@/components/skal/SidNav";
import type { SidMeta } from "@/components/skal/SidVaeljare";
import { VyInnehall } from "@/components/skal/VyInnehall";
import { VySvep } from "@/components/skal/VySvep";
import { useAgentStatus, useOverview } from "@/hooks/useSkal";
import { useVyer } from "@/hooks/useVyer";
import { useVantandeBeslut } from "@/hooks/useVantandeBeslut";
import { useLasning } from "@/hooks/useLasning";
import { useBredSkarm } from "@/hooks/useBredSkarm";
import { useDarkMode } from "@/hooks/useDarkMode";
import { STANDARDSORTERING, type Sortering } from "@/lib/skal/bocker";
import { bokslutApi } from "@/lib/skal/bokslut";
import { arsalternativ, arsrad, somOverviewAr } from "@/lib/skal/header";
import { lageFarg } from "@/lib/skal/lage";
import type { Detalj } from "@/lib/skal/detalj";
import { lasDetalj, lasPosition, positionsUrl } from "@/lib/skal/rutt";
import {
  type Sidnyckel,
  type ViewKey,
  type Vy,
  type Vynyckel,
  allaVyer,
  arBokslutsdel,
  forstaVyn,
  sidan,
  vyAt,
  vyIndex as indexForVy,
} from "@/lib/skal/vyer";

/**
 * Skalet: tre sidor, deras vyer, en rutt.
 *
 * Vyn är ett skrolläge och sidan är en navigering. Vypositionen skrivs med
 * history.replaceState så att ett svep inte kostar en post i historiken och
 * bakåtknappen förblir användbar; sidbytet går genom samma mekanism men är
 * ett riktigt byte som landar på sidans FÖRSTA vy.
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
  // En rad kan leda till en vy på en annan sida: ett lönekort i
  // Verifikationers Väntar på beslut leder till Löner. Det är en länk till
  // just den vyn, som en inklistrad adress, inte ett sidbyte i väljaren —
  // därför landar den inte på sidans första vy.
  const gaTillVy = useCallback(
    (key: Vynyckel) => {
      const i = indexForVy(sidnyckel, key);
      if (i !== -1) {
        setVyIndex(i);
        return;
      }
      const annan = allaVyer().find((v) => v.key === key);
      if (!annan) return;
      setSidnyckel(annan.sida);
      setVyIndex(indexForVy(annan.sida, key));
    },
    [sidnyckel]
  );
  // Ett oläst svar i en annan vys tråd leder dit (`ChattBubbla`). Hör den
  // aktiva vyn redan till tråden står man kvar.
  const gaTillTrad = useCallback(
    (trad: string) => {
      if (aktivVy.trad === trad) return;
      const pasidan = sida.vyer.find((v) => v.trad === trad);
      const vy = pasidan ?? allaVyer().find((v) => v.trad === trad);
      if (vy) gaTillVy(vy.key);
    },
    [aktivVy.trad, sida, gaTillVy]
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
  const tema = useDarkMode();
  // Årsväljaren. Utan val gäller översiktens år (det aktuella); ett valt år
  // som inte längre finns i listan faller tillbaka dit.
  const { data: arslista } = useQuery({
    queryKey: ["skal", "rakenskapsar"],
    queryFn: bokslutApi.getRakenskapsar,
    staleTime: 60 * 1000,
  });
  const [valtArId, setValtArId] = useState<string | null>(null);
  const valtAr = arslista?.fiscal_years.find((a) => a.id === valtArId);
  // Räknarna (sidornas rader, flikarnas antal) gäller året som visas; det
  // som väntar i ett annat år står i `other_years`.
  const { data: overview } = useOverview(valtAr?.id ?? null);
  const ar = valtAr ? somOverviewAr(valtAr) : overview === undefined ? undefined : overview.fiscal_year;
  // Chatten följer årsväljaren: en tråd per vy och år.
  // Utan val löser servern innevarande år själv, så tråden laddas inte om
  // när översikten kommer.
  const tradensAr = valtAr?.id ?? null;
  const { data: agent } = useAgentStatus();
  // Märket läses för den aktiva vyn, på chattbubblan. Inte beroende av om chatten är
  // minimerad: det är då märket behövs (komponenter.md). Grannvyerna i
  // svepraden får 0, som de får en oläst tråd (C5) — de ligger utanför skärmen.
  // Bara årets beslut, som vyn visar.
  const vantandeBeslut = useVantandeBeslut(aktivVy.trad, { arId: ar?.id });

  const antalPerVy = useMemo<Partial<Record<ViewKey, number>>>(() => {
    const ut: Partial<Record<ViewKey, number>> = {};
    for (const v of overview?.views ?? []) ut[v.key] = v.waiting;
    return ut;
  }, [overview]);

  // Bokslutets kontroller står under vyn de gäller, inte under sidan.
  const bokslutPerVy = useMemo<Partial<Record<Vynyckel, SidMeta>>>(() => {
    const ut: Partial<Record<Vynyckel, SidMeta>> = {};
    for (const v of overview?.closing_views ?? []) ut[v.key] = { waiting: v.waiting > 0, meta: v.meta };
    return ut;
  }, [overview]);

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

  // Översiktens lås gäller året som visas.
  const lasning = useLasning();
  const visatAr = arslista?.fiscal_years.find((a) => a.id === ar?.id);
  const arsLas = visatAr ? lasning.ar(visatAr) : undefined;

  // Sökrutan i Verifikationer. Den uppskjutna termen filtrerar, så att
  // rutan svarar på varje tangent också när året är stort. Termen står kvar
  // medan en verifikation är öppen, så "tillbaka" landar i samma träffar.
  const [sokterm, setSokterm] = useState("");
  // Postades ordning, som söktermen kvar medan en verifikation är öppen.
  const [sortering, setSortering] = useState<Sortering>(STANDARDSORTERING);
  const vyer = useVyer(ar, sidnyckel, useDeferredValue(sokterm), sortering);
  const sok = { varde: sokterm, onAndra: setSokterm, sortering, onSortera: setSortering };

  const { data } = vyer[aktivVy.key];
  const vyStatus = { text: data.status, fg: lageFarg(data.lage) };

  return (
    // h-dvh, inte h-screen: 100vh är i iOS Safari höjden med adressraden
    // indragen, så chattlisten längst ner hamnade bakom den.
    // `overflow-hidden`: skalet är exakt en skärm. Allt som skrollar gör det
    // i sin egen yta, aldrig dokumentet.
    //
    // `text-bok-text`: allt utan egen textfärg ärver skalets, inte shadcn-
    // temats `--foreground` (#59). Mörkt läge byter värdena på `--bok-*`.
    <BeslutFokusProvider>
    <DetaljProvider value={detalj}>
    <div className="flex h-screen h-dvh min-h-0 flex-col overflow-hidden bg-bok-app text-bok-text">
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
        tema={tema}
      />

      <div className="flex min-h-0 flex-1">
      {bred && (
        <SidNav
          aktivVy={aktivVy.key}
          metaPerSida={metaPerSida}
          antalPerVy={antalPerVy}
          metaPerVy={bokslutPerVy}
          andraAr={overview?.other_years ?? []}
          onValjVy={gaTillVy}
          onValjAr={setValtArId}
          tema={tema}
        />
      )}
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
          // sidans alla vyer, och det ska vara en
          // ström per flik.
          const aktiv = i === vyIndex;
          const variant = bred ? "desktop" : "mobil";
          const bokslutsvy = arBokslutsdel(vy.key) ? (
            <BokslutVy
              del={vy.key}
              titel={vy.titel}
              arId={ar === undefined ? undefined : (ar?.id ?? null)}
              las={arsLas}
              onGaTill={gaTillVy}
              variant={variant}
            />
          ) : vy.key === "bocker.dropzone" ? (
            <DropzoneVy titel={vy.titel} variant={variant} />
          ) : vy.key === "bocker.kontoplan" ? (
            <KontoplanVy titel={vy.titel} variant={variant} />
          ) : vy.key === "bocker.revisionslogg" ? (
            <RevisionsloggVy titel={vy.titel} variant={variant} />
          ) : vy.key === "betala.anstallda" ? (
            <AnstalldaVy titel={vy.titel} variant={variant} onGaTill={gaTillVy} />
          ) : null;
          if (bred) {
            // Vyn äger ytan bredvid sidonavigeringen; chatten är en bubbla
            // (`ChattBubbla`) nere till höger. Kolumnen fyller bredden upp
            // till en maxbredd, så att beloppskolumnerna får plats.
            return (
              <div className="flex min-h-0 flex-1 justify-center px-6 pt-5">
                <div className="flex min-h-0 w-full max-w-[1180px] flex-col overflow-hidden rounded-t-[12px] border-x border-t border-bok-linje bg-bok-yta">
                  {aktiv && lagerOppet ? (
                    <DetaljLager vyTitel={vy.titel} ar={ar} />
                  ) : bokslutsvy ? (
                    bokslutsvy
                  ) : (
                    <VyInnehall
                      vy={vy}
                      data={innehall}
                      laddar={laddar}
                      sok={vy.key === "bocker.verifikationer" ? sok : undefined}
                    />
                  )}
                </div>
              </div>
            );
          }
          return (
            <div className="flex min-h-0 flex-1 flex-col">
              {aktiv && lagerOppet ? (
                <DetaljLager vyTitel={vy.titel} ar={ar} variant="mobil" />
              ) : bokslutsvy ? (
                bokslutsvy
              ) : (
                <VyInnehall
                  vy={vy}
                  data={innehall}
                  laddar={laddar}
                  variant="mobil"
                  sok={vy.key === "bocker.verifikationer" ? sok : undefined}
                />
              )}
            </div>
          );
        }}
      />
      </div>
      <ChattBubbla
        vyTitel={aktivVy.titel}
        viewKey={aktivVy.trad}
        vantandeBeslut={vantandeBeslut}
        variant={bred ? "desktop" : "mobil"}
        arId={tradensAr}
        gaTillTrad={gaTillTrad}
      />
    </div>
    </DetaljProvider>
    </BeslutFokusProvider>
  );
}
