"use client";

/**
 * Olästa agentsvar, för chattbubblans märke.
 *
 * Chatten öppnas inte av sig själv när agenten svarar: den som stängt den
 * läser något annat. Bubblan visar i stället att ett svar väntar.
 *
 * Två vägar in:
 *
 * - Den aktiva tråden (`useTrad`) säger till när ett textsvar kommer. Är
 *   panelen stängd är det oläst.
 * - En tråd som lämnats med en obesvarad fråga (vy- eller årsbyte) stänger
 *   sin ström. Här öppnas en egen ström mot den tråden som bara väntar på
 *   textsvaret och sedan stängs.
 *
 * Bara textsvar räknas: statusrader och kort är inget svar att läsa. Väntande
 * beslut har redan sitt eget märke.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { arAgentText, type LamnadTrad } from "@/hooks/useTrad";
import { oppnaStrom } from "@/lib/chattyta/strom";

/** En agentkörning som inte svarat på så här länge bevakas inte längre. */
export const BEVAKNING_MAX_MS = 15 * 60 * 1000;

export function tradNyckel(viewKey: string, fiscalYearId: string | null): string {
  return `${viewKey}|${fiscalYearId ?? ""}`;
}

export interface OlastSvar {
  viewKey: string;
  fiscalYearId: string | null;
}

export function useOlastaSvar(
  viewKey: string,
  fiscalYearId: string | null,
  oppen: boolean
): {
  /** Trådar med ett oläst svar, på `tradNyckel`. */
  olasta: ReadonlyMap<string, OlastSvar>;
  /** Till den aktiva trådens `useTrad`. */
  onAgentSvar: () => void;
  onLamnadUtanSvar: (trad: LamnadTrad) => void;
} {
  const { logout } = useAuth();
  const [olasta, setOlasta] = useState<ReadonlyMap<string, OlastSvar>>(new Map());
  const aktuell = tradNyckel(viewKey, fiscalYearId);
  const lage = useRef({ aktuell, oppen });
  useLayoutEffect(() => {
    lage.current = { aktuell, oppen };
  }, [aktuell, oppen]);
  const vakter = useRef(new Map<string, AbortController>());
  const monterad = useRef(true);

  const markera = useCallback((svar: OlastSvar) => {
    const nyckel = tradNyckel(svar.viewKey, svar.fiscalYearId);
    // Syns det redan är det inte oläst.
    if (lage.current.oppen && lage.current.aktuell === nyckel) return;
    setOlasta((f) => (f.has(nyckel) ? f : new Map(f).set(nyckel, svar)));
  }, []);

  const onAgentSvar = useCallback(() => {
    const [vk, ar] = lage.current.aktuell.split("|");
    markera({ viewKey: vk, fiscalYearId: ar || null });
  }, [markera]);

  const onLamnadUtanSvar = useCallback(
    ({ viewKey: vk, fiscalYearId: ar, since }: LamnadTrad) => {
      if (!monterad.current) return;
      const nyckel = tradNyckel(vk, ar);
      vakter.current.get(nyckel)?.abort();
      const avbryt = new AbortController();
      vakter.current.set(nyckel, avbryt);
      const tid = setTimeout(() => avbryt.abort(), BEVAKNING_MAX_MS);
      avbryt.signal.addEventListener("abort", () => {
        clearTimeout(tid);
        if (vakter.current.get(nyckel) === avbryt) vakter.current.delete(nyckel);
      });
      void oppnaStrom({
        viewKey: vk,
        ...(ar ? { fiscalYearId: ar } : {}),
        since,
        signal: avbryt.signal,
        onHandelse: (h) => {
          if (!arAgentText(h)) return;
          markera({ viewKey: vk, fiscalYearId: ar });
          avbryt.abort();
        },
        onObehorig: logout,
      });
    },
    [markera, logout]
  );

  // Tillbaka i en bevakad tråd: dess egen `useTrad` tar över.
  useEffect(() => {
    vakter.current.get(aktuell)?.abort();
  }, [aktuell]);

  // Det som syns är läst.
  useEffect(() => {
    if (!oppen) return;
    setOlasta((f) => {
      if (!f.has(aktuell)) return f;
      const ny = new Map(f);
      ny.delete(aktuell);
      return ny;
    });
  }, [oppen, aktuell]);

  useEffect(() => {
    monterad.current = true;
    const alla = vakter.current;
    return () => {
      monterad.current = false;
      for (const a of Array.from(alla.values())) a.abort();
    };
  }, []);

  return { olasta, onAgentSvar, onLamnadUtanSvar };
}
