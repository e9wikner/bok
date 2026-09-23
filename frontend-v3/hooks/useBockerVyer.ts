"use client";

import { useQuery } from "@tanstack/react-query";
import type { OverviewFiscalYear } from "@/lib/skal/api";
import {
  FEL_VY,
  INGET_AR_VY,
  LADDAR_VY,
  VERIFIKATIONER_ANTAL,
  balansVy,
  bockerApi,
  resultatVy,
  verifikationerVy,
} from "@/lib/skal/bocker";
import type { VyData } from "@/lib/skal/mock";

export interface BockerVy {
  data: VyData;
  laddar: boolean;
}

type BockerVyer = Record<"bocker.balans" | "bocker.resultat" | "bocker.verifikationer", BockerVy>;

/**
 * Böckernas tre vyer för räkenskapsåret som översikten pekar ut.
 *
 * Frågorna går bara när `aktiv` är sann, alltså när Böcker är sidan som
 * visas: balansräkningen läser hela liggaren på servern.
 */
export function useBockerVyer(ar: OverviewFiscalYear | null | undefined, aktiv: boolean): BockerVyer {
  const id = ar?.id ?? "";
  const pa = aktiv && !!id;
  const staleTime = 60 * 1000;

  const balans = useQuery({
    queryKey: ["skal", "balans", id],
    queryFn: () => bockerApi.getBalansrakning(id),
    enabled: pa,
    staleTime,
  });
  const resultat = useQuery({
    queryKey: ["skal", "resultat", id],
    queryFn: () => bockerApi.getResultatrakning(id),
    enabled: pa,
    staleTime,
  });
  const postade = useQuery({
    queryKey: ["skal", "verifikationer", id, "posted"],
    queryFn: () => bockerApi.getVerifikationer(id, "posted", VERIFIKATIONER_ANTAL),
    enabled: pa,
    staleTime,
  });
  const utkast = useQuery({
    queryKey: ["skal", "verifikationer", id, "draft"],
    queryFn: () => bockerApi.getVerifikationer(id, "draft"),
    enabled: pa,
    staleTime,
  });

  function vy(fragor: { isError: boolean }[], klar: boolean, bygg: () => VyData): BockerVy {
    if (ar === null) return { data: INGET_AR_VY, laddar: false };
    if (fragor.some((f) => f.isError)) return { data: FEL_VY, laddar: false };
    if (!ar || !klar) return { data: LADDAR_VY, laddar: true };
    return { data: bygg(), laddar: false };
  }

  return {
    "bocker.balans": vy([balans, resultat], !!balans.data && !!resultat.data, () =>
      balansVy(ar!, balans.data!, resultat.data!)
    ),
    "bocker.resultat": vy([resultat], !!resultat.data, () => resultatVy(ar!, resultat.data!)),
    "bocker.verifikationer": vy([postade, utkast], !!postade.data && !!utkast.data, () =>
      verifikationerVy(ar!, postade.data!, utkast.data!)
    ),
  };
}
