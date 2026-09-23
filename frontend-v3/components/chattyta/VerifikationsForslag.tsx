import type { ReactNode } from "react";
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
 * Knappraden är en slot (`knappar`). C12 fyller den med `Posta` och `Ändra`;
 * fram till dess renderas inga knappar, eftersom en knapp utan idempotens-
 * nyckeln (C11) vore en väg till två verifikationer i en append-only-bok.
 */
export function VerifikationsForslag({
  inlagg,
  knappar,
}: {
  inlagg: DraftInlagg;
  /** C12:s knappar. Tom slot tills postningen byggs. */
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
