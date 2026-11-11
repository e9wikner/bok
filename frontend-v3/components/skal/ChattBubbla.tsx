"use client";

import { useEffect, useRef, useState } from "react";
import { MessageCircle, X } from "lucide-react";
import { useBeslutFokus } from "@/components/skal/BeslutFokus";
import { ChattKolumn } from "@/components/skal/ChattKolumn";
import { tradNyckel, useOlastaSvar } from "@/hooks/useOlastaSvar";
import { allaVyer } from "@/lib/skal/vyer";

/** Vyns namn för en tråd. Flera vyer kan dela tråd; den första får ge namnet. */
function tradensTitel(viewKey: string): string {
  return allaVyer().find((v) => v.trad === viewKey)?.titel ?? viewKey;
}

/**
 * Chatten: en bubbla nere till höger som fäller ut den aktiva vyns tråd.
 *
 * Chatten var en kolumn (desktop) och en list längst ner (mobil) som tog yta
 * från vyn — det man faktiskt läser. Nu äger vyn ytan och chatten öppnas när
 * den behövs.
 *
 * - Desktop: en panel ovanför bubblan. Den är inte modal: vyn bakom går att
 *   läsa, men ett klick utanför panelen stänger den. Den står kvar öppen när
 *   vyn byts och visar då den nya vyns tråd.
 * - Mobil: ett ark från skärmens nederkant, som listen fälldes upp förut
 *   (tråden 260 px, mobilens fält). Ett vybyte stänger det: den som går
 *   till en ny vy möter vyn, inte förra vyns chatt. Ett tryck ovanför arket
 *   stänger det också.
 *
 * Panelen förblir monterad när den är stängd, så att strömmen, skrollen och
 * osänd text står kvar. Ett beslut, ett inlägg eller en förifyllning som tas
 * upp i vyn öppnar den. Väntande beslut syns som ett märke på bubblan även
 * när chatten är stängd (komponenter.md) — kön ligger i tråden och det finns
 * inga notiser.
 *
 * Ett svar från agenten öppnar den inte: den som stängt chatten läser något
 * annat. Ett oläst textsvar syns som en prick på bubblan, också när svaret
 * kom i en annan vys tråd (`useOlastaSvar`). Panelen säger då var svaret
 * ligger och leder dit.
 */
export function ChattBubbla({
  vyTitel,
  viewKey,
  vantandeBeslut,
  variant = "desktop",
  arId = null,
  gaTillTrad,
}: {
  vyTitel: string;
  viewKey: string;
  vantandeBeslut: number;
  variant?: "desktop" | "mobil";
  /** Årsväljarens räkenskapsår; `null` = innevarande. Varje år har sin tråd. */
  arId?: string | null;
  /** Byter till en vy med den tråden: dit ett oläst svar i en annan vy leder. */
  gaTillTrad?: (viewKey: string) => void;
}) {
  const mobil = variant === "mobil";
  const [oppen, setOppen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const bubbla = useRef<HTMLButtonElement>(null);
  const { valt, inlagg, forifyllning } = useBeslutFokus();
  const { olasta, onAgentSvar, onLamnadUtanSvar } = useOlastaSvar(viewKey, arId, oppen);
  const aktuell = tradNyckel(viewKey, arId);
  const svarHar = olasta.has(aktuell);
  const svarAndra = Array.from(olasta.entries())
    .filter(([k]) => k !== aktuell)
    .map(([, s]) => s);
  const harOlast = olasta.size > 0;
  const olastText = svarHar
    ? "nytt svar"
    : svarAndra.length > 0
      ? `nytt svar i ${svarAndra.map((s) => tradensTitel(s.viewKey)).join(", ")}`
      : null;

  // Mobil: ett vybyte stänger arket.
  const forraVyn = useRef(viewKey);
  useEffect(() => {
    if (forraVyn.current === viewKey) return;
    forraVyn.current = viewKey;
    if (mobil) setOppen(false);
  }, [viewKey, mobil]);

  useEffect(() => {
    if (valt && valt.view_key === viewKey) setOppen(true);
  }, [valt, viewKey]);
  useEffect(() => {
    if (inlagg && inlagg.viewKey === viewKey) setOppen(true);
  }, [inlagg, viewKey]);
  useEffect(() => {
    if (forifyllning && forifyllning.viewKey === viewKey) setOppen(true);
  }, [forifyllning, viewKey]);

  // Ett klick utanför panelen stänger den. Bubblan räknas inte som utanför:
  // den växlar själv. Ett klick i vyn som tar upp något i chatten (ett
  // beslut, ett inlägg) stänger först och öppnar sedan igen via effekterna
  // ovan.
  useEffect(() => {
    if (!oppen) return;
    const vidTryck = (e: PointerEvent) => {
      const mal = e.target as Node | null;
      if (!mal || !mal.isConnected) return;
      if (panel.current?.contains(mal) || bubbla.current?.contains(mal)) return;
      setOppen(false);
    };
    document.addEventListener("pointerdown", vidTryck);
    return () => document.removeEventListener("pointerdown", vidTryck);
  }, [oppen]);

  // Desktop: fältet får fokus när panelen öppnas. Inte på mobil, där
  // fokus fäller upp tangentbordet över tråden man ville läsa.
  useEffect(() => {
    if (!oppen || mobil) return;
    const id = requestAnimationFrame(() => {
      const el = panel.current;
      if (el && !el.contains(document.activeElement)) {
        el.querySelector<HTMLInputElement>("input[type=text], input:not([type])")?.focus();
      }
    });
    return () => cancelAnimationFrame(id);
  }, [oppen, viewKey, mobil]);

  const stang = () => {
    setOppen(false);
    // Bubblan döljs inte på desktop, så fokus kan gå tillbaka dit direkt.
    // På mobil syns den först efter nästa rendering.
    requestAnimationFrame(() => bubbla.current?.focus());
  };

  return (
    <>
      <div
        ref={panel}
        role="dialog"
        aria-modal="false"
        aria-label={`Chatt · ${vyTitel}`}
        hidden={!oppen}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.stopPropagation();
            stang();
          }
        }}
        className={
          mobil
            ? "fixed inset-x-0 bottom-0 z-40 flex max-h-[85dvh] flex-col overflow-hidden rounded-t-[14px] border-t border-bok-linje bg-bok-yta pb-[env(safe-area-inset-bottom)] shadow-bok-chattlist [&[hidden]]:hidden"
            : "fixed bottom-[132px] right-6 z-40 flex h-[min(680px,calc(100dvh-220px))] w-[min(460px,calc(100vw-48px))] flex-col overflow-hidden rounded-[14px] border border-bok-linje bg-bok-yta shadow-bok-meny [&[hidden]]:hidden"
        }
      >
        <div
          className={`flex shrink-0 items-center gap-2 border-b border-bok-linje ${
            mobil ? "min-h-[50px] px-4 py-[11px]" : "px-5 py-3"
          }`}
        >
          <span className="flex min-w-0 flex-1 items-baseline gap-2">
            <span className="text-[14px] font-medium text-bok-text">Chatt</span>
            <span className="truncate text-[14px] text-bok-meta">{vyTitel}</span>
          </span>
          <button
            type="button"
            onClick={stang}
            aria-label="Stäng chatten"
            className="-mr-1 rounded-md p-1 text-bok-text-svag hover:bg-bok-app hover:text-bok-text"
          >
            <X size={mobil ? 20 : 16} aria-hidden="true" />
          </button>
        </div>
        {svarAndra.length > 0 && (
          <ul className="shrink-0 border-b border-bok-linje px-5 py-2 text-[13px]">
            {svarAndra.map((s) => (
              <li key={tradNyckel(s.viewKey, s.fiscalYearId)}>
                <button
                  type="button"
                  onClick={() => gaTillTrad?.(s.viewKey)}
                  disabled={!gaTillTrad}
                  className="text-bok-lank hover:text-bok-lank-hover hover:underline disabled:text-bok-text-svag disabled:no-underline"
                >
                  Nytt svar i {tradensTitel(s.viewKey)} →
                </button>
              </li>
            ))}
          </ul>
        )}
        <ChattKolumn
          key={viewKey}
          vyTitel={vyTitel}
          viewKey={viewKey}
          variant={mobil ? "mobil" : "panel"}
          arId={arId}
          onAgentSvar={onAgentSvar}
          onLamnadUtanSvar={onLamnadUtanSvar}
        />
      </div>

      <button
        ref={bubbla}
        type="button"
        // Mobil: arket täcker bubblan och har sin egen stängknapp.
        hidden={mobil && oppen}
        onClick={() => (oppen ? stang() : setOppen(true))}
        aria-expanded={oppen}
        aria-label={
          oppen
            ? "Stäng chatten"
            : [
                `Öppna chatten för ${vyTitel}`,
                ...(olastText ? [olastText] : []),
                ...(vantandeBeslut > 0 ? [`${vantandeBeslut} väntar på beslut`] : []),
              ].join(" · ")
        }
        className={`fixed z-40 flex h-14 w-14 items-center justify-center rounded-full bg-bok-text text-bok-yta shadow-bok-meny transition-transform hover:scale-105 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-bok-lank [&[hidden]]:hidden ${
          mobil ? "bottom-[calc(16px+env(safe-area-inset-bottom))] right-4" : "bottom-[64px] right-6"
        }`}
      >
        {oppen ? <X size={22} aria-hidden="true" /> : <MessageCircle size={24} aria-hidden="true" />}
        {!oppen && vantandeBeslut > 0 && (
          <span
            data-testid="chattbubbla-marke"
            aria-hidden="true"
            className="bok-mono absolute -right-1 -top-1 flex h-[22px] min-w-[22px] items-center justify-center rounded-full border px-[6px] text-[11px]"
            style={{
              color: "var(--bok-vantar-meta)",
              background: "var(--bok-vantar-yta)",
              borderColor: "var(--bok-vantar-kant)",
            }}
          >
            {vantandeBeslut}
          </span>
        )}
        {!oppen && harOlast && (
          <span
            data-testid="chattbubbla-svar"
            aria-hidden="true"
            className="absolute -left-0.5 -top-0.5 h-[14px] w-[14px] rounded-full border-2 border-bok-yta bg-bok-lank"
          />
        )}
      </button>
    </>
  );
}
