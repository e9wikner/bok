"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { BESLUT_NYCKEL, DRAFTS_NYCKEL, kastaUtkast, VOUCHERS_NYCKEL } from "@/lib/chattyta/api";

/**
 * `Kasta utkast` under ett utkasts detalj: ett tryck, en bekräftelse, och
 * utkastet tas bort (`POST /vouchers/{id}/discard`). Det hade inget nummer,
 * så ingen lucka uppstår. Listorna hämtas om och lagret stängs (`onKlar`).
 * Ett fel står kvar under knappen, med serverns skäl i klartext.
 */
export function KastaUtkast({ voucherId, onKlar }: { voucherId: string; onKlar: () => void }) {
  const queryClient = useQueryClient();
  const [lage, setLage] = useState<"redo" | "bekrafta" | "skickar">("redo");
  const [fel, setFel] = useState<string | null>(null);

  const kasta = async () => {
    if (lage === "skickar") return;
    setLage("skickar");
    const orsak = await kastaUtkast(voucherId);
    if (orsak) {
      setFel(orsak);
      setLage("redo");
      return;
    }
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: VOUCHERS_NYCKEL }),
      queryClient.invalidateQueries({ queryKey: DRAFTS_NYCKEL }),
      queryClient.invalidateQueries({ queryKey: BESLUT_NYCKEL }),
    ]);
    onKlar();
  };

  return (
    <div className="pt-4">
      {lage === "redo" ? (
        <button
          type="button"
          data-testid="kasta-utkast"
          onClick={() => {
            setFel(null);
            setLage("bekrafta");
          }}
          className="min-h-[40px] rounded-[8px] border border-bok-kant bg-bok-yta px-[14px] text-[14px] text-bok-text hover:bg-bok-yta-svag focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-bok-lank"
        >
          Kasta utkast
        </button>
      ) : (
        <span className="flex min-h-[40px] flex-wrap items-center gap-[10px] text-[14px]">
          <span className="text-bok-text-dampad">Kasta utkastet? Det går inte att ångra.</span>
          <button
            type="button"
            data-testid="kasta-utkast-ja"
            aria-disabled={lage === "skickar" ? true : undefined}
            onClick={() => void kasta()}
            className="font-medium text-bok-text hover:underline aria-disabled:opacity-70"
          >
            {lage === "skickar" ? "Kastar…" : "Ja, kasta"}
          </button>
          {lage === "bekrafta" && (
            <button type="button" onClick={() => setLage("redo")} className="text-bok-text-svag hover:text-bok-text">
              Avbryt
            </button>
          )}
        </span>
      )}
      {fel && (
        <p
          role="status"
          data-testid="kasta-utkast-fel"
          className="m-0 mt-[10px] rounded-[8px] border border-bok-fel-kant bg-bok-fel-yta px-[12px] py-[8px] text-[13px] leading-[1.5] text-bok-fel-text"
        >
          {fel}
        </p>
      )}
    </div>
  );
}
