"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { felText, usePostaUtkast, type PostaLage } from "@/hooks/usePostaUtkast";
import type { ForslagStatusSvar } from "@/lib/chattyta/api";
import type { DraftInlagg, KonteringsRad as KonteringsRadData } from "@/lib/chattyta/typer";
import { formatBelopp } from "@/lib/skal/format";

/**
 * `VerifikationsForslag` (komponenter.md §Kort i tråden, SPEC-chattyta.md
 * §4.3, §5, §8): utkastet som det blir i böckerna.
 *
 * Kortet visar serverns rader ordagrant. Agenten formulerar, servern räknar
 * (antagande 3): `title`, `meta`, `footnote` och `consequence` skrivs inte om,
 * och ingen summa räknas här — öre in, `formatBelopp` ut, inget mer.
 *
 * Knappraden är en slot (`knappar`). `TradRenderare` fyller den med
 * `PostaKnappar` (C12, längre ned). Kortet självt vet inget om postning, så
 * att det kan ritas utan nät och utan `QueryClientProvider`.
 *
 * **Lägena** (flode-verifikationer §10, F13) kommer ur `forslag`, raden ur
 * `GET /drafts` som `TradRenderare` slår upp med `useForslag`:
 * - saknas (frågan har inte svarat, misslyckades, eller raden finns inte)
 *   eller `pending`: som i dag, med knapparna. `last_error_code` hanteras av
 *   `PostaKnappar` (felraden, ingen `Posta`);
 * - `posted`: `Postad · {serie}-{nummer}` ur `voucher`, inga knappar;
 * - `superseded`: `Ersatt av ett nytt förslag`, inga knappar.
 * Konsekvensnotisen står kvar i alla fyra.
 */
export function VerifikationsForslag({
  inlagg,
  knappar,
  forslag,
}: {
  inlagg: DraftInlagg;
  /** `PostaKnappar`, eller ingenting. Ritas bara i `pending`. */
  knappar?: ReactNode;
  /** Förslagets rad ur `GET /drafts`, eller `undefined` när den inte är känd. */
  forslag?: ForslagStatusSvar;
}) {
  const { title, meta, rows, footnote, consequence } = inlagg.body;
  const status = forslag?.status;

  return (
    <div
      data-inlagg-id={inlagg.id}
      // Alla kort: max-bredd 560, radius 12. Kant #d4d4d8 (--bok-kant).
      className="w-full max-w-[560px] overflow-hidden rounded-[12px] border border-bok-kant bg-bok-yta"
    >
      {/* Rubrikrad: titel 15/500 + mono 12 metagrå, linje #f1f1f4 under. */}
      <div className="flex items-baseline justify-between gap-[14px] border-b border-bok-linje-svag px-[18px] py-[14px]">
        <span className="min-w-0 text-[15px] font-medium text-bok-text">{title}</span>
        <span className="bok-mono whitespace-nowrap text-[12px] text-bok-meta">{meta}</span>
      </div>

      {/* Kolumnrubriker mono 10 versalt; de två högra 92 px högerställda. */}
      <div className="flex items-baseline gap-[8px] px-[18px] pb-[2px] pt-[10px]">
        <span className="bok-mono flex-1 text-[10px] uppercase tracking-wide text-bok-meta">
          Konto
        </span>
        <span className="bok-mono w-[92px] text-right text-[10px] uppercase tracking-wide text-bok-meta">
          Debet
        </span>
        <span className="bok-mono w-[92px] text-right text-[10px] uppercase tracking-wide text-bok-meta">
          Kredit
        </span>
      </div>

      <div>
        {rows.map((rad, i) => (
          // Samma konto kan förekomma två gånger i en verifikation; index ingår.
          <KonteringsRad key={`${rad.account}-${i}`} rad={rad} />
        ))}
      </div>

      {/* Fot 13/1.55 #78716c: underlag och flaggor. Utgår när servern inte skickar någon. */}
      {footnote && (
        <p
          data-testid="forslag-fot"
          className="px-[18px] pt-[10px] text-[13px] leading-[1.55] text-[#78716c]"
        >
          {footnote}
        </p>
      )}

      {/*
       * Knapprad: primär + sekundär + konsekvensnotis. Notisen står kvar
       * utan knappar — varningen gäller förslaget, inte knappen.
       *
       * Notisen är INTE metatext (komponenter.md): den bär varningen och ska
       * ha läsbar kontrast, ≥ 4.5:1 (SPEC §11). Därför `text-bok-text-dampad`
       * (#52525b) och aldrig `text-bok-meta` (#9ca3af). Testfall 24.
       */}
      <div
        data-testid="forslag-knapprad"
        className="flex flex-wrap items-center gap-[10px] px-[18px] pb-[16px] pt-[14px]"
      >
        {status === "posted" ? (
          <PostadEtikett
            text={forslag?.voucher ? `Postad · ${forslag.voucher.series}-${forslag.voucher.number}` : "Postad"}
          />
        ) : status === "superseded" ? (
          <span
            role="status"
            data-testid="forslag-ersatt"
            className="bok-mono rounded-full border border-bok-linje bg-bok-linje-svagast px-[10px] py-[3px] text-[12px] text-bok-text-dampad"
          >
            Ersatt av ett nytt förslag
          </span>
        ) : (
          knappar
        )}
        {/* `whitespace-pre-line`: en rättelses konsekvens har två rader (§7.2). */}
        <span className="bok-mono whitespace-pre-line text-[12px] text-bok-text-dampad">
          {consequence}
        </span>
      </div>
    </div>
  );
}

/**
 * `KonteringsRad` (komponenter.md): padding 9/18, konto mono 13 #6b7280 +
 * namn 14, belopp mono 14 tabular. Exakt ett av debet/kredit är satt
 * (typer.ts); den tomma cellen står kvar så att kolumnerna håller linjen.
 */
function KonteringsRad({ rad }: { rad: KonteringsRadData }) {
  return (
    <div
      data-testid="konteringsrad"
      className="flex items-baseline gap-[8px] border-b border-bok-linje-svagast px-[18px] py-[9px]"
    >
      <span className="flex min-w-0 flex-1 items-baseline gap-[10px]">
        <span className="bok-mono text-[13px] text-bok-text-svag">{rad.account}</span>
        <span className="min-w-0 text-[14px] text-bok-text">{rad.name}</span>
      </span>
      <span
        data-kolumn="debet"
        className="bok-mono bok-tal w-[92px] whitespace-nowrap text-right text-[14px] text-bok-text"
      >
        {rad.debit_ore !== null ? formatBelopp(rad.debit_ore) : ""}
      </span>
      <span
        data-kolumn="kredit"
        className="bok-mono bok-tal w-[92px] whitespace-nowrap text-right text-[14px] text-bok-text"
      >
        {rad.credit_ore !== null ? formatBelopp(rad.credit_ore) : ""}
      </span>
    </div>
  );
}

// ─── Postningsknapparna (SPEC-chattyta.md §8, C12) ────────────────────────

// Träffyta 46: mobilens krav (SPEC-chattyta §11), som också täcker desktopens 44.
const PRIMAR =
  "min-h-[46px] rounded-[8px] bg-bok-black px-[16px] text-[14px] font-medium text-bok-yta hover:bg-bok-black-hover aria-disabled:cursor-default aria-disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-bok-lank";
const SEKUNDAR =
  "min-h-[46px] rounded-[8px] border border-bok-kant bg-bok-yta px-[16px] text-[14px] text-bok-text hover:bg-bok-yta-svag aria-disabled:cursor-default aria-disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-bok-lank";

/**
 * `Posta` + `Ändra` och de sju utfallen (§8). Nyckeln görs i `postaUtkast`,
 * aldrig här; kortet vet bara `draftId` (antagande 4).
 *
 * **Låst, inte `disabled`** (som `AlternativLista`): `aria-disabled` och en
 * vakt i klicket. En `disabled` knapp tappar fokus mitt i trycket.
 *
 * `onAndra` är kolumnens `ChattFalt`-fokus (`TradRenderare`). Utan den ritas
 * ingen `Ändra` — en knapp som inte kan göra något är värre än ingen.
 * `Ändra` skickar aldrig något och skriver inget i fältet (§8 steg 4): en
 * knapp som skickar en färdig mening är ett förvalt yttrande, samma sak som
 * förslagschipsen som togs bort (SPEC-skal.md §2.1).
 */
/** Klartonens `Postad · A-118`. Delas av klickets utfall och `posted` ur `GET /drafts`. */
const PostadEtikett = ({ text, etikettRef }: { text: string; etikettRef?: (el: HTMLElement | null) => void }) => (
  <span
    ref={etikettRef}
    tabIndex={-1}
    role="status"
    data-testid="posta-klart"
    className="bok-mono rounded-full border border-bok-klart-kant bg-bok-klart-yta px-[10px] py-[3px] text-[12px] text-bok-klart-text outline-none"
  >
    {text}
  </span>
);

/**
 * Kortets läge: klickets eget utfall, utom när det inte säger något
 * (`redo`) eller inte vet något (`natverk`) och servern har ett fel på
 * förslaget (`last_error_code`, flode-verifikationer §10). Klickets fel går
 * före serverns kod, eftersom det bär mer (vem som låste, vilket nummer).
 */
function medServerFel(lage: PostaLage, serverFel: string | null | undefined): PostaLage {
  if (!serverFel || (lage.lage !== "redo" && lage.lage !== "natverk")) return lage;
  return { lage: "avvisad", kod: serverFel, bokford_pa: null };
}

export function PostaKnappar({
  draftId,
  onAndra,
  serverFel,
}: {
  draftId: string;
  onAndra?: () => void;
  /** `last_error_code` ur `GET /drafts`: ett fel som ett nytt tryck inte rättar. */
  serverFel?: string | null;
}) {
  const { lage: egetLage, langsam, posta } = usePostaUtkast(draftId);
  const lage = medServerFel(egetLage, serverFel);
  const postar = lage.lage === "postar";

  // Efter ett tryck försvinner knappen människan stod på. Fokus går till
  // utfallsraden i stället för till `body` (§11).
  const flyttaFokus = useRef(false);
  const utfallRef = useRef<HTMLElement | null>(null);
  const satUtfall = (el: HTMLElement | null) => {
    utfallRef.current = el;
  };
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
    return <PostadEtikett etikettRef={satUtfall} text={v ? `Postad · ${v.series}-${v.number}` : "Postad"} />;
  }

  const fel = felText(lage);
  // Bara nätverksfelet får ett nytt försök: de andra kan inte lyckas (§8).
  const kanPosta = lage.lage === "redo" || lage.lage === "postar" || lage.lage === "natverk";

  return (
    <>
      {fel && (
        <p
          ref={satUtfall}
          tabIndex={-1}
          role="status"
          data-testid="posta-fel"
          data-period-id={lage.lage === "period_last" ? (lage.period_id ?? undefined) : undefined}
          // FelKort-ton i kortet (§8), full bredd över knappraden.
          className="m-0 basis-full rounded-[8px] border border-bok-fel-kant bg-bok-fel-yta px-[12px] py-[8px] text-[13px] leading-[1.5] text-bok-fel-text outline-none"
        >
          {fel}
        </p>
      )}
      {kanPosta && (
        <button
          type="button"
          aria-disabled={postar ? true : undefined}
          onClick={tryck}
          className={PRIMAR}
        >
          {postar
            ? langsam
              ? "Postar fortfarande…"
              : "Postar…"
            : lage.lage === "natverk"
              ? "Försök igen"
              : "Posta"}
        </button>
      )}
      {onAndra && (
        <button
          type="button"
          aria-disabled={postar ? true : undefined}
          onClick={() => {
            if (!postar) onAndra();
          }}
          className={SEKUNDAR}
        >
          Ändra
        </button>
      )}
    </>
  );
}
