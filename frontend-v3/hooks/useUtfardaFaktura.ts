"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  BESLUT_NYCKEL,
  DRAFTS_NYCKEL,
  FAKTUROR_NYCKEL,
  OVERVIEW_NYCKEL,
  VOUCHERS_NYCKEL,
  utfardaFaktura,
  type UtfardadFaktura,
} from "@/lib/chattyta/api";
import {
  startaUtfardande,
  taBortUtfardande,
  utfardandeKlart,
  type UtfardandeForslag,
} from "@/lib/chattyta/utfardanden";

/** Så länge `Utfärdar…` står innan knappen säger `Utfärdar fortfarande…` (§7.1). */
export const UTFARDAR_FORTFARANDE_MS = 3000;

/**
 * `Utfärda` för ett fakturaförslag (SPEC-fakturering-f1.md §7.1).
 *
 * - `redo`: inget tryck än.
 * - `utfardar`: i flykt. Knappen är borta (panelen: en dubbel faktura är ett
 *   kundproblem); raden i vyn står som `utfärdas…`.
 * - `utfardad`: `201`, eller `409 draft_already_issued` — samma faktura.
 * - `ersatt`: `422 draft_rejected`, förslaget hann ersättas (§5.4).
 * - `fel`: servern vägrade och skrev ett felinlägg (§9). `kvar` säger om
 *   `Utfärda` står kvar (beslut 8).
 * - `natverk`: vi vet inte om servern hann; ett nytt tryck är ofarligt, för
 *   ett utkast kan bara ge en faktura.
 */
export type UtfardaLage =
  | { lage: "redo" }
  | { lage: "utfardar" }
  | { lage: "utfardad"; faktura: UtfardadFaktura | null }
  | { lage: "ersatt" }
  | { lage: "fel"; kod: string; kvar: boolean }
  | { lage: "natverk" };

export function useUtfardaFaktura(draftId: string, forslag: UtfardandeForslag | null) {
  const qc = useQueryClient();
  const [lage, setLage] = useState<UtfardaLage>({ lage: "redo" });
  const [langsam, setLangsam] = useState(false);
  const upptagen = useRef(false);
  const monterad = useRef(true);

  useEffect(() => {
    monterad.current = true;
    return () => {
      monterad.current = false;
    };
  }, []);

  const utfardar = lage.lage === "utfardar";
  useEffect(() => {
    if (!utfardar) {
      setLangsam(false);
      return;
    }
    const t = setTimeout(() => setLangsam(true), UTFARDAR_FORTFARANDE_MS);
    return () => clearTimeout(t);
  }, [utfardar]);

  const utfarda = useCallback(() => {
    if (upptagen.current) return;
    upptagen.current = true;
    setLage({ lage: "utfardar" });
    startaUtfardande(qc, draftId, forslag);

    void (async () => {
      let slut: UtfardaLage;
      try {
        const utfall = await utfardaFaktura(draftId);
        switch (utfall.utfall) {
          case "utfardad":
            utfardandeKlart(qc, draftId, utfall.invoice_id);
            slut = { lage: "utfardad", faktura: utfall.faktura };
            break;
          case "ersatt":
            taBortUtfardande(qc, draftId);
            slut = { lage: "ersatt" };
            break;
          case "fel":
            taBortUtfardande(qc, draftId);
            slut = { lage: "fel", kod: utfall.kod, kvar: utfall.kvar };
            break;
          case "natverk":
            taBortUtfardande(qc, draftId);
            slut = { lage: "natverk" };
            break;
        }
      } catch {
        taBortUtfardande(qc, draftId);
        slut = { lage: "natverk" };
      }

      // Förslagets rad kan ha ändrats: utfärdad, ersatt eller med felkod.
      void qc.invalidateQueries({ queryKey: DRAFTS_NYCKEL });
      if (slut.lage === "utfardad") {
        void qc.invalidateQueries({ queryKey: FAKTUROR_NYCKEL });
        void qc.invalidateQueries({ queryKey: OVERVIEW_NYCKEL });
        void qc.invalidateQueries({ queryKey: BESLUT_NYCKEL });
        void qc.invalidateQueries({ queryKey: VOUCHERS_NYCKEL });
      }
      if (!monterad.current) return;
      if (slut.lage === "natverk" || (slut.lage === "fel" && slut.kvar)) upptagen.current = false;
      setLage(slut);
    })();
  }, [draftId, forslag, qc]);

  return { lage, langsam: utfardar && langsam, utfarda };
}

/** Felradens mening per kod (§9). Felinlägget i tråden bär orsaken i detalj. */
export function utfardaFelText(kod: string): string {
  switch (kod) {
    case "number_taken":
      return "Numret är redan använt. Be agenten föreslå nästa.";
    case "period_locked":
      return "Perioden är låst. Lås upp den och tryck igen, eller be agenten ändra datumet.";
    case "company_info_incomplete":
      return "Företagsuppgifter saknas. Fyll i dem under Inställningar och tryck igen.";
    default:
      return `Fakturan kunde inte utfärdas (${kod}). Ingenting är bokfört.`;
  }
}
