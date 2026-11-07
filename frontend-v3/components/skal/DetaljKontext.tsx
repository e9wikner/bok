"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { type Detalj, type RadMal, sammaDetalj } from "@/lib/skal/detalj";
import type { ViewKey } from "@/lib/skal/vyer";

/**
 * Detaljlagrets stack (`Detalj.tsx`).
 *
 * Att öppna en detalj är en riktig navigering, till skillnad från svepet:
 * den läggs i historiken med `pushState`, så att bakåtknappen stänger den.
 * Stacken står i `history.state`, och bara det översta lagret i URL:en
 * (`&konto=`/`&ver=`). Ett vybyte stänger lagret.
 */

export interface DetaljVarde {
  stack: readonly Detalj[];
  oppna: (mal: RadMal) => void;
  bakat: () => void;
  stang: () => void;
}

const DetaljKontext = createContext<DetaljVarde | null>(null);

/** `null` utanför skalet: då är raderna text, inte knappar. */
export const useDetalj = () => useContext(DetaljKontext);

export const DetaljProvider = DetaljKontext.Provider;

/** Det `history.state` bär: lagren, och om posten är en som skalet lagt dit. */
interface Historik {
  bokDetalj?: Detalj[];
  bokPushad?: boolean;
}

const historik = (): Historik =>
  typeof window === "undefined" ? {} : ((window.history.state as Historik | null) ?? {});

/**
 * Stacken och historiken. `url` bygger adressen för en stack; `gaTillVy`
 * tar en rad som leder till en annan vy (Årets resultat → Resultaträkning).
 */
export function useDetaljHistorik({
  start,
  url,
  gaTillVy,
}: {
  start: Detalj | null;
  url: (stack: readonly Detalj[]) => string;
  gaTillVy: (key: ViewKey) => void;
}): DetaljVarde {
  const [stack, setStack] = useState<Detalj[]>(() => historik().bokDetalj ?? (start ? [start] : []));

  useEffect(() => {
    const vidBakat = (e: PopStateEvent) => setStack((e.state as Historik | null)?.bokDetalj ?? []);
    window.addEventListener("popstate", vidBakat);
    return () => window.removeEventListener("popstate", vidBakat);
  }, []);

  const oppna = useCallback(
    (mal: RadMal) => {
      if (mal.typ === "vy") {
        gaTillVy(mal.key);
        return;
      }
      const overst = stack[stack.length - 1];
      if (overst && sammaDetalj(overst, mal)) return;
      const ny = [...stack, mal];
      window.history.pushState({ ...historik(), bokDetalj: ny, bokPushad: true }, "", url(ny));
      setStack(ny);
    },
    [stack, url, gaTillVy]
  );

  const bakat = useCallback(() => {
    // Ett lager som skalet lagt i historiken stängs med historiken, så att
    // bakåtknappen och länken gör samma sak. Ett lager ur en inklistrad
    // länk har ingen post att gå tillbaka till.
    if (historik().bokPushad) {
      window.history.back();
      return;
    }
    const ny = stack.slice(0, -1);
    window.history.replaceState({ ...historik(), bokDetalj: ny }, "", url(ny));
    setStack(ny);
  }, [stack, url]);

  const stang = useCallback(() => setStack((s) => (s.length === 0 ? s : [])), []);

  return useMemo(() => ({ stack, oppna, bakat, stang }), [stack, oppna, bakat, stang]);
}
