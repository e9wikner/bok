"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useDetalj } from "@/components/skal/DetaljKontext";
import { VyInnehall } from "@/components/skal/VyInnehall";
import { VOUCHERS_NYCKEL } from "@/lib/chattyta/api";
import type { OverviewFiscalYear } from "@/lib/skal/api";
import {
  type Detalj,
  type Huvudbok,
  type VerifikationDetalj,
  detaljApi,
  huvudbokTitel,
  huvudbokVy,
  verifikationTitel,
  verifikationVy,
} from "@/lib/skal/detalj";
import type { VyInnehallData } from "@/hooks/useVyer";
import { FEL_VY, LADDAR_VY } from "@/lib/skal/vydata";

/**
 * Detaljlagret: ett kontos huvudbok eller en verifikation, i läskolumnens
 * ställe (`lib/skal/detalj.ts`). Stacken och historiken: `DetaljKontext.tsx`.
 */

const huvudbokNyckel = (arId: string, kod: string) => [...VOUCHERS_NYCKEL, "skal", "huvudbok", arId, kod];
const verifikationNyckel = (id: string) => [...VOUCHERS_NYCKEL, "skal", "ver", id];

/**
 * Lagrets innehåll ur API:t. Under `VOUCHERS_NYCKEL`, så att en postning och
 * `view.changed` når huvudboken och verifikationen som de når listorna.
 */
function useDetaljData(
  detalj: Detalj,
  ar: OverviewFiscalYear | null | undefined
): VyInnehallData & { titel: string } {
  const arId = ar?.id ?? "";
  const huvudbok = useQuery({
    queryKey: huvudbokNyckel(arId, detalj.typ === "konto" ? detalj.kod : ""),
    queryFn: () => detaljApi.getHuvudbok(detalj.typ === "konto" ? detalj.kod : "", arId),
    enabled: detalj.typ === "konto" && !!arId,
    staleTime: 60 * 1000,
  });
  const verifikation = useQuery({
    queryKey: verifikationNyckel(detalj.typ === "ver" ? detalj.id : ""),
    queryFn: () => detaljApi.getVerifikation(detalj.typ === "ver" ? detalj.id : ""),
    enabled: detalj.typ === "ver",
    staleTime: 60 * 1000,
  });

  if (detalj.typ === "konto") {
    const titel = huvudbokTitel(detalj.kod, huvudbok.data?.account_name);
    if (huvudbok.isError) return { titel, data: FEL_VY, laddar: false };
    if (!huvudbok.data || !ar) return { titel, data: LADDAR_VY, laddar: true };
    return { titel, data: huvudbokVy(ar, huvudbok.data), laddar: false };
  }
  const titel = verifikation.data ? verifikationTitel(verifikation.data) : "Verifikation";
  if (verifikation.isError) return { titel, data: FEL_VY, laddar: false };
  if (!verifikation.data) return { titel, data: LADDAR_VY, laddar: true };
  return { titel, data: verifikationVy(verifikation.data), laddar: false };
}

/** Tillbakalänkens text: lagret under, med namnet om det redan är hämtat. */
function useForegaende(foregaende: Detalj | undefined, vyTitel: string, arId: string): string {
  const queryClient = useQueryClient();
  if (!foregaende) return vyTitel;
  if (foregaende.typ === "konto") {
    const h = queryClient.getQueryData<Huvudbok>(huvudbokNyckel(arId, foregaende.kod));
    return huvudbokTitel(foregaende.kod, h?.account_name);
  }
  const v = queryClient.getQueryData<VerifikationDetalj>(verifikationNyckel(foregaende.id));
  return v ? verifikationTitel(v) : "Verifikation";
}

/** Lagret i läskolumnens ställe, med en tillbakalänk till det under. */
export function DetaljLager({
  vyTitel,
  ar,
  variant = "desktop",
}: {
  /** Den underliggande vyns titel, tillbakalänken från det första lagret. */
  vyTitel: string;
  ar: OverviewFiscalYear | null | undefined;
  variant?: "desktop" | "mobil";
}) {
  const detalj = useDetalj();
  const stack = detalj?.stack ?? [];
  const overst = stack[stack.length - 1];
  const foregaende = useForegaende(stack[stack.length - 2], vyTitel, ar?.id ?? "");
  const bakat = detalj?.bakat;

  // Escape stänger lagret, men inte medan någon skriver i chatten.
  useEffect(() => {
    if (!bakat) return;
    const vidTangent = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      const mal = e.target as HTMLElement | null;
      if (mal && (mal.tagName === "INPUT" || mal.tagName === "TEXTAREA" || mal.isContentEditable)) return;
      bakat();
    };
    window.addEventListener("keydown", vidTangent);
    return () => window.removeEventListener("keydown", vidTangent);
  }, [bakat]);

  if (!overst || !bakat) return null;
  return <DetaljInnehall detalj={overst} ar={ar} foregaende={foregaende} onBakat={bakat} variant={variant} />;
}

function DetaljInnehall({
  detalj,
  ar,
  foregaende,
  onBakat,
  variant,
}: {
  detalj: Detalj;
  ar: OverviewFiscalYear | null | undefined;
  foregaende: string;
  onBakat: () => void;
  variant: "desktop" | "mobil";
}) {
  const { titel, data, laddar } = useDetaljData(detalj, ar);
  return (
    <VyInnehall
      vy={{ titel }}
      data={data}
      laddar={laddar}
      variant={variant}
      tillbaka={{ text: foregaende, onClick: onBakat }}
    />
  );
}
