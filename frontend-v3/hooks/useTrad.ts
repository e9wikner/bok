"use client";

/**
 * En vys tråd: läs, prenumerera, skicka (SPEC-chattyta.md §6.2–6.3).
 *
 * Tillståndet är reducerns (`lib/chattyta/trad.ts`); här bor bara
 * livscykeln — när strömmen öppnas, när den stängs, och vilka frågor en
 * händelse gör inaktuella.
 *
 * Strömmen öppnas på exakt två ställen, båda med serverns `cursor`:
 * GET-svaret när det bär ett `thread_id` (§6.2 punkt 2), och det första
 * POST-svaret i en tom tråd (punkt 3). Aldrig innan: servern svarar `404`
 * på en ström mot en tråd som inte finns (§2 rad 3), och `oppnaStrom`
 * återansluter på `404` — en för tidig ström vore en evig backoff-slinga.
 */

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { BESLUT_NYCKEL, hamtaTrad, OVERVIEW_NYCKEL, skickaMeddelande } from "@/lib/chattyta/api";
import { oppnaStrom, type SseHandelse } from "@/lib/chattyta/strom";
import {
  listaInlagg,
  LOKALT_PREFIX,
  tomTrad,
  tradReducer,
  type Strommande,
} from "@/lib/chattyta/trad";
import type { Inlagg } from "@/lib/chattyta/typer";

/**
 * Inlägg vars ankomst kan ändra ett besluts status (§7): ett nytt beslut,
 * nya alternativ, eller människans fritext som agenten kan ha tolkat som svar.
 */
const BESLUTSTYPER = new Set(["decision", "options", "user_text"]);

/** Allt som hör till EN vy. Byts ut hel vid vybyte (§6.2 punkt 5). */
interface Vy {
  viewKey: string;
  avbryt: AbortController;
  stromOppen: boolean;
}

export interface UseTrad {
  inlagg: Inlagg[];
  strommande: Strommande | null;
  /**
   * `true` när servern lagrat meddelandet, `false` när POST misslyckades.
   * Vid `false` är det optimistiska inlägget borttaget och `fel` satt —
   * anroparen (C5:s `ChattFalt`) behåller då texten i fältet.
   */
  skicka: (text: string) => Promise<boolean>;
  laddar: boolean;
  /** Senaste felet från GET eller POST; nollställs av nästa lyckade. */
  fel: unknown;
}

let lopnummer = 0;

export function useTrad(viewKey: string): UseTrad {
  const [tillstand, dispatch] = useReducer(tradReducer, undefined, tomTrad);
  const [laddar, setLaddar] = useState(true);
  const [fel, setFel] = useState<unknown>(null);
  const qc = useQueryClient();
  // Samma utloggning som resten av appen. Det finns ingen 401-hantering i
  // axios-instansen att återanvända (C2), så strömmen får den härifrån.
  const { logout } = useAuth();
  const vyRef = useRef<Vy | null>(null);

  const paHandelse = useCallback(
    (h: SseHandelse) => {
      dispatch({ typ: "handelse", handelse: h });
      if (h.event === "view.changed") {
        // Vyns rader är `flode-verifikationer`s; här blir bara headern och
        // besluten inaktuella (§6.3).
        void qc.invalidateQueries({ queryKey: OVERVIEW_NYCKEL });
        void qc.invalidateQueries({ queryKey: BESLUT_NYCKEL });
      } else if (h.event === "message.completed") {
        const typ = (h.data as { type?: unknown } | null)?.type;
        if (typeof typ === "string" && BESLUTSTYPER.has(typ)) {
          void qc.invalidateQueries({ queryKey: BESLUT_NYCKEL });
        }
      }
    },
    [qc]
  );

  /** En ström per vy; ett andra anrop är en no-op (§6.2 punkt 5). */
  const oppna = useCallback(
    (vy: Vy, since: number) => {
      if (vy.stromOppen || vy.avbryt.signal.aborted) return;
      vy.stromOppen = true;
      void oppnaStrom({
        viewKey: vy.viewKey,
        since,
        signal: vy.avbryt.signal,
        onHandelse: paHandelse,
        onObehorig: logout,
      });
    },
    [paHandelse, logout]
  );

  useEffect(() => {
    const vy: Vy = { viewKey, avbryt: new AbortController(), stromOppen: false };
    vyRef.current = vy;
    dispatch({ typ: "nollstall" });
    setLaddar(true);
    setFel(null);

    hamtaTrad(viewKey)
      .then((svar) => {
        if (vy.avbryt.signal.aborted) return;
        dispatch({ typ: "hamtad", posts: svar.posts, cursor: svar.cursor });
        // `thread_id: null` = ingen har sagt något här i år; ingen ström
        // förrän första POST skapat tråden (§6.2 punkt 1, testfall 8).
        if (svar.thread_id !== null) oppna(vy, svar.cursor);
      })
      .catch((e: unknown) => {
        if (!vy.avbryt.signal.aborted) setFel(e);
      })
      .finally(() => {
        if (!vy.avbryt.signal.aborted) setLaddar(false);
      });

    // Vybyte och avmontering stänger strömmen och gör varje svar som
    // fortfarande är i flykt för den här vyn verkningslöst.
    return () => vy.avbryt.abort();
  }, [viewKey, oppna]);

  const skicka = useCallback(
    async (text: string): Promise<boolean> => {
      const vy = vyRef.current;
      if (!vy || vy.avbryt.signal.aborted) return false;
      const lokaltId = `${LOKALT_PREFIX}${++lopnummer}`;
      dispatch({ typ: "optimistisk", id: lokaltId, text, skapad: new Date().toISOString() });

      try {
        const svar = await skickaMeddelande(vy.viewKey, text);
        // Svaret hör till vyn som var aktiv när människan tryckte. Har hon
        // bytt vy sedan dess är den nya vyns tråd en annan tråd.
        if (vy.avbryt.signal.aborted) return true;
        dispatch({ typ: "skickad", lokaltId, posts: svar.posts, cursor: svar.cursor });
        setFel(null);
        oppna(vy, svar.cursor);
        return true;
      } catch (e) {
        if (vy.avbryt.signal.aborted) return false;
        // Det optimistiska tas BORT, det markeras inte. Ett inlägg som står
        // kvar i tråden påstår att servern har det — och tråden är
        // append-only-bokens samtal, där ett påstående om vad som sagts ska
        // vara sant (antagande 2). Texten går inte förlorad: `false` säger
        // till fältet att behålla den, och `fel` bär orsaken.
        dispatch({ typ: "misslyckad", lokaltId });
        setFel(e);
        return false;
      }
    },
    [oppna]
  );

  const inlagg = useMemo(() => listaInlagg(tillstand), [tillstand]);

  return { inlagg, strommande: tillstand.strommande, skicka, laddar, fel };
}
