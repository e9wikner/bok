import type { KonteringsRad as KonteringsRadData } from "@/lib/chattyta/typer";
import { formatBelopp } from "@/lib/skal/format";

/**
 * Konteringen som den blir i böckerna: kolumnrubrikerna Konto / Debet /
 * Kredit och serverns rader ordagrant. Samma tabell på varje kort som
 * bokför — ett verifikationsförslag, ett lönekort, ett fakturaförslag — så
 * att det som bokförs alltid ser likadant ut, var det än kommer ifrån.
 *
 * `rubrik` står ovanför kolumnrubrikerna när tabellen inte är kortets
 * huvudsak (fakturaförslaget visar fakturan först och konteringen sist).
 */
export function Kontering({ rader, rubrik }: { rader: readonly KonteringsRadData[]; rubrik?: string }) {
  return (
    <div data-testid="kontering">
      {rubrik && (
        <div className="bok-mono px-[18px] pt-[12px] text-[11px] text-bok-text-dampad">{rubrik}</div>
      )}
      {/* Kolumnrubriker mono 10 versalt; de två högra 92 px högerställda. */}
      <div className="flex items-baseline gap-[8px] px-[18px] pb-[2px] pt-[10px]">
        <span className="bok-mono flex-1 text-[10px] uppercase tracking-wide text-bok-meta">Konto</span>
        <span className="bok-mono w-[92px] text-right text-[10px] uppercase tracking-wide text-bok-meta">
          Debet
        </span>
        <span className="bok-mono w-[92px] text-right text-[10px] uppercase tracking-wide text-bok-meta">
          Kredit
        </span>
      </div>

      <div>
        {rader.map((rad, i) => (
          // Samma konto kan förekomma två gånger i en verifikation; index ingår.
          <KonteringsRad key={`${rad.account}-${i}`} rad={rad} />
        ))}
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
