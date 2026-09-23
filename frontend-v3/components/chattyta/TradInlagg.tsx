import type { ReactNode } from "react";
import type { AgentTextInlagg, Spar, UserTextInlagg } from "@/lib/chattyta/typer";

/**
 * `TradInlagg/agent` och `TradInlagg/du` (komponenter.md §Chatten,
 * SPEC-chattyta.md §5).
 *
 * Markupen är skalets (`components/skal/ChattKolumn.tsx`) flyttad hit, så
 * att tråden ser likadan ut före och efter att C5 byter renderaren. Det som
 * är nytt är att metaraden räknas ur `created_at` i stället för att vara en
 * färdig mocksträng, och att agentens `traces[]` blir `SparChip`.
 *
 * `SparChip` bor i den här filen: den är en del av agentinlägget
 * (komponenter.md: *"valfria SparChip under texten"*) och har ingen egen
 * inläggstyp i renderaren. Den exporteras för `FelKort`s `Visa vad som
 * hände` (SPEC §5), som fäller ut samma spår.
 */

// ─── Metaraden ────────────────────────────────────────────────────────────

/**
 * `HH:MM` i webbläsarens lokala tid (SPEC §5). Servern lagrar UTC; en
 * människa i Sverige som skrev 08:41 ska inte se 06:41.
 *
 * Ett oläsbart datum ger `null`, inte `NaN:NaN` — metaraden säger då bara
 * `agenten`. Hellre mindre än fel (SPEC §4.4:s hållning, i litet format).
 */
export function klockslag(createdAt: string): string | null {
  const d = new Date(createdAt);
  if (Number.isNaN(d.getTime())) return null;
  const tvaSiffror = (n: number) => String(n).padStart(2, "0");
  return `${tvaSiffror(d.getHours())}:${tvaSiffror(d.getMinutes())}`;
}

/**
 * Metarad `agenten · 06:41`. Skrivs med gemener; `bok-etikett` gör den
 * versal (globals.css), så att skärmläsaren läser ett ord och inte bokstaverar.
 * Delas med `SkriverIndikator`, som har samma rad utan tid.
 */
export function AgentMeta({ tid }: { tid?: string | null }) {
  return (
    <span className="bok-etikett text-[11px] text-bok-meta">{tid ? `agenten · ${tid}` : "agenten"}</span>
  );
}

// ─── SparChip ─────────────────────────────────────────────────────────────

/**
 * Ett spår: `label` + ` · detail` när detail finns (testfall 13). Texten är
 * serverns (`build_trace`), ordagrant — agenten formulerar, klienten
 * skriver inte om (antagande 3).
 *
 * komponenter.md: mono 12 #52525b, bakgrund #f4f4f5, kant 1px #e5e7eb,
 * radius 999, padding 4/10.
 */
export function SparChip({ spar }: { spar: Spar }) {
  // Ett tomt `detail` är inget detail: annars står det `label · ` med en
  // hängande punkt, som ser ut som att något saknas.
  const text = spar.detail ? `${spar.label} · ${spar.detail}` : spar.label;
  return (
    <span
      data-testid="sparchip"
      className="bok-mono rounded-full border border-bok-linje bg-bok-linje-svagast px-[10px] py-1 text-[12px] text-bok-text-dampad"
    >
      {text}
    </span>
  );
}

/** Chipraden: gap 8, radbryter (komponenter.md). Tom lista → ingenting. */
export function SparChipRad({ spar }: { spar: Spar[] }) {
  if (spar.length === 0) return null;
  return (
    <div data-testid="sparchip-rad" className="flex flex-wrap gap-2">
      {spar.map((s, i) => (
        // Samma verktyg kan anropas två gånger i en körning; ordningen är
        // serverns och ändras aldrig, så indexet är ett stabilt nyckelbidrag.
        <SparChip key={`${s.tool}-${i}`} spar={s} />
      ))}
    </div>
  );
}

// ─── Inlägget ─────────────────────────────────────────────────────────────

export function TradInlagg({
  inlagg,
  radLista,
}: {
  inlagg: AgentTextInlagg | UserTextInlagg;
  /**
   * `RadLista/i-tråd` när kroppen bär `rows[]`. Komponenten byggs i
   * `JamforelseRader.tsx` (C9, samma radkomponent som kvittot) och skickas
   * in av renderaren — den här filen ska inte ha en egen kopia av raderna.
   */
  radLista?: ReactNode;
}) {
  if (inlagg.type === "user_text") {
    // `TradInlagg/du`: högerställd, max 74 %, #eef0f3, radius 14 14 4 14,
    // padding 12/16, 15/1.55. Optimistiska inlägg ser likadana ut; de
    // ersätts på `id` när servern svarat (SPEC §6.3), inte här.
    return (
      <div className="flex justify-end">
        <div className="max-w-[74%] rounded-[14px_14px_4px_14px] bg-bok-bubbla px-4 py-3 text-[15px] leading-[1.55] [text-wrap:pretty]">
          {inlagg.body.text}
        </div>
      </div>
    );
  }

  // `TradInlagg/agent`: kolumn med gap 13; text 15/1.6, max 54ch.
  return (
    <div className="flex flex-col gap-[13px]">
      <AgentMeta tid={klockslag(inlagg.created_at)} />
      <p className="m-0 max-w-[54ch] text-[15px] leading-[1.6] [text-wrap:pretty]">{inlagg.body.text}</p>
      {radLista}
      {inlagg.traces && <SparChipRad spar={inlagg.traces} />}
    </div>
  );
}
