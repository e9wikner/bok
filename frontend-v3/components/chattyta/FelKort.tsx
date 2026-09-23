"use client";

import { useEffect, useId, useRef, useState } from "react";
import { SparChipRad, klockslag } from "@/components/chattyta/TradInlagg";
import { felText, usePostaUtkast } from "@/hooks/usePostaUtkast";
import type { ErrorInlagg } from "@/lib/chattyta/typer";

/**
 * `FelKort` (komponenter.md §FelKort, SPEC-chattyta.md §5, §9, §11; C13):
 * en tur som inte slutade i ett beslut eller en verifikation.
 *
 * Kortet visar serverns `cause` och `consequence` ordagrant (antagande 3).
 * Det är konsekvensen — "Ingenting bokfördes." eller vad servern nu skrev —
 * som säger det människan behöver veta. Rubriken är därför kort och lugn:
 * **`Något gick fel`**. Designens exempel (`Postningen misslyckades`) gäller
 * ett postningsfel, men nästan varje `error` backenden skriver i dag är en
 * tur som tog slut (`agent_turn_limit`, `llm_connection_error` …). En
 * rubrik som påstår att en postning misslyckades vore ett påstående om
 * huvudboken som servern inte gjort.
 *
 * **`Försök igen` bara när `retry_draft_id` finns** (§9, testfall 29, 30).
 * I dag är den alltid `null`, och då har kortet ingen primärknapp — det är
 * rätt, inte ofullständigt: att skicka om människans senaste meddelande vore
 * en ny tur, inte ett omförsök av samma avsikt, och kan ge ett annat utfall.
 * Finns ett utkast går knappen genom `usePostaUtkast` — samma hook och samma
 * härledda nyckel som förslagskortets `Posta` (§8 steg 1), så ett omförsök
 * kan aldrig ge en andra verifikation.
 *
 * **`Visa vad som hände`** fäller ut `traces[]` på plats (§5). Knappen finns
 * alltid, även utan spår: §9 säger att kortet har den, och en knapp som
 * ibland saknas lär människan att den inte går att lita på. Utan spår säger
 * ytan det i en neutral rad i stället för att vara tom.
 */

/**
 * Orsakens kod, för metaraden. Servern bildar sin kod likadant
 * (`services/thread_service.py::_error_body`: allt före första `:`).
 * Bara en maskinkod visas (`period_locked`, `agent_turn_limit`) — är orsaken
 * fri text (`okänd orsak`) står den redan i kroppen och upprepas inte.
 */
function orsaksKod(cause: string): string | null {
  const kod = cause.split(":", 1)[0].trim();
  return /^[a-z][a-z0-9_]*$/.test(kod) ? kod : null;
}

export function FelKort({ inlagg }: { inlagg: ErrorInlagg }) {
  const { cause, consequence, retry_draft_id } = inlagg.body;
  const [utfalld, setUtfalld] = useState(false);
  const sparId = useId();
  const spar = inlagg.traces ?? [];
  const meta = [klockslag(inlagg.created_at), orsaksKod(cause)].filter(Boolean).join(" · ");

  return (
    <div
      data-inlagg-id={inlagg.id}
      // Alla kort: max-bredd 560, radius 12, padding 20/22 (komponenter.md).
      // Felets yta #fef2f2 och kant #fecaca som tokens (README, fel).
      className="flex w-full max-w-[560px] flex-col gap-[14px] rounded-[12px] border border-bok-fel-kant bg-bok-fel-yta px-[22px] py-[20px]"
    >
      {/* Rubrikrad: 14/500 #b91c1c + mono 12 #dc2626 med tid och orsak. */}
      <div className="flex items-baseline justify-between gap-[14px]">
        <span data-testid="fel-rubrik" className="text-[14px] font-medium text-bok-fel-rubrik">
          Något gick fel
        </span>
        {meta && (
          <span
            data-testid="fel-meta"
            className="bok-mono whitespace-nowrap text-[12px] text-bok-fel-meta"
          >
            {meta}
          </span>
        )}
      </div>

      {/*
       * Orsak OCH konsekvens (komponenter.md), serverns ord. #7f1d1d mot
       * #fef2f2 håller ≥ 4.5:1 (§11) — felorsaken är inte metatext.
       */}
      <div
        data-testid="fel-text"
        className="flex flex-col gap-[4px] text-[14px] leading-[1.55] text-bok-fel-text [text-wrap:pretty]"
      >
        <p className="m-0">{cause}</p>
        <p className="m-0">{consequence}</p>
      </div>

      <div className="flex flex-wrap items-center gap-[10px]">
        {retry_draft_id && <ForsokIgen draftId={retry_draft_id} />}
        <button
          type="button"
          aria-expanded={utfalld}
          aria-controls={sparId}
          onClick={() => setUtfalld((u) => !u)}
          className={SEKUNDAR}
        >
          Visa vad som hände
        </button>
      </div>

      {utfalld && (
        <div id={sparId} data-testid="fel-spar">
          {spar.length > 0 ? (
            <SparChipRad spar={spar} />
          ) : (
            <p data-testid="fel-inga-spar" className="bok-mono m-0 text-[12px] text-bok-text-dampad">
              Inga spår sparades för den här turen.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Försök igen ──────────────────────────────────────────────────────────

// Träffyta 46: mobilens krav (SPEC-chattyta §11), som också täcker desktopens 44.
const PRIMAR =
  "min-h-[46px] rounded-[8px] bg-bok-black px-[16px] text-[14px] font-medium text-bok-yta hover:bg-bok-black-hover aria-disabled:cursor-default aria-disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-bok-lank";
const SEKUNDAR =
  "min-h-[46px] rounded-[8px] border border-bok-fel-kant bg-bok-yta px-[16px] text-[14px] text-bok-text hover:bg-bok-yta-svag focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-bok-lank";

/**
 * Primärknappen, bara med ett utkast. Egen komponent så att ett kort utan
 * `retry_draft_id` — alla i dag — varken anropar hooken eller kräver en
 * `QueryClientProvider`.
 *
 * Låst med `aria-disabled` och en vakt i klicket, inte `disabled` (C7, C12):
 * en avstängd knapp tappar fokus mitt i trycket.
 */
function ForsokIgen({ draftId }: { draftId: string }) {
  const { lage, posta } = usePostaUtkast(draftId);
  const postar = lage.lage === "postar";

  // Knappen människan stod på kan försvinna; fokus går till utfallet, inte
  // till `body` (§11).
  const flyttaFokus = useRef(false);
  const utfallRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!flyttaFokus.current || lage.lage === "postar" || lage.lage === "redo") return;
    flyttaFokus.current = false;
    utfallRef.current?.focus();
  }, [lage]);

  const tryck = () => {
    if (postar) return;
    flyttaFokus.current = true;
    posta();
  };

  if (lage.lage === "postad") {
    const v = lage.verifikation;
    return (
      <span
        ref={(el) => {
          utfallRef.current = el;
        }}
        tabIndex={-1}
        role="status"
        data-testid="fel-postad"
        className="bok-mono rounded-full border border-bok-klart-kant bg-bok-klart-yta px-[10px] py-[3px] text-[12px] text-bok-klart-text outline-none"
      >
        {v ? `Postad · ${v.series}-${v.number}` : "Postad"}
      </span>
    );
  }

  const text = felText(lage);
  // Bara nätverksfelet får ett nytt försök; de andra kan inte lyckas (§8).
  const kanForsoka = lage.lage === "redo" || lage.lage === "postar" || lage.lage === "natverk";

  return (
    <>
      {text && (
        <p
          ref={(el) => {
            utfallRef.current = el;
          }}
          tabIndex={-1}
          role="status"
          data-testid="fel-utfall"
          className="m-0 basis-full text-[13px] leading-[1.5] text-bok-fel-text outline-none"
        >
          {text}
        </p>
      )}
      {kanForsoka && (
        <button
          type="button"
          aria-disabled={postar ? true : undefined}
          onClick={tryck}
          className={PRIMAR}
        >
          {postar ? "Postar…" : "Försök igen"}
        </button>
      )}
    </>
  );
}
