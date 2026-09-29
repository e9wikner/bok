"use client";

import { useCallback } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { BESLUT_GRANS, beslutStatusNyckel } from "@/hooks/useBeslut";
import { FORSLAG_GRANS, forslagNyckel } from "@/hooks/useForslag";
import { useLasning } from "@/hooks/useLasning";
import { usePostningar } from "@/hooks/usePostningar";
import { VOUCHERS_NYCKEL, hamtaBeslut, hamtaForslag } from "@/lib/chattyta/api";
import { KOPPLINGAR_NYCKEL, type Koppling } from "@/lib/chattyta/kopplingar";
import type { OverviewFiscalYear } from "@/lib/skal/api";
import { betalaApi, faktureringVy, lonerVy } from "@/lib/skal/betala";
import {
  VERIFIKATIONER_ANTAL,
  balansVy,
  bockerApi,
  nastaSida,
  resultatVy,
  slaSamman,
  verifikationerVy,
} from "@/lib/skal/bocker";
import { atgarderVy, bokslutApi, rapporterVy } from "@/lib/skal/bokslut";
import { lasApi } from "@/lib/skal/las";
import { FEL_VY, INGET_AR_VY, LADDAR_VY, type VyData } from "@/lib/skal/vydata";
import type { Sidnyckel, ViewKey } from "@/lib/skal/vyer";

/** Dagens datum i lokal tid, `YYYY-MM-DD`. */
function idag(): string {
  const d = new Date();
  const tva = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${tva(d.getMonth() + 1)}-${tva(d.getDate())}`;
}

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
  // Under `VOUCHERS_NYCKEL`, så att `view.changed` (`useTrad`) och en
  // postning (`usePostaUtkast`) når listorna utan att känna till vyn.
  // Postade utan dem som saknar underlag: de står i sin egen sektion, och
  // en verifikation visas på ett ställe (SPEC-flode-underlag.md §10.4).
  //
  // Sida för sida (SPEC-lasbarhet.md §4.5): nästa sida när listans slut syns.
  // En invalidering hämtar om alla hämtade sidor, från offset 0.
  const postadeSidor = useInfiniteQuery({
    queryKey: [...VOUCHERS_NYCKEL, "skal", id, "posted"],
    queryFn: ({ pageParam }) =>
      bockerApi.getVerifikationer(id, "posted", VERIFIKATIONER_ANTAL, false, pageParam),
    initialPageParam: 0,
    getNextPageParam: (sida, _sidor, offset) => nastaSida(sida, offset),
    enabled: bocker,
    staleTime,
  });
  const postade = {
    data: postadeSidor.data ? slaSamman(postadeSidor.data.pages) : undefined,
    isError: postadeSidor.isError,
  };
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = postadeSidor;
  const hamtaFler = useCallback(() => {
    // Utan spärren avbryter ett andra anrop det pågående och börjar om.
    if (hasNextPage && !isFetchingNextPage) void fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);
  const saknar = useQuery({
    queryKey: [...VOUCHERS_NYCKEL, "skal", id, "saknar"],
    queryFn: () => bockerApi.getSaknarUnderlag(id),
    enabled: bocker,
    staleTime,
  });
  const utkast = useQuery({
    queryKey: [...VOUCHERS_NYCKEL, "skal", id, "draft"],
    queryFn: () => bockerApi.getVerifikationer(id, "draft"),
    enabled: bocker,
    staleTime,
  });
  // Väntar på beslut (flode-verifikationer §11.1). Samma nycklar och samma
  // cachade form som trådens `useBeslut`/`useForslag` — en fråga per vy, som
  // korten och vyn delar; bara `select` skiljer, och den är per observatör.
  const verifikationer = "bocker.verifikationer";
  const beslut = useQuery({
    queryKey: beslutStatusNyckel(verifikationer),
    queryFn: () => hamtaBeslut({ viewKey: verifikationer, status: "all", limit: BESLUT_GRANS }),
    enabled: bocker,
    staleTime,
  });
  const forslag = useQuery({
    queryKey: forslagNyckel(verifikationer),
    queryFn: () => hamtaForslag({ viewKey: verifikationer, status: "all", limit: FORSLAG_GRANS }),
    enabled: bocker,
    staleTime,
  });
  // Månaderna i Postade, med sina lås. Frågan väntas in, men ett fel fäller
  // inte vyn: då står de postade i en enda sektion som förut.
  const perioder = useQuery({
    queryKey: ["skal", "perioder", id],
    queryFn: () => lasApi.getPerioder(id),
    enabled: bocker,
    staleTime,
  });
  const perioderFraga = {
    data: perioder.isError ? { periods: [] } : perioder.data,
    isError: false,
  };
  const lasning = useLasning();
  const postningar = usePostningar();
  // `Nyss kopplad` (§10.4): klientens, som postningarna — ingen fråga går.
  const { data: kopplingar } = useQuery<Koppling[]>({
    queryKey: KOPPLINGAR_NYCKEL,
    enabled: false,
    staleTime: Infinity,
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
    "bocker.verifikationer":
      utanAr ??
      vy([postade, utkast, beslut, forslag, saknar, perioderFraga], (p, u, b, f, s, per) => ({
        ...verifikationerVy(
          ar!,
          p,
          u,
          {
            beslut: b.decisions,
            forslag: f.drafts,
            postningar,
            saknar: s,
            kopplingar: kopplingar ?? [],
          },
          {
            perioder: per.periods,
            las: lasning.period,
            idag: idag(),
            harFler: hasNextPage,
          }
        ),
        harFler: hasNextPage,
        hamtaFler,
      })),
    "betala.fakturering": vy([fakturor], faktureringVy),
    "betala.loner": vy([loner], lonerVy),
    "bokslut.rapporter": vy([rakenskapsar], (r) => rapporterVy(r, lasning.ar)),
    "bokslut.atgarder": vy([avvikelser], atgarderVy),
  };
}
