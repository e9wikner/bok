"use client";

import { useQuery } from "@tanstack/react-query";
import { UTFARDANDEN_NYCKEL, type Utfardande } from "@/lib/chattyta/utfardanden";

const INGA: readonly Utfardande[] = [];

/** De optimistiska utfärdandena (SPEC-fakturering-f1.md §10.2). Ingen fråga går. */
export function useUtfardanden(): readonly Utfardande[] {
  const { data } = useQuery<Utfardande[]>({
    queryKey: UTFARDANDEN_NYCKEL,
    enabled: false,
    staleTime: Infinity,
  });
  return data ?? INGA;
}
