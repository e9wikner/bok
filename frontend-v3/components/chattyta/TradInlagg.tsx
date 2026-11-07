import type { ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AgentTextInlagg, UserTextInlagg } from "@/lib/chattyta/typer";

/**
 * `TradInlagg/agent` och `TradInlagg/du` (komponenter.md §Chatten,
 * SPEC-chattyta.md §5).
 *
 * Markupen är skalets (`components/skal/ChattKolumn.tsx`) flyttad hit, så
 * att tråden ser likadan ut före och efter att C5 byter renderaren. Det som
 * är nytt är att metaraden räknas ur `created_at` i stället för att vara en
 * färdig mocksträng.
 *
 * Agentens `traces[]` ritas inte (SPEC-lasbarhet §4.3): spåren gav inget
 * för beslutet. Servern skickar och lagrar dem fortfarande — de är
 * revisionsspår — men klienten visar bara texten.
 *
 * Agentens text ritas som markdown (SPEC-lasbarhet §4.4): `react-markdown`
 * + `remark-gfm` för tabeller. Ingen rå HTML — utan `rehype-raw` blir
 * `<script>` och andra taggar aldrig element. Användarens inlägg och
 * beslutskortets fält är fortfarande ren text.
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

// ─── Agentens markdown ────────────────────────────────────────────────────

/** Stycken, listor och rubriker: 15/1.6, max 54ch — inläggets text som förut. */
const TEXT = "m-0 max-w-[54ch] text-[15px] leading-[1.6] [text-wrap:pretty]";
const LISTA = `${TEXT} pl-5 [&>li+li]:mt-1 [&_ol]:mt-1 [&_ul]:mt-1`;
const CELL = "border-b border-bok-linje px-2 py-1.5 text-left align-top";

/**
 * Elementen markdownen får bli. `node` plockas bort så att den inte hamnar
 * som attribut i DOM:en. Vikt 500 är den tyngsta (globals.css), så fetstil
 * och rubriker är `font-medium`, inte `font-bold`.
 */
const KOMPONENTER: Components = {
  p: ({ node: _n, ...p }) => <p {...p} className={TEXT} />,
  strong: ({ node: _n, ...p }) => <strong {...p} className="font-medium" />,
  ul: ({ node: _n, ...p }) => <ul {...p} className={`${LISTA} list-disc`} />,
  ol: ({ node: _n, ...p }) => <ol {...p} className={`${LISTA} list-decimal`} />,
  li: ({ node: _n, ...p }) => <li {...p} className="pl-0.5 [&>p]:max-w-none" />,
  h1: ({ node: _n, ...p }) => <h3 {...p} className={`${TEXT} font-medium`} />,
  h2: ({ node: _n, ...p }) => <h3 {...p} className={`${TEXT} font-medium`} />,
  h3: ({ node: _n, ...p }) => <h3 {...p} className={`${TEXT} font-medium`} />,
  h4: ({ node: _n, ...p }) => <h4 {...p} className={`${TEXT} font-medium`} />,
  h5: ({ node: _n, ...p }) => <h5 {...p} className={`${TEXT} font-medium`} />,
  h6: ({ node: _n, ...p }) => <h6 {...p} className={`${TEXT} font-medium`} />,
  a: ({ node: _n, ...p }) => (
    <a {...p} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2" />
  ),
  code: ({ node: _n, ...p }) => (
    <code {...p} className="bok-mono rounded bg-bok-bubbla px-1 py-px text-[13px]" />
  ),
  pre: ({ node: _n, ...p }) => (
    <pre
      {...p}
      className="m-0 overflow-x-auto rounded-md bg-bok-bubbla p-3 text-[13px] leading-[1.5] [&>code]:bg-transparent [&>code]:p-0"
    />
  ),
  blockquote: ({ node: _n, ...p }) => (
    <blockquote {...p} className="m-0 max-w-[54ch] border-l-2 border-bok-linje pl-3 text-bok-text-dampad" />
  ),
  hr: () => <hr className="m-0 border-0 border-t border-bok-linje" />,
  // Ingen bild ur agentens text laddas; alt-texten står kvar.
  img: ({ alt }) => <>{alt}</>,
  table: ({ node: _n, ...p }) => (
    <div className="w-full overflow-x-auto">
      <table {...p} className="bok-tal w-full border-collapse text-[13px] leading-[1.45]" />
    </div>
  ),
  th: ({ node: _n, ...p }) => <th {...p} className={`${CELL} font-medium text-bok-text-dampad`} />,
  td: ({ node: _n, ...p }) => <td {...p} className={CELL} />,
};

/** Agentens text som markdown, i en egen kolumn med samma gap 13 som inlägget. */
function AgentText({ text }: { text: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-[13px]">
      <Markdown remarkPlugins={[remarkGfm]} components={KOMPONENTER}>
        {text}
      </Markdown>
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
      <AgentText text={inlagg.body.text} />
      {radLista}
    </div>
  );
}
