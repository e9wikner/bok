import type { ReactNode } from "react";
import { formatBelopp } from "@/lib/skal/format";
import type { RadListaRad, ReceiptKropp } from "@/lib/chattyta/typer";

/**
 * `JamforelseRader` (`receipt`) och `RadLista/i-tråd` (`agent_text` med
 * `rows[]`) — SPEC-chattyta.md §5, komponenter.md §RadLista/i-tråd och
 * §JamforelseRader.
 *
 * komponenter.md säger att de är SAMMA komponent. Därför en fil och en
 * radkomponent (`Rad`) som tar en lista tal: jämförelsen ger två, listan
 * ett. Skiljer de sig åt i mått glider de isär i tråden, och läsaren ska
 * kunna lita på att en rad ser ut som en rad.
 *
 * Belopp kommer i öre och går rakt in i `formatBelopp` (regel 2: klienten
 * formaterar, räknar aldrig). Två decimaler, inte `formatBeloppHela` — en
 * jämförelse som avrundar kan visa två lika tal för en skillnad i öre.
 */

/**
 * Talkolumnernas bredd. Fast, så att `var` och `blir` står i linje rad för
 * rad och etiketten står över sitt tal. Samma 92 px som
 * `VerifikationsForslag`s beloppskolumner (SPEC §5, C10).
 */
const TALKOLUMN = "w-[92px] shrink-0 text-right";

function Rad({ nyckel, text, tal }: { nyckel: string; text: string; tal: number[] }) {
  return (
    <div
      data-testid="jamforelse-rad"
      // Rader padding 11/16, border-bottom #f1f1f4; sista raden utan, då
      // ramen redan stänger listan.
      className="flex items-center justify-between gap-4 border-b border-bok-linje-svag px-4 py-[11px] last:border-b-0"
    >
      <div className="flex min-w-0 items-baseline gap-3">
        <span className="bok-mono whitespace-nowrap text-[13px] text-bok-text-svag">{nyckel}</span>
        <span className="text-[14px]">{text}</span>
      </div>
      <div className="flex shrink-0 gap-4">
        {tal.map((ore, i) => (
          <span
            // Ordningen ÄR betydelsen (vänster = var, höger = blir), så
            // indexet är rätt nyckel här.
            key={i}
            data-testid="tal"
            className={`bok-mono bok-tal whitespace-nowrap text-[14px] ${
              tal.length > 1 ? TALKOLUMN : ""
            }`}
          >
            {formatBelopp(ore)}
          </span>
        ))}
      </div>
    </div>
  );
}

/** Vit yta, border #e5e7eb, radius 12, max-bredd 560 (komponenter.md). */
function Ram({ children }: { children: ReactNode }) {
  return (
    <div className="max-w-[560px] overflow-hidden rounded-xl border border-bok-linje bg-bok-yta">
      {children}
    </div>
  );
}

/**
 * Kvittot efter en handling. **Båda talen visas alltid** — också när de är
 * lika. En ensam ny summa är fel (komponenter.md), eftersom läsaren då
 * inte kan se vad som ändrades. `parseInlagg` har redan vägrat en rad som
 * saknar något av talen (SPEC §4.1), så här finns alltid två.
 *
 * Etiketterna är serverns (`labels`), inte komponentens: `var`/`blir` och
 * `kvitto`/`A-118` är olika jämförelser, och det är agenten som vet vilken.
 */
export function JamforelseRader({ kropp }: { kropp: ReceiptKropp }) {
  const [vanster, hoger] = kropp.labels;
  return (
    <div data-testid="jamforelse" className="flex max-w-[560px] flex-col gap-2">
      <span className="text-[14px] font-medium">{kropp.title}</span>
      <Ram>
        <div
          data-testid="jamforelse-etiketter"
          className="flex justify-end gap-4 border-b border-bok-linje-svag px-4 py-2"
        >
          <span className={`bok-mono text-[11px] text-bok-meta ${TALKOLUMN}`}>{vanster}</span>
          <span className={`bok-mono text-[11px] text-bok-meta ${TALKOLUMN}`}>{hoger}</span>
        </div>
        {kropp.rows.map((r, i) => (
          // `key` är inte garanterat unikt (samma konto kan stå två gånger).
          <Rad key={`${r.key}-${i}`} nyckel={r.key} text={r.text} tal={[r.left_ore, r.right_ore]} />
        ))}
      </Ram>
    </div>
  );
}

/**
 * Rader i ett agentsvar: belopp per anställd, kvitterade spår. En kolumn
 * tal och ingen etikettrad — agentens text ovanför säger vad talen är.
 * En tom lista blir ingenting, inte en tom ram.
 */
export function RadLista({ rader }: { rader: RadListaRad[] }) {
  if (rader.length === 0) return null;
  return (
    <Ram>
      {rader.map((r, i) => (
        <Rad key={`${r.key}-${i}`} nyckel={r.key} text={r.text} tal={[r.amount_ore]} />
      ))}
    </Ram>
  );
}
