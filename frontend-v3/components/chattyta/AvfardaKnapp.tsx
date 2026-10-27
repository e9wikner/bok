"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { avfardaBeslut, BESLUT_NYCKEL } from "@/lib/chattyta/api";

/**
 * `Avfärda` på ett öppet beslut: ett tryck, en bekräftelse, och beslutet
 * lämnar kön (`POST /decisions/{id}/dismiss`). Inget skrivs i tråden och
 * agenten startar inte. Beslutslistan hämtas om, så kortet, raden och märket
 * visar serverns nya läge utan att knappen själv påstår något.
 */
export function AvfardaKnapp({ decisionId, onKlar }: { decisionId: string; onKlar?: () => void }) {
  const queryClient = useQueryClient();
  const [lage, setLage] = useState<"redo" | "bekrafta" | "skickar" | "fel">("redo");

  if (lage === "redo" || lage === "fel") {
    return (
      <button
        type="button"
        data-testid="avfarda"
        onClick={() => setLage("bekrafta")}
        className="text-[13px] text-bok-text-svag hover:text-bok-text"
      >
        {lage === "fel" ? "Gick inte, försök igen" : "Avfärda"}
      </button>
    );
  }

  return (
    <span className="flex items-baseline gap-[10px] text-[13px]">
      <span className="text-bok-text-dampad">Avfärda beslutet?</span>
      <button
        type="button"
        data-testid="avfarda-ja"
        disabled={lage === "skickar"}
        onClick={() => {
          setLage("skickar");
          avfardaBeslut(decisionId)
            .then(() => queryClient.invalidateQueries({ queryKey: BESLUT_NYCKEL }))
            .then(() => onKlar?.())
            .catch(() => setLage("fel"));
        }}
        className="font-medium text-bok-text hover:underline disabled:opacity-70"
      >
        {lage === "skickar" ? "Avfärdar…" : "Ja"}
      </button>
      {lage === "bekrafta" && (
        <button
          type="button"
          onClick={() => setLage("redo")}
          className="text-bok-text-svag hover:text-bok-text"
        >
          Avbryt
        </button>
      )}
    </span>
  );
}
