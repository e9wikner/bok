"use client";

import { useCallback } from "react";
import { skipToken, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useDropzoneOversikt } from "@/hooks/useDropzone";
import { BESLUT_GRANS, beslutStatusNyckel } from "@/hooks/useBeslut";
import { FORSLAG_GRANS, forslagNyckel } from "@/hooks/useForslag";
import { useLasning } from "@/hooks/useLasning";
import { usePostningar } from "@/hooks/usePostningar";
import { useUtfardanden } from "@/hooks/useUtfardanden";
import { FAKTUROR_NYCKEL, LONER_NYCKEL, VOUCHERS_NYCKEL, hamtaBeslut, hamtaForslag } from "@/lib/chattyta/api";
import { KOPPLINGAR_NYCKEL, type Koppling } from "@/lib/chattyta/kopplingar";
import type { OverviewFiscalYear } from "@/lib/skal/api";
import { betalaApi, betalaVantar, faktureringVy, lonerVy } from "@/lib/skal/betala";
import {
  STANDARDSORTERING,
  VERIFIKATIONER_ANTAL,
  arStandardsortering,
  balansVy,
  bockerApi,
  nastaSida,
  resultatVy,
  slaSamman,
  type Sortering,
  verifikationerVy,
} from "@/lib/skal/bocker";
import { atgarderVy, bokslutApi, bokslutNyckel, bokslutStatus } from "@/lib/skal/bokslut";
import { lasApi } from "@/lib/skal/las";
import { dropzoneStatus } from "@/lib/skal/dropzone";
import { ANSTALLDA_NYCKEL, anstalldaApi, anstalldaStatus } from "@/lib/skal/anstallda";
import { FORETAGET_NYCKEL, foretagetApi, foretagetStatus } from "@/lib/skal/foretaget";
import { KONTOPLAN_NYCKEL, kontoplanApi, kontoplanStatus } from "@/lib/skal/kontoplan";
import { REVISIONSLOGG_NYCKEL, revisionsloggApi, revisionsloggStatus } from "@/lib/skal/revisionslogg";
import { sokVy } from "@/lib/skal/sok";
import { FEL_VY, INGET_AR_VY, LADDAR_VY, type VyData } from "@/lib/skal/vydata";
import type { Sidnyckel, Vynyckel } from "@/lib/skal/vyer";

/** En vy med egen komponent: bara statusraden, till headern. */
function statusrad(st: { text: string; lage: VyData["lage"] }): { data: VyData; laddar: boolean } {
  return { data: { ...LADDAR_VY, status: st.text, lage: st.lage }, laddar: false };
}

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
 * Alla vyernas innehåll, ur API:t.
 *
 * Frågorna går bara för sidan som visas. Böckernas, Faktureringens och
 * Lönernas vyer gäller årsväljarens räkenskapsår; `ar === undefined` betyder
 * att översikten inte har svarat än, `null` att det inte finns något
 * räkenskapsår.
 *
 * `sokterm` filtrerar Verifikationer (`lib/skal/sok.ts`). Med en sökterm
 * hämtas årets alla postade, så att sökningen inte stannar vid de sidor
 * som hunnit skrollas fram; tills de har svarat söks de hämtade sidorna.
 *
 * `sortering` ordnar Postade. Annat än standardordningen (datum, senaste
 * först) hämtar också årets alla postade och sorterar dem i klienten — en
 * sida i taget i fel ordning vore en lista med hål.
 */
export function useVyer(
  ar: OverviewFiscalYear | null | undefined,
  sida: Sidnyckel,
  sokterm = "",
  sortering: Sortering = STANDARDSORTERING
): Record<Vynyckel, VyInnehallData> {
  const id = ar?.id ?? "";
  const bocker = sida === "bocker" && !!id;
  const betala = sida === "betala" && !!id;
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
  // en verifikation visas på ett ställe.
  //
  // Sida för sida: nästa sida när listans slut syns.
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
  const soker = sokterm.trim() !== "";
  const helaListan = soker || !arStandardsortering(sortering);
  const allaPostade = useQuery({
    queryKey: [...VOUCHERS_NYCKEL, "skal", id, "posted", "alla"],
    queryFn: () => bockerApi.getVerifikationer(id, "posted", undefined, false),
    enabled: bocker && helaListan,
    staleTime,
  });
  const postade = {
    data:
      helaListan && allaPostade.data
        ? allaPostade.data
        : postadeSidor.data
          ? slaSamman(postadeSidor.data.pages)
          : undefined,
    isError: postadeSidor.isError,
  };
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = postadeSidor;
  const hamtaFler = useCallback(() => {
    // Utan spärren avbryter ett andra anrop det pågående och börjar om.
    if (hasNextPage && !isFetchingNextPage) void fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);
  // Dropzonen gäller inget år; frågan går när Böcker visas.
  const dropzone = useDropzoneOversikt(sida === "bocker");
  // De anställda gäller inget år; frågan går när Betala visas. Samma
  // nyckel som `AnstalldaVy`, så att det är en fråga.
  const anstallda = useQuery({
    queryKey: ANSTALLDA_NYCKEL,
    queryFn: anstalldaApi.lista,
    enabled: sida === "betala",
    staleTime: 30 * 1000,
  });
  // Kontoplanen gäller inget år; frågan går när Böcker visas. Samma nyckel
  // som `KontoplanVy`.
  const kontoplan = useQuery({
    queryKey: KONTOPLAN_NYCKEL,
    queryFn: kontoplanApi.lista,
    enabled: sida === "bocker",
    staleTime: 10 * 60 * 1000,
  });
  // Företagets uppgifter gäller inget år; frågan går när Betala visas. Samma
  // nyckel som `ForetagetVy`.
  const foretaget = useQuery({
    queryKey: FORETAGET_NYCKEL,
    queryFn: foretagetApi.hamta,
    enabled: sida === "betala",
    staleTime: 60 * 1000,
  });
  // Revisionsloggens senaste händelse, till statusraden. Ingen sida av
  // `RevisionsloggVy`s lista: bara en händelse.
  const senasteLogg = useQuery({
    queryKey: [...REVISIONSLOGG_NYCKEL, "senaste"],
    queryFn: () => revisionsloggApi.sida([], 0, 1),
    enabled: sida === "bocker",
    staleTime: 30 * 1000,
  });
  const saknar = useQuery({
    queryKey: [...VOUCHERS_NYCKEL, "skal", id, "saknar"],
    queryFn: () => bockerApi.getSaknarUnderlag(id),
    enabled: bocker,
    staleTime,
  });
  // Kontoutdragens rader utan verifikation. Under `VOUCHERS_NYCKEL`: en
  // postning eller koppling kan ta bort en rad. Väntas inte in — ett fel
  // eller en fråga i flykt ger bara ingen sektion.
  const bank = useQuery({
    queryKey: [...VOUCHERS_NYCKEL, "skal", id, "bank"],
    queryFn: () => bockerApi.getOppnaBanktransaktioner(id),
    enabled: bocker,
    staleTime,
  });
  const utkast = useQuery({
    queryKey: [...VOUCHERS_NYCKEL, "skal", id, "draft"],
    queryFn: () => bockerApi.getVerifikationer(id, "draft"),
    enabled: bocker,
    staleTime,
  });
  // Väntar på beslut (flode-verifikationer §11.1). Besluten är bara årets
  // (`fiscal_year_id`): ett beslut om ett underlag från ett annat år väntar
  // där, inte här. Nyckeln ligger under trådens `useBeslut`, så att varje
  // invalidering av `BESLUT_NYCKEL` når båda. Förslagen delar trådens fråga;
  // vyn visar bara dem vars utkast hör till året.
  const verifikationer = "bocker.verifikationer";
  const beslut = useQuery({
    queryKey: [...beslutStatusNyckel(verifikationer), id],
    queryFn: () =>
      hamtaBeslut({ viewKey: verifikationer, status: "all", limit: BESLUT_GRANS, fiscalYearId: id }),
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
    queryFn: skipToken,
    staleTime: Infinity,
  });
  // Under `FAKTUROR_NYCKEL`, så att ett utfärdande och `view.changed` når
  // dem.
  const fakturor = useQuery({
    queryKey: [...FAKTUROR_NYCKEL, "skal", id],
    queryFn: () => betalaApi.getFakturor(id),
    enabled: betala,
    staleTime,
  });
  // Verifikationer läser också Betalas väntande kort (`betalaVantar`): samma
  // frågor, så att ett svar i Löner eller ett utfärdande når båda vyerna.
  const betalaVantarFragor = betala || bocker;
  const fakturautkast = useQuery({
    queryKey: [...FAKTUROR_NYCKEL, "skal", "utkast"],
    queryFn: betalaApi.getFakturautkast,
    enabled: betalaVantarFragor,
    staleTime,
  });
  // Under trådens `useBeslut`/`useForslag`-nycklar, en fråga per vy. Besluten
  // är årets (`fiscal_year_id`); förslagen delar trådens fråga och vyn visar
  // bara dem vars utkast hör till året.
  const fakturering = "betala.fakturering";
  const faktureringBeslut = useQuery({
    queryKey: [...beslutStatusNyckel(fakturering), id],
    queryFn: () =>
      hamtaBeslut({ viewKey: fakturering, status: "all", limit: BESLUT_GRANS, fiscalYearId: id }),
    enabled: betala,
    staleTime,
  });
  const faktureringForslag = useQuery({
    queryKey: forslagNyckel(fakturering),
    queryFn: () => hamtaForslag({ viewKey: fakturering, status: "all", limit: FORSLAG_GRANS }),
    enabled: betalaVantarFragor,
    staleTime,
  });
  const utfardanden = useUtfardanden();
  // Under `LONER_NYCKEL`, så att `view.changed` efter en bokföring når dem.
  const loner = useQuery({
    queryKey: [...LONER_NYCKEL, "skal", id],
    queryFn: () => betalaApi.getLonekorningar(id),
    enabled: betala,
    staleTime,
  });
  // Årets lönekort, i Löner och i Verifikationers Väntar på beslut.
  const lonerVyKey = "betala.loner";
  const lonerBeslut = useQuery({
    queryKey: [...beslutStatusNyckel(lonerVyKey), id],
    queryFn: () =>
      hamtaBeslut({ viewKey: lonerVyKey, status: "all", limit: BESLUT_GRANS, fiscalYearId: id }),
    enabled: betalaVantarFragor,
    staleTime,
  });
  // Bokslutets delar ritas av `BokslutVy`, som läser samma fråga. Här
  // behövs bara statusraden, till sidhuvudet.
  const bokslutet = useQuery({
    queryKey: bokslutNyckel(id),
    queryFn: () => bokslutApi.getBokslut(id),
    enabled: bokslut && !!id,
    staleTime: 30 * 1000,
  });
  const avvikelser = useQuery({
    queryKey: ["skal", "avvikelser"],
    queryFn: bokslutApi.getAvvikelser,
    enabled: bokslut,
    staleTime,
  });

  const utanAr: VyInnehallData | null =
    ar === null ? { data: INGET_AR_VY, laddar: false } : ar === undefined ? { data: LADDAR_VY, laddar: true } : null;

  const bokslutsdel: VyInnehallData =
    utanAr ??
    vy([bokslutet], (b) => {
      const { text, lage } = bokslutStatus(b);
      return { lage, status: text, period: "", sektioner: [], fot: "" };
    });

  return {
    "bocker.balans": utanAr ?? vy([balans, resultat], (b, r) => balansVy(ar!, b, r)),
    "bocker.resultat": utanAr ?? vy([resultat], (r) => resultatVy(ar!, r)),
    "bocker.verifikationer":
      utanAr ??
      vy([postade, utkast, beslut, forslag, saknar, perioderFraga], (p, u, b, f, s, per) => {
        const harFler = hasNextPage && !(helaListan && allaPostade.data);
        const v = verifikationerVy(
          ar!,
          p,
          u,
          {
            beslut: b.decisions,
            forslag: f.drafts,
            postningar,
            saknar: s,
            kopplingar: kopplingar ?? [],
            bank: bank.data?.items,
            avstamning: bank.data?.reconciliation,
            // Ett fel eller en fråga i flykt fäller inte Verifikationer: då
            // står bara vyns egna rader där.
            andraVyer: betalaVantar({
              lonerBeslut: lonerBeslut.data?.decisions ?? [],
              faktureringForslag: faktureringForslag.data?.drafts ?? [],
              fakturautkast: fakturautkast.data?.drafts ?? [],
              ar: ar!,
            }),
          },
          {
            perioder: per.periods,
            las: lasning.period,
            idag: idag(),
            harFler,
          },
          sortering
        );
        return soker ? sokVy(v, sokterm) : { ...v, harFler, hamtaFler };
      }),
    "betala.fakturering":
      utanAr ??
      vy([fakturor, fakturautkast, faktureringBeslut, faktureringForslag], (f, u, b, fs) =>
        faktureringVy(f, { utkast: u.drafts, beslut: b.decisions, forslag: fs.drafts, utfardanden, ar: ar! })
      ),
    "betala.loner": utanAr ?? vy([loner, lonerBeslut], (l, b) => lonerVy(l, { beslut: b.decisions, ar: ar! })),
    "bokslut.rapporter": bokslutsdel,
    "bokslut.ink2": bokslutsdel,
    "bokslut.moms": bokslutsdel,
    "bokslut.arsredovisning": bokslutsdel,
    "bokslut.uppgifter": bokslutsdel,
    "bokslut.atgarder": vy([avvikelser], atgarderVy),
    // Dropzonen har sin egen komponent (`DropzoneVy`), som Bokslutets delar.
    // Här bara statusraden, till headern.
    "bocker.dropzone": {
      data: {
        ...LADDAR_VY,
        ...(() => {
          const st = dropzoneStatus(dropzone.data, dropzone.isError, dropzone.dataUpdatedAt);
          return { status: st.text, lage: st.lage };
        })(),
      },
      laddar: false,
    },
    // Kontoplanen har sin egen komponent (`KontoplanVy`); här bara statusraden.
    "bocker.kontoplan": statusrad(kontoplanStatus(kontoplan.data, kontoplan.isError)),
    "bocker.revisionslogg": statusrad(revisionsloggStatus(senasteLogg.data, senasteLogg.isError)),
    "betala.foretaget": statusrad(foretagetStatus(foretaget.data, foretaget.isError)),
    // Anställda har sin egen komponent (`AnstalldaVy`); här bara statusraden.
    "betala.anstallda": {
      data: {
        ...LADDAR_VY,
        ...(() => {
          const st = anstalldaStatus(anstallda.data, anstallda.isError);
          return { status: st.text, lage: st.lage };
        })(),
      },
      laddar: false,
    },
  };
}
