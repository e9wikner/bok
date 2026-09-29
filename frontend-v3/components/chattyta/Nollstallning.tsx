"use client";

import { useState } from "react";
import { InlaggRenderare } from "@/components/chattyta/TradRenderare";
import { klockslag } from "@/components/chattyta/TradInlagg";
import { arOptimistisk } from "@/lib/chattyta/trad";
import type { Inlagg } from "@/lib/chattyta/typer";

/**
 * Konversationens nollställning i ytan (migration 034).
 *
 * En nollställning raderar ingenting: tråden är append-only, och servern
 * flyttar bara en gräns för vad som går till agenten. Det som sades före
 * gränsen står kvar — hopfällt ovanför en avdelare, så att människan ser
 * var agentens minne börjar och fortfarande kan läsa (och svara på) det
 * som stod där.
 */

/** Tråden delad vid gränsen. Optimistiska inlägg hör alltid till efter. */
export function delaVidGrans(inlagg: Inlagg[], kontextFran: number): { fore: Inlagg[]; efter: Inlagg[] } {
  if (kontextFran <= 0) return { fore: [], efter: inlagg };
  const fore: Inlagg[] = [];
  const efter: Inlagg[] = [];
  for (const i of inlagg) (!arOptimistisk(i) && i.seq <= kontextFran ? fore : efter).push(i);
  return { fore, efter };
}

/** `2026-09-29 14:02`, lokal tid. */
function tidpunkt(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return `${d.toLocaleDateString("sv-SE")} ${klockslag(iso)}`;
}

/**
 * De hopfällda inläggen och avdelaren. Hopfällt från början: poängen med att
 * nollställa är att börja om, och det gamla ska inte stå i vägen — men en
 * knapp bort, aldrig borta.
 */
export function TidigareKonversation({
  inlagg,
  nollstalldVid,
  viewKey,
}: {
  inlagg: Inlagg[];
  nollstalldVid: string | null;
  viewKey?: string;
}) {
  const [oppen, setOppen] = useState(false);
  const tid = tidpunkt(nollstalldVid);
  return (
    <>
      {inlagg.length > 0 && (
        <button
          type="button"
          aria-expanded={oppen}
          onClick={() => setOppen((v) => !v)}
          className="bok-mono self-start text-[12px] text-bok-meta hover:text-bok-text"
        >
          {`${oppen ? "▾" : "▸"} ${inlagg.length} tidigare inlägg · ${oppen ? "dölj" : "visa"}`}
        </button>
      )}
      {oppen && (
        <div data-testid="tidigare-konversation" className="flex flex-col gap-6 opacity-70 [&>*]:shrink-0">
          {inlagg.map((i) => (
            <InlaggRenderare key={i.id} inlagg={i} viewKey={viewKey} />
          ))}
        </div>
      )}
      <div
        role="separator"
        aria-label={`Konversationen nollställd${tid ? ` ${tid}` : ""}`}
        data-testid="nollstallning-avdelare"
        className="flex items-center gap-3"
      >
        <span aria-hidden="true" className="h-px flex-1 bg-bok-linje" />
        <span aria-hidden="true" className="bok-mono whitespace-nowrap text-[11px] text-bok-meta">
          {`konversationen nollställd${tid ? ` · ${tid}` : ""}`}
        </span>
        <span aria-hidden="true" className="h-px flex-1 bg-bok-linje" />
      </div>
    </>
  );
}

/**
 * `Ny konversation`. Två steg, för att ett felklick mitt i ett ärende inte
 * ska ta agentens minne av det: första trycket frågar, andra nollställer.
 * Avstängd medan agenten svarar — servern säger ändå `409` då.
 */
export function NollstallKnapp({
  onNollstall,
  arbetar,
  variant = "desktop",
}: {
  onNollstall: () => Promise<boolean>;
  arbetar: boolean;
  variant?: "desktop" | "mobil";
}) {
  const [lage, setLage] = useState<"vila" | "fraga" | "pagar" | "fel">("vila");
  const kant = variant === "desktop" ? "px-[38px]" : "px-[18px]";

  const nollstall = async () => {
    setLage("pagar");
    setLage((await onNollstall()) ? "vila" : "fel");
  };

  return (
    <div className={`bok-mono flex shrink-0 items-center justify-end gap-3 pb-2 text-[12px] ${kant}`}>
      {lage === "fraga" ? (
        <>
          <span className="text-bok-text-dampad">Nollställ konversationen?</span>
          <button type="button" onClick={nollstall} disabled={arbetar} className="text-bok-text hover:underline disabled:text-bok-kant-streckad">
            ja
          </button>
          <button type="button" onClick={() => setLage("vila")} className="text-bok-meta hover:text-bok-text">
            avbryt
          </button>
        </>
      ) : (
        <>
          {lage === "fel" && <span className="text-bok-fel-meta">kunde inte nollställas</span>}
          <button
            type="button"
            onClick={() => setLage("fraga")}
            disabled={arbetar || lage === "pagar"}
            title="Agenten glömmer konversationen hittills. Inget raderas."
            className="text-bok-meta hover:text-bok-text disabled:cursor-default disabled:text-bok-kant-streckad disabled:hover:text-bok-kant-streckad"
          >
            ↺ ny konversation
          </button>
        </>
      )}
    </div>
  );
}
