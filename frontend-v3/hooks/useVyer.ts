"use client";

import { useQuery } from "@tanstack/react-query";
import type { OverviewFiscalYear } from "@/lib/skal/api";
import { betalaApi, faktureringVy, lonerVy } from "@/lib/skal/betala";
import { VERIFIKATIONER_ANTAL, balansVy, bockerApi, resultatVy, verifikationerVy } from "@/lib/skal/bocker";
import { atgarderVy, bokslutApi, rapporterVy } from "@/lib/skal/bokslut";
import { FEL_VY, INGET_AR_VY, LADDAR_VY, type VyData } from "@/lib/skal/vydata";
import type { Sidnyckel, ViewKey } from "@/lib/skal/vyer";

export interface VyInnehallData {
  data: VyData;
  laddar: boolean;
}

interface Fraga<T> {
  data: T | undefined;
  isError: boolean;
}

function vy<T extends unknown[]>(
  fragor: { [K in keyof T]: Fraga<T[K]> },
  bygg: (...data: T) => VyData
): VyInnehallData {
  if (fragor.some((f) => f.isError)) return { data: FEL_VY, laddar: false };
  if (fragor.some((f) => f.data === undefined)) return { data: LADDAR_VY, laddar: true };
  return { data: bygg(...(fragor.map((f) => f.data) as T)), laddar: false };
}

/**
 * Alla sju vyernas innehåll, ur API:t.
 *
 * Frågorna går bara för sidan som visas. Böckernas vyer gäller räkenskapsåret
 * som översikten pekar ut; `ar === undefined` betyder att översikten inte har
 * svarat än, `null` att det inte finns något räkenskapsår.
 */
export function useVyer(
  ar: OverviewFiscalYear | null | undefined,
  sida: Sidnyckel
): Record<ViewKey, VyInnehallData> {
  const id = ar?.id ?? "";
  const bocker = sida === "bocker" && !!id;
  const betala = sida === "betala";
  const bokslut = sida === "bokslut";
  const staleTime = 60 * 1000;

  const balans = useQuery({
    queryKey: ["skal", "balans", id],
    queryFn: () => bockerApi.getBalansrakning(id),
    enabled: bocker,
    staleTime,
  });
  const resultat = useQuery({
    queryKey: ["skal", "resultat", id],
    queryFn: () => bockerApi.getResultatrakning(id),
    enabled: bocker,
    staleTime,
  });
  const postade = useQuery({
    queryKey: ["skal", "verifikationer", id, "posted"],
    queryFn: () => bockerApi.getVerifikationer(id, "posted", VERIFIKATIONER_ANTAL),
    enabled: bocker,
    staleTime,
  });
  const utkast = useQuery({
    queryKey: ["skal", "verifikationer", id, "draft"],
    queryFn: () => bockerApi.getVerifikationer(id, "draft"),
    enabled: bocker,
    staleTime,
  });
  const fakturor = useQuery({
    queryKey: ["skal", "fakturor"],
    queryFn: betalaApi.getFakturor,
    enabled: betala,
    staleTime,
  });
  const loner = useQuery({
    queryKey: ["skal", "lonekorningar"],
    queryFn: betalaApi.getLonekorningar,
    enabled: betala,
    staleTime,
  });
  const rakenskapsar = useQuery({
    queryKey: ["skal", "rakenskapsar"],
    queryFn: bokslutApi.getRakenskapsar,
    enabled: bokslut,
    staleTime,
  });
  const avvikelser = useQuery({
    queryKey: ["skal", "avvikelser"],
    queryFn: bokslutApi.getAvvikelser,
    enabled: bokslut,
    staleTime,
  });

  const utanAr: VyInnehallData | null =
    ar === null ? { data: INGET_AR_VY, laddar: false } : ar === undefined ? { data: LADDAR_VY, laddar: true } : null;

  return {
    "bocker.balans": utanAr ?? vy([balans, resultat], (b, r) => balansVy(ar!, b, r)),
    "bocker.resultat": utanAr ?? vy([resultat], (r) => resultatVy(ar!, r)),
    "bocker.verifikationer": utanAr ?? vy([postade, utkast], (p, u) => verifikationerVy(ar!, p, u)),
    "betala.fakturering": vy([fakturor], faktureringVy),
    "betala.loner": vy([loner], lonerVy),
    "bokslut.rapporter": vy([rakenskapsar], rapporterVy),
    "bokslut.atgarder": vy([avvikelser], atgarderVy),
  };
}
