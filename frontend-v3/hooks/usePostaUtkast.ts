"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import {
  BESLUT_NYCKEL,
  OVERVIEW_NYCKEL,
  postaUtkast,
  type PostaUtfall,
  type VerifikationSvar,
} from "@/lib/chattyta/api";

/**
 * Postningens tillstånd för ett utkast (SPEC-chattyta.md §8, C12). Delas av
 * `VerifikationsForslag`s `Posta` och `FelKort`s `Försök igen` (C13, §9) —
 * båda går genom `postaUtkast`, alltså med samma härledda nyckel.
 *
 * Lägena, ett per slut i §8:s tabell:
 * - `redo`: inget tryck än.
 * - `postar`: i flykt, och även medan `request_in_flight` väntar ut
 *   `retry_after_ms` — för människan är det samma postning.
 * - `postad`: `200`, uppspelning och `409 already_posted`. `verifikation`
 *   är `null` bara när servern inte bifogade den.
 * - `period_last`, `andrad` (`422`): slut. Ett nytt tryck kan inte lyckas,
 *   så det finns inget att trycka på.
 * - `natverk`: vi vet inte om servern hann; samma nyckel gör ett nytt
 *   försök ofarligt, därför `Försök igen`.
 * - `nekad`: ett svar utanför §8 (t.ex. `400 voucher_date_outside_period`).
 *   Servern har sagt nej till just det här utkastet; ett omförsök ger samma
 *   nej. `kod` är serverns, oöversatt — klienten gissar inte vad den betyder.
 */
export type PostaLage =
  | { lage: "redo" }
  | { lage: "postar" }
  | { lage: "postad"; verifikation: VerifikationSvar | null }
  | {
      lage: "period_last";
      period_id: string | null;
      locked_at: string | null;
      locked_by: string | null;
    }
  | { lage: "andrad" }
  | { lage: "natverk" }
  | { lage: "nekad"; kod: string };

export interface UsePostaUtkast {
  lage: PostaLage;
  /** `Posta` och `Försök igen`. Ett anrop åt gången per kort; nyckeln skyddar resten. */
  posta: () => void;
}

/** Ett slutligt utfall (allt utom `pagar`) som kortets läge. */
function tillLage(utfall: Exclude<PostaUtfall, { utfall: "pagar" }>): PostaLage {
  switch (utfall.utfall) {
    case "postad":
    case "redan_postad":
      return { lage: "postad", verifikation: utfall.verifikation };
    case "period_last":
      return {
        lage: "period_last",
        period_id: utfall.period_id,
        locked_at: utfall.locked_at,
        locked_by: utfall.locked_by,
      };
    case "nyckel_ateranvand":
      return { lage: "andrad" };
    case "natverk":
      return { lage: "natverk" };
  }
}

function nekadKod(fel: unknown): string {
  if (!axios.isAxiosError(fel)) return "okänt fel";
  const detalj = (fel.response?.data as { detail?: unknown } | undefined)?.detail;
  const kod = (detalj as { code?: unknown } | null | undefined)?.code;
  return typeof kod === "string" ? kod : `status ${fel.response?.status ?? "okänd"}`;
}

export function usePostaUtkast(draftId: string): UsePostaUtkast {
  const qc = useQueryClient();
  const [lage, setLage] = useState<PostaLage>({ lage: "redo" });

  // Staten ritar låset; ref:en ÄR låset — två klick innan React hunnit
  // rendera `postar` ger annars två anrop. Det är bekvämlighet, inte
  // skyddet (§8 steg 2): skyddet är nyckeln, som testfall 25 prövar med
  // två flikar, var och en med sitt eget lås.
  const upptagen = useRef(false);
  // Kortet kan försvinna mitt i en `request_in_flight`-väntan (vybyte). Då
  // ska ingen timer fråga servern för ett kort ingen ser.
  const monterad = useRef(true);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    monterad.current = true;
    return () => {
      monterad.current = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const vanta = (ms: number) =>
    new Promise<void>((klar) => {
      timer.current = setTimeout(() => {
        timer.current = null;
        klar();
      }, ms);
    });

  const posta = useCallback(() => {
    if (upptagen.current) return;
    upptagen.current = true;
    setLage({ lage: "postar" });

    void (async () => {
      let slut: PostaLage;
      try {
        let utfall = await postaUtkast(draftId);
        while (utfall.utfall === "pagar") {
          // Ett annat anrop med samma nyckel håller på (en annan flik, eller
          // vårt eget förra). Fråga igen med SAMMA nyckel; svaret blir den
          // lagrade postningen (SPEC-idempotens.md §6). Knappen står kvar i
          // `Postar…` hela tiden (§8).
          if (!monterad.current) return;
          await vanta(utfall.retry_after_ms);
          if (!monterad.current) return;
          utfall = await postaUtkast(draftId);
        }
        slut = tillLage(utfall);
      } catch (fel) {
        slut = { lage: "nekad", kod: nekadKod(fel) };
      }
      if (!monterad.current) return;

      if (slut.lage === "postad") {
        // Huvudboken ändrades: headerns tal och vyns väntande beslut kan ha
        // följt med. Kvittot och `view.changed` är producentens (§8, §12.1).
        void qc.invalidateQueries({ queryKey: OVERVIEW_NYCKEL });
        void qc.invalidateQueries({ queryKey: BESLUT_NYCKEL });
      }
      // Låset släpps bara där ett nytt tryck är meningsfullt. Efter `postad`,
      // `period_last`, `andrad` och `nekad` finns ingen knapp att trycka på.
      if (slut.lage === "natverk") upptagen.current = false;
      setLage(slut);
    })();
  }, [draftId, qc]);

  return { lage, posta };
}

// ─── Utfallens text (SPEC-chattyta.md §8) ─────────────────────────────────
// På ett ställe: `PostaKnappar` och `FelKort`s `Försök igen` visar samma utfall,
// och nätverksfelets mening får aldrig glida till `Ingenting är bokfört` i
// den ena kopian men inte den andra.

/**
 * `locked_at` som servern skrev den (`isoformat()`, lokal tid utan zon) →
 * `2026-10-12 09:14`. Strängen skärs, den tolkas inte som en `Date`: utan
 * tidszon skulle webbläsaren gissa en, och tiden bli en annan än serverns.
 */
export function lastTid(iso: string | null): string {
  if (!iso) return "okänt datum";
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(iso);
  return m ? `${m[1]} ${m[2]}` : iso;
}

/**
 * Texten för ett slut som inte är klart. Alla säger vad som hände med
 * böckerna, eftersom det är det människan behöver veta (§8).
 *
 * `period_locked`: §8 skriver `Perioden {period}`, men `detail` bär bara
 * `period_id` — ett UUID, ingen etikett. Att visa UUID:t vore brus, och att
 * räkna ut månaden ur förslagets `meta` vore att tolka en sträng servern
 * formulerat (antagande 3). Meningen utelämnar därför perioden; id:t står i
 * `data-period-id` för den som felsöker.
 *
 * Nätverksfel: klienten vet INTE om servern hann posta. Därför påstås inte
 * att ingenting är bokfört — bara att ett nytt försök är ofarligt, vilket
 * nyckeln (och `409 already_posted`) garanterar.
 */
export function felText(lage: PostaLage): string | null {
  switch (lage.lage) {
    case "period_last":
      return `Perioden är låst sedan ${lastTid(lage.locked_at)} av ${
        lage.locked_by ?? "okänd"
      }. Ingenting är bokfört.`;
    case "andrad":
      return "Förslaget har ändrats sedan du tryckte. Ingenting är bokfört.";
    case "nekad":
      return `Servern nekade postningen · ${lage.kod}. Ingenting är bokfört.`;
    case "natverk":
      return "Svaret kom inte fram, så det är oklart om postningen hann igenom. Försök igen ger samma verifikation, aldrig två.";
    default:
      return null;
  }
}
