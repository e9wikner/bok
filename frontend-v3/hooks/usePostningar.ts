"use client";

import { useQuery } from "@tanstack/react-query";
import { POSTNINGAR_NYCKEL, type Postning } from "@/lib/chattyta/postningar";

const INGA: readonly Postning[] = [];

/**
 * De optimistiska raderna (flode-verifikationer §11.2), som `usePostaUtkast`
 * skriver dem. Ingen fråga går någonsin: `enabled: false` och ingen
 * `queryFn` — hooken prenumererar bara på cachen.
 */
export function usePostningar(): readonly Postning[] {
  const { data } = useQuery<Postning[]>({
    queryKey: POSTNINGAR_NYCKEL,
    enabled: false,
    staleTime: Infinity,
  });
  return data ?? INGA;
}
