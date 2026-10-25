"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AlternativLista } from "@/components/chattyta/AlternativLista";
import { AvfardaKnapp } from "@/components/chattyta/AvfardaKnapp";
import { useBeslut } from "@/hooks/useBeslut";
import { aldersTon } from "@/lib/chattyta/alder";
import {
  BESLUT_NYCKEL,
  forsokIgenMedUnderlag,
  oppnaFil,
  underlagsfilSokvag,
  type BeslutSvar,
} from "@/lib/chattyta/api";
import type { OptionsInlagg } from "@/lib/chattyta/typer";
import { formatBelopp } from "@/lib/skal/format";

/**
 * Ett beslut i vyn tas upp i chatten (docs/oppna-beslut.md, steg A).
 *
 * Raden i `Väntar på beslut` är bara en rad; förklaringen och vägarna ut bor
 * i chatten. Ett klick på raden sätter `valt` här. Chatten visar då beslutet:
 * finns dess inlägg i tråden skrollas dit, annars ritas `BeslutFokusKort`
 * längst ner i tråden — de syntetiska besluten (`intake`, `correction`) har
 * inget inlägg.
 *
 * `Svara agenten` lägger ingenting i munnen på människan. Fältet får en
 * inledning som säger vad svaret gäller och, för ett underlag, underlaget
 * som bilaga. Bilagan är det som gör svaret begripligt för agenten: tråden
 * får ett `user_file`-inlägg med källans id, och servern öppnar underlaget
 * igen så att agenten i tråden får bokföra från det.
 */

/** Det `ChattFalt` fylls med. `nyckel` är ny för varje tryck, så samma beslut två gånger fyller igen. */
export interface Forifyllning {
  nyckel: number;
  /** Vyn vars fält fylls: beslutets egen. */
  viewKey: string;
  text: string;
  bilaga?: { id: string; namn: string };
}

interface BeslutFokusVarde {
  valt: BeslutSvar | null;
  valj: (b: BeslutSvar) => void;
  stang: () => void;
  forifyllning: Forifyllning | null;
  svara: (b: BeslutSvar) => void;
  /**
   * En inledning i vyns fält utan något beslut: en rad som väntar men inte
   * har något kort (ett obokat lönebesked). Fältet fylls, inget skickas.
   */
  fyll: (viewKey: string, text: string) => void;
}

const INGET: BeslutFokusVarde = {
  valt: null,
  valj: () => {},
  stang: () => {},
  forifyllning: null,
  svara: () => {},
  fyll: () => {},
};

const BeslutFokusKontext = createContext<BeslutFokusVarde>(INGET);

export const useBeslutFokus = () => useContext(BeslutFokusKontext);

let fyllnummer = 0;

/** Fältets inledning: vad svaret gäller, med serverns egna namn. */
export function svarsinledning(b: BeslutSvar): string {
  if (b.kind === "intake") return `Om underlaget ${b.title}: `;
  if (b.kind === "correction") return `Om ${b.title.charAt(0).toLowerCase()}${b.title.slice(1)}: `;
  return `Om beslutet "${b.title}": `;
}

export function BeslutFokusProvider({ children }: { children: React.ReactNode }) {
  const [valt, setValt] = useState<BeslutSvar | null>(null);
  const [forifyllning, setForifyllning] = useState<Forifyllning | null>(null);
  const stang = useCallback(() => setValt(null), []);
  const svara = useCallback((b: BeslutSvar) => {
    setForifyllning({
      nyckel: ++fyllnummer,
      viewKey: b.view_key,
      text: svarsinledning(b),
      bilaga: b.kind === "intake" && b.source ? { id: b.source.id, namn: b.title } : undefined,
    });
  }, []);
  const fyll = useCallback((viewKey: string, text: string) => {
    setForifyllning({ nyckel: ++fyllnummer, viewKey, text });
  }, []);
  const varde = useMemo(
    () => ({ valt, valj: setValt, stang, forifyllning, svara, fyll }),
    [valt, stang, forifyllning, svara, fyll]
  );
  return <BeslutFokusKontext.Provider value={varde}>{children}</BeslutFokusKontext.Provider>;
}

const RUBRIK: Record<BeslutSvar["kind"], string> = {
  intake: "Agenten avstod · behöver ditt beslut",
  correction: "Korrigeringsnotering · behöver ditt beslut",
  abstention: "Agenten avstod · behöver ditt beslut",
  approval: "Väntar på ditt godkännande",
};

/**
 * Kortet för det valda beslutet, när det inte har något inlägg i tråden.
 * Läser beslutets nuvarande läge ur `useBeslut`: är det inte längre öppet
 * (besvarat, eller underlaget har tagits upp igen) stängs kortet.
 */
export function BeslutFokusKort({ viewKey, inlaggIds }: { viewKey: string; inlaggIds: ReadonlySet<string> }) {
  const { valt, stang, svara } = useBeslutFokus();
  const uppslag = useBeslut(valt ? viewKey : undefined);
  const aktuell = valt && uppslag ? uppslag.get(valt.id) : valt;
  const oppet = aktuell?.status === "open";

  useEffect(() => {
    if (valt && uppslag && !oppet) stang();
  }, [valt, uppslag, oppet, stang]);

  // Ett riktigt beslut vars inlägg står i tråden: dit, i stället för ett kort till.
  const postId = aktuell?.post_id ?? null;
  const iTraden = postId !== null && inlaggIds.has(postId);
  useEffect(() => {
    if (!iTraden || !postId) return;
    const el = Array.from(document.querySelectorAll<HTMLElement>("[data-inlagg-id]")).find(
      (e) => e.dataset.inlaggId === postId
    );
    if (!el) return;
    centreraITraden(el);
    el.dataset.fokus = "true";
    const t = setTimeout(() => delete el.dataset.fokus, 2400);
    return () => clearTimeout(t);
  }, [iTraden, postId, valt]);

  if (!aktuell || !oppet || iTraden) return null;
  return <Kort beslut={aktuell} onStang={stang} onSvara={() => svara(aktuell)} />;
}

/**
 * Skrollar trådens egen yta så att inlägget hamnar mitt i den. Inte
 * `scrollIntoView`: den skrollar varje förfader, också skalets
 * `overflow-hidden`-ruta, som då flyttades upp en bit med ett vitt fält
 * under och inte gick att skrolla tillbaka.
 */
function centreraITraden(el: HTMLElement) {
  let yta = el.parentElement;
  while (yta && !/(auto|scroll)/.test(getComputedStyle(yta).overflowY)) yta = yta.parentElement;
  if (!yta) return;
  const forskjutning = el.getBoundingClientRect().top - yta.getBoundingClientRect().top;
  const top = yta.scrollTop + forskjutning - (yta.clientHeight - el.offsetHeight) / 2;
  yta.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
}

/** Beslutets alternativ som ett `options`-inlägg, så att `AlternativLista` svarar som i tråden. */
function somAlternativ(b: BeslutSvar): OptionsInlagg {
  return {
    id: `fokus:${b.id}`,
    seq: -1,
    type: "options",
    actor: "agent",
    created_at: "",
    traces: null,
    run_id: null,
    body: {
      decision_id: b.id,
      footnote: null,
      options: b.options.map((o) => ({
        option_id: o.id,
        title: o.title,
        account: o.account,
        amount_ore: o.amount_ore,
        rationale: o.rationale,
        recommended: o.recommended,
        is_exit: o.is_exit,
      })),
    },
  };
}

function Kort({ beslut, onStang, onSvara }: { beslut: BeslutSvar; onStang: () => void; onSvara: () => void }) {
  const queryClient = useQueryClient();
  const [forsok, setForsok] = useState<"redo" | "skickar" | "fel">("redo");
  const [fil, setFil] = useState<"redo" | "saknas" | "fel">("redo");
  const underlag = beslut.kind === "intake" ? beslut.source?.id : undefined;
  const kalla = [beslut.source?.kind === "intake_source" ? "underlag" : beslut.source?.kind, beslut.source?.date]
    .filter(Boolean)
    .join(" · ");
  const forfallen = aldersTon(beslut.age_days) === "forfallen";

  return (
    <div
      data-testid="beslut-fokus"
      data-beslut-id={beslut.id}
      className="flex w-full max-w-[560px] flex-col gap-[14px] rounded-[12px] border border-bok-vantar-kant bg-bok-vantar-yta px-[22px] py-[20px]"
    >
      <div className="flex items-baseline justify-between gap-[14px]">
        <span className="text-[14px] font-medium text-bok-vantar-text">{RUBRIK[beslut.kind]}</span>
        {kalla && (
          <span
            className="bok-mono whitespace-nowrap text-[12px]"
            style={{ color: forfallen ? "var(--bok-fel-meta)" : "var(--bok-vantar-meta)" }}
          >
            {kalla}
          </span>
        )}
      </div>

      <div className="flex flex-col gap-[6px]">
        <div className="flex items-baseline justify-between gap-[14px]">
          <span className="min-w-0 break-words text-[15px] text-bok-text">{beslut.title}</span>
          {beslut.amount_ore !== null && (
            <span className="bok-mono bok-tal whitespace-nowrap text-[15px] text-bok-text">
              {formatBelopp(beslut.amount_ore)}
            </span>
          )}
        </div>
        <p className="m-0 whitespace-pre-line text-[14px] leading-[1.55] text-[#78716c]">{beslut.reason}</p>
      </div>

      <p className="bok-mono m-0 text-[12px] text-bok-text-dampad">{beslut.consequence}</p>

      {/*
       * Alternativen, när beslutet har några: kortet står här för att
       * inlägget inte syns i tråden, och då får det inte bli ett kort som
       * bara går att stänga. Ett lönekort bokförs med ett av dem.
       */}
      {beslut.options.length > 0 && <AlternativLista inlagg={somAlternativ(beslut)} beslut={beslut} />}

      <div className="flex flex-wrap items-center gap-[10px]">
        <button
          type="button"
          onClick={onSvara}
          className="rounded-[8px] border border-bok-kant bg-bok-yta px-[14px] py-[7px] text-[14px] text-bok-text hover:border-bok-text-svag"
        >
          Svara agenten
        </button>
        {underlag && (
          <button
            type="button"
            disabled={forsok === "skickar"}
            onClick={() => {
              setForsok("skickar");
              forsokIgenMedUnderlag(underlag)
                .then(() => queryClient.invalidateQueries({ queryKey: BESLUT_NYCKEL }))
                .then(onStang)
                .catch(() => setForsok("fel"));
            }}
            className="rounded-[8px] border border-bok-kant bg-bok-yta px-[14px] py-[7px] text-[14px] text-bok-text hover:border-bok-text-svag disabled:opacity-70"
          >
            {forsok === "skickar" ? "Skickar…" : forsok === "fel" ? "Gick inte, försök igen" : "Försök igen"}
          </button>
        )}
        {underlag && (
          <button
            type="button"
            onClick={() => {
              setFil("redo");
              oppnaFil(underlagsfilSokvag(underlag))
                .then((fanns) => setFil(fanns ? "redo" : "saknas"))
                .catch(() => setFil("fel"));
            }}
            className="text-[14px] text-bok-lank underline-offset-2 hover:text-bok-lank-hover hover:underline"
          >
            {fil === "saknas" ? "filen saknas" : fil === "fel" ? "kunde inte öppnas" : "Öppna underlaget"}
          </button>
        )}
        <span className="ml-auto">
          <AvfardaKnapp decisionId={beslut.id} onKlar={onStang} />
        </span>
        <button
          type="button"
          onClick={onStang}
          className="text-[13px] text-bok-text-svag hover:text-bok-text"
        >
          Stäng
        </button>
      </div>
      {underlag && (
        <p className="m-0 text-[12px] leading-[1.5] text-bok-text-svag">
          Försök igen läser om underlaget med instruktionerna som de är nu. Svara agenten bifogar underlaget i
          chatten, så att agenten bokför det utifrån ditt svar.
        </p>
      )}
    </div>
  );
}
