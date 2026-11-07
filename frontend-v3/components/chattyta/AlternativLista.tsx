"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { klockslag } from "@/components/chattyta/TradInlagg";
import { BESLUT_NYCKEL, svaraBeslut, type BeslutSvar } from "@/lib/chattyta/api";
import type { Alternativ, OptionsInlagg } from "@/lib/chattyta/typer";
import { formatBelopp } from "@/lib/skal/format";

/**
 * `AlternativLista` (komponenter.md §AlternativLista, SPEC-chattyta.md §4.2,
 * §5, §7, §11): agentens alternativ till ett beslut. Tryck på en rad = svaret.
 *
 * **Ingenting förväljs** (§4.2, testfall 14). Det finns ingen state som
 * börjar på ett alternativ; `recommended` ger `RekMarke` och ingenting annat
 * — inte fokus, inte ordning, inte en mörkare kant. Radens klasser räknas
 * därför aldrig ur `recommended`, bara ur listans läge. En rekommendation som
 * syns mer än som ett märke är ett förval, och ett förval låter en LLM:s
 * kontering gå igenom av bara farten (plan.md, risker).
 *
 * **En grupp knappar, inte en radiogrupp** (§11): en radiogrupp har ett valt
 * värde, och här finns inget valt värde förrän svaret är skickat. Ingen
 * bekräftelsedialog — konsekvensen står i beslutskortet (§5).
 *
 * **Låst, inte `disabled`.** Raderna låses med `aria-disabled` och en vakt i
 * klicket. En `disabled` knapp kan inte ta fokus, och §11 vill att fokus går
 * till den besvarade raden efter svaret — det vore omöjligt om raden blev
 * `disabled` i samma ögonblick.
 *
 * **Vilket svar som gäller.** Två källor, som i `BeslutKort`:
 * - Beslutet ur `GET /decisions` (`beslut`, via `useBeslut`) säger om det är
 *   besvarat, och sedan 2026-09-23 också VILKET alternativ (`answer_option_id`)
 *   och när (`answered_at`). Efter en omladdning markeras alltså den valda
 *   raden. Saknas `answer_option_id` — ett fritextsvar, eller en server från
 *   före fälten — låses alla rader och ingen markeras: att markera på gissning
 *   vore att påstå något servern inte sagt.
 * - Inom sessionen vet klienten: vid `202` är det raden som trycktes, vid
 *   `409 decision_already_answered` är det `answer_option_id` ur kroppen —
 *   som kan vara ett annat alternativ, eller `null` om svaret var fritext.
 */

type Lage = "oppen" | "besvarad" | "ersatt";

/** Svaret som det blev i den här sessionen. `optionId: null` = fritext. */
interface LokaltSvar {
  optionId: string | null;
  /** Ur `202`-svarets beslut, eller ur `409`-kroppen. */
  answeredAt: string | null;
}

const FEL_TEXT = "Svaret kom inte fram. Ingenting är besvarat.";

export function AlternativLista({
  inlagg,
  beslut,
}: {
  inlagg: OptionsInlagg;
  /** Beslutet ur `GET /decisions`; `undefined` = okänt → öppen (servern avgör vid svar). */
  beslut?: BeslutSvar;
}) {
  const { decision_id, options, footnote } = inlagg.body;
  const qc = useQueryClient();
  const fotId = useId();

  const [iFlykt, setIFlykt] = useState<string | null>(null);
  const [lokalt, setLokalt] = useState<LokaltSvar | null>(null);
  const [fel, setFel] = useState(false);

  // Två tryck innan React hunnit rendera låsningen får inte ge två anrop
  // (§5: en rad åt gången i flykt). Staten ritar låset; ref:en ÄR låset.
  const upptagen = useRef(false);
  const flyttaFokus = useRef(false);
  const radRefs = useRef(new Map<string, HTMLButtonElement>());
  const statusRef = useRef<HTMLParagraphElement>(null);

  // Lokalt svar vinner över listan: det är färskare, och bara det vet vilken rad.
  const lage: Lage = lokalt
    ? "besvarad"
    : beslut?.status === "answered"
      ? "besvarad"
      : beslut?.status === "superseded"
        ? "ersatt"
        : "oppen";
  const last = lage !== "oppen" || iFlykt !== null;
  // Lokalt svar först (färskast); annars serverns, efter en omladdning.
  const valdId = lokalt ? lokalt.optionId : (beslut?.answer_option_id ?? null);

  // Fokus efter svaret (§11): till den besvarade raden, eller till
  // statusraden när svaret var fritext och ingen rad är besvarad. Aldrig vid
  // en omladdning — då har människan inte gjort något här.
  useEffect(() => {
    if (!lokalt || !flyttaFokus.current) return;
    flyttaFokus.current = false;
    const mal = (lokalt.optionId && radRefs.current.get(lokalt.optionId)) || statusRef.current;
    mal?.focus();
  }, [lokalt]);

  async function svara(optionId: string) {
    if (last || upptagen.current) return;
    upptagen.current = true;
    setIFlykt(optionId);
    setFel(false);
    try {
      const utfall = await svaraBeslut(decision_id, optionId);
      flyttaFokus.current = true;
      setLokalt(
        utfall.utfall === "besvarat"
          ? { optionId, answeredAt: utfall.svar.decision.answered_at ?? null }
          : { optionId: utfall.answer_option_id, answeredAt: utfall.answered_at }
      );
      // §7: ett svar (202 eller 409) invaliderar beslutsfrågan — roten, så
      // att både `BeslutKort`s status och märket (C8) följer med.
      void qc.invalidateQueries({ queryKey: BESLUT_NYCKEL });
    } catch {
      // Nätverk, 5xx, eller ett 4xx som inte är "redan besvarat": raderna
      // låses upp och människan får trycka igen själv. Inget automatiskt
      // omförsök — ett svar är ett yttrande, inte en idempotent postning.
      setFel(true);
      upptagen.current = false;
    } finally {
      setIFlykt(null);
    }
  }

  // `202` bär ingen tid; den kommer med listan när beslutsfrågan hämtats om.
  const answeredAt = lokalt?.answeredAt ?? beslut?.answered_at ?? null;
  const tid = answeredAt ? klockslag(answeredAt) : null;
  const statusText =
    lage === "besvarad" ? (tid ? `Besvarat · ${tid}` : "Besvarat") : "Inte längre aktuellt";

  return (
    <div
      data-inlagg-id={inlagg.id}
      data-alternativ-lage={lage}
      // Vit yta, `border 1px #e5e7eb`, radius 12 (komponenter.md).
      className="w-full max-w-[560px] overflow-hidden rounded-[12px] border border-bok-linje bg-bok-yta"
    >
      <div
        role="group"
        aria-label="Alternativ"
        aria-describedby={footnote ? fotId : undefined}
        aria-busy={iFlykt !== null ? true : undefined}
      >
        {options.map((alt) => (
          <AlternativRad
            key={alt.option_id}
            alt={alt}
            last={last}
            vald={alt.option_id === valdId}
            onTryck={() => void svara(alt.option_id)}
            radRef={(el) => {
              if (el) radRefs.current.set(alt.option_id, el);
              else radRefs.current.delete(alt.option_id);
            }}
          />
        ))}
      </div>

      {lage !== "oppen" && (
        <p
          ref={statusRef}
          tabIndex={-1}
          data-testid="alternativ-status"
          className={`bok-mono m-0 border-t border-bok-linje-svag px-[18px] py-[10px] text-[12px] outline-none ${
            lage === "besvarad" ? "text-bok-klart-text" : "text-bok-text-svag"
          }`}
        >
          {statusText}
        </p>
      )}

      {fel && (
        // Neutral, inte FelKort-rött: ingenting i böckerna gick fel, bara
        // leveransen av svaret. Mono 12 i `#52525b` för läsbar kontrast (§11).
        <p
          role="status"
          data-testid="alternativ-fel"
          className="bok-mono m-0 border-t border-bok-linje-svag px-[18px] py-[10px] text-[12px] text-bok-text-dampad"
        >
          {FEL_TEXT}
        </p>
      )}

      {footnote && (
        // Fot: mono 12 #6b7280, ett villkor som gäller alla alternativ.
        <p
          id={fotId}
          className="bok-mono m-0 border-t border-bok-linje-svag px-[18px] py-[12px] text-[12px] text-bok-text-svag"
        >
          {footnote}
        </p>
      )}
    </div>
  );
}

/**
 * En rad. Klasserna räknas ur `last` och `vald` — aldrig ur
 * `alt.recommended`, som bara styr om `RekMarke` ritas (testfall 14).
 */
function AlternativRad({
  alt,
  last,
  vald,
  onTryck,
  radRef,
}: {
  alt: Alternativ;
  last: boolean;
  vald: boolean;
  onTryck: () => void;
  radRef: (el: HTMLButtonElement | null) => void;
}) {
  const ton = vald
    ? "bg-bok-klart-yta"
    : last
      ? "cursor-default"
      : "cursor-pointer hover:bg-bok-yta-svag";
  return (
    <button
      ref={radRef}
      type="button"
      data-option-id={alt.option_id}
      data-vald={vald ? "ja" : "nej"}
      aria-disabled={last ? true : undefined}
      onClick={onTryck}
      // Padding 15/18, `border-bottom 1px #f1f1f4` (komponenter.md). Träffyta
      // ≥ 44 ges av padding + titelraden (§11).
      className={`flex min-h-[44px] w-full items-start gap-[12px] border-b border-bok-linje-svag px-[18px] py-[15px] text-left last:border-b-0 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-bok-lank ${ton}`}
    >
      {/* Ring 16×16, `border 1px #c7c7cc`, radius 50 % — aldrig förvald. */}
      <span
        aria-hidden="true"
        data-testid="alternativ-ring"
        data-fylld={vald ? "ja" : "nej"}
        className={`mt-[3px] flex h-[16px] w-[16px] flex-none items-center justify-center rounded-full border ${
          vald ? "border-bok-klart-meta bg-bok-klart-meta" : "border-bok-kant-streckad bg-bok-yta"
        }`}
      >
        {vald && <span className="h-[6px] w-[6px] rounded-full bg-bok-yta" />}
      </span>

      <span className="flex min-w-0 flex-1 flex-col gap-[4px]">
        <span className="flex flex-wrap items-baseline gap-x-[8px] gap-y-[2px]">
          <span className={`text-[15px] ${vald ? "text-bok-klart-text" : "text-bok-text"}`}>
            {alt.title}
          </span>
          {alt.account !== null && (
            <span data-testid="alternativ-konto" className="bok-mono text-[12px] text-bok-text-svag">
              {alt.account}
            </span>
          )}
          {alt.recommended && <RekMarke />}
        </span>
        {/* Motivering 14/1.5 #78716c (ingen token; samma som förslagets fot). */}
        <span className="text-[14px] leading-[1.5] text-[#78716c]">{alt.rationale}</span>
      </span>

      {alt.amount_ore !== null && (
        <span
          data-testid="alternativ-belopp"
          className="bok-mono bok-tal whitespace-nowrap text-[14px] text-bok-text"
        >
          {formatBelopp(alt.amount_ore)}
        </span>
      )}
    </button>
  );
}

/** `RekMarke`: mono 11 #15803d på #f0fdf4, kant #bbf7d0, radius 999, padding 2/8. */
export function RekMarke() {
  return (
    <span className="bok-mono rounded-full border border-bok-klart-kant bg-bok-klart-yta px-[8px] py-[2px] text-[11px] text-bok-klart-meta">
      rekommenderas
    </span>
  );
}
