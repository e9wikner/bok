"use client";

import { skipToken, useQuery } from "@tanstack/react-query";
import { POSTNINGAR_NYCKEL, type Postning } from "@/lib/chattyta/postningar";

const INGA: readonly Postning[] = [];

/**
 * De optimistiska raderna (flode-verifikationer §11.2), som `usePostaUtkast`
 * skriver dem. Ingen fråga går någonsin: `queryFn` är `skipToken`,
 * och hooken prenumererar bara på cachen.
 */
export function usePostningar(): readonly Postning[] {
  const { data } = useQuery<Postning[]>({
    queryKey: POSTNINGAR_NYCKEL,
    queryFn: skipToken,
    staleTime: Infinity,
  });
  return data ?? INGA;
}
