"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { usePostaUtkast, type PostaLage } from "@/hooks/usePostaUtkast";
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
 */
export function VerifikationsForslag({
  inlagg,
  knappar,
}: {
  inlagg: DraftInlagg;
  /** `PostaKnappar`, eller ingenting. */
  knappar?: ReactNode;
}) {
  const { title, meta, rows, footnote, consequence } = inlagg.body;

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
        {knappar}
        <span className="bok-mono text-[12px] text-bok-text-dampad">{consequence}</span>
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

/**
 * `locked_at` som servern skrev den (`isoformat()`, lokal tid utan zon) →
 * `2026-10-12 09:14`. Strängen skärs, den tolkas inte som en `Date`: utan
 * tidszon skulle webbläsaren gissa en, och tiden bli en annan än serverns.
 */
function lastTid(iso: string | null): string {
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
function felText(lage: PostaLage): string | null {
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

const PRIMAR =
  "min-h-[44px] rounded-[8px] bg-bok-black px-[16px] text-[14px] font-medium text-bok-yta hover:bg-bok-black-hover aria-disabled:cursor-default aria-disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-bok-lank";
const SEKUNDAR =
  "min-h-[44px] rounded-[8px] border border-bok-kant bg-bok-yta px-[16px] text-[14px] text-bok-text hover:bg-bok-yta-svag aria-disabled:cursor-default aria-disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-bok-lank";

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
export function PostaKnappar({
  draftId,
  onAndra,
}: {
  draftId: string;
  onAndra?: () => void;
}) {
  const { lage, posta } = usePostaUtkast(draftId);
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
    return (
      <span
        ref={satUtfall}
        tabIndex={-1}
        role="status"
        data-testid="posta-klart"
        className="bok-mono rounded-full border border-bok-klart-kant bg-bok-klart-yta px-[10px] py-[3px] text-[12px] text-bok-klart-text outline-none"
      >
        {v ? `Postad · ${v.series}-${v.number}` : "Postad"}
      </span>
    );
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
          {postar ? "Postar…" : lage.lage === "natverk" ? "Försök igen" : "Posta"}
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
