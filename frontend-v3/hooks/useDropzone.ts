"use client";

import { useQuery } from "@tanstack/react-query";
import { DROPZONE_NYCKEL, type DropzoneOversikt, dropzoneApi } from "@/lib/skal/dropzone";

/** Dropzonens mappar och filer (`GET /api/v1/intake/dropzone`). */
export function useDropzoneOversikt(enabled = true) {
  return useQuery({
    queryKey: DROPZONE_NYCKEL,
    queryFn: dropzoneApi.getOversikt,
    enabled,
    staleTime: 5 * 1000,
    // Tätare medan något väntar på skannern, så att filen syns flytta sig.
    refetchInterval: (q) => {
      const d = q.state.data as DropzoneOversikt | undefined;
      return (d?.pending?.length ?? 0) > 0 ? 5 * 1000 : 30 * 1000;
    },
  });
}
