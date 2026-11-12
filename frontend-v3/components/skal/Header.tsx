"use client";

import { AgentStatus } from "@/components/skal/AgentStatus";
import { PrickNav } from "@/components/skal/PrickNav";
import { SidVaeljare, type SidMeta } from "@/components/skal/SidVaeljare";
import type { Tema } from "@/components/skal/TemaVaxel";
import type { AgentStatus as AgentStatusData } from "@/lib/skal/api";
import type { Sida, Sidnyckel, Vy } from "@/lib/skal/vyer";

/**
 * Headern. Desktop 62, mobil 56 (README.md §Mått — fasta värden).
 *
 * Desktop: väljaren och bolagsraden till vänster; vyns status, räkenskapsår
 * med periodläge och `AgentStatus` till höger.
 * Mobil: sidtiteln är väljaren, prickarna ligger till höger.
 *
 * `waiting` och `meta` kommer färdiga från servern. Headern räknar
 * ingenting — datakontraktets regel 2.
 */
export interface Arsval {
  /** `text` är hela årsraden, `etikett` bara året ("2026"). */
  alternativ: { id: string; text: string; etikett: string }[];
  valt: string;
  onValj: (id: string) => void;
}

/**
 * Räkenskapsåret som en native select. Desktop visar hela årsraden; mobilen
 * visar bara året i den stängda väljaren men hela raden i listan.
 */
function ArsValjare({ arsval, variant }: { arsval: Arsval; variant: "desktop" | "mobil" }) {
  const mobil = variant === "mobil";
  const valt = arsval.alternativ.find((a) => a.id === arsval.valt);
  return (
    <label className="relative flex shrink-0 items-center">
      <span className="sr-only">Välj räkenskapsår</span>
      {/* På mobil är selecten osynlig ovanpå etiketten, så att den stängda
          väljaren kan visa bara året medan listan visar hela raden. */}
      {mobil && (
        <span aria-hidden className="bok-mono pr-4 text-[13px] text-bok-text-dampad">
          {valt?.etikett}
        </span>
      )}
      <select
        value={arsval.valt}
        onChange={(e) => arsval.onValj(e.target.value)}
        className={
          mobil
            ? "absolute inset-0 cursor-pointer appearance-none opacity-0"
            : "bok-mono cursor-pointer appearance-none bg-transparent pr-4 text-[13px] text-bok-text-dampad hover:text-bok-text focus:outline-none focus-visible:underline"
        }
        // iOS zoomar in på fält under 16 px; den osynliga selecten får 16 px.
        style={mobil ? { fontSize: 16 } : undefined}
      >
        {arsval.alternativ.map((a) => (
          <option key={a.id} value={a.id}>
            {a.text}
          </option>
        ))}
      </select>
      <span aria-hidden className="pointer-events-none absolute right-0 text-[10px] text-bok-text-dampad">
        ▾
      </span>
    </label>
  );
}

export function Header({
  variant,
  sida,
  aktivVy,
  aktivIndex,
  metaPerSida,
  arsrad,
  arsval,
  vyStatus,
  agent,
  onValjSida,
  onValjVy,
  tema,
}: {
  variant: "desktop" | "mobil";
  sida: Sida;
  aktivVy: Vy;
  aktivIndex: number;
  metaPerSida: Partial<Record<Sidnyckel, SidMeta>>;
  /** T.ex. "Räkenskapsår 2026 · juni öppen". Serverns fält, klientens skiljetecken. */
  arsrad: string;
  /** Åren att välja mellan. Saknas listan visas `arsrad` som text. */
  arsval?: Arsval;
  vyStatus: { text: string; fg: string };
  agent?: AgentStatusData;
  onValjSida: (s: Sidnyckel) => void;
  onValjVy: (index: number) => void;
  /** Mobilen har ingen sidonavigering; växeln ligger i sidmenyn. */
  tema?: Tema;
}) {
  if (variant === "mobil") {
    return (
      <header
        // viewport-fit=cover (app/layout.tsx) lägger sidan under statusraden
        // och Dynamic Island. Headern tar höjden ovanför sig som padding, så
        // att bakgrunden fyller ut dit men innehållet börjar under den.
        className="box-content flex h-[56px] shrink-0 items-center justify-between gap-3 border-b border-bok-linje-svag bg-bok-yta px-[14px] pt-[env(safe-area-inset-top)]"
        style={{ position: "relative", zIndex: 6 }}
      >
        <div className="flex min-w-0 items-center gap-3">
          <SidVaeljare aktiv={sida.key} metaPerSida={metaPerSida} onValj={onValjSida} variant="mobil" tema={tema} />
          {/* Mobilen har inte plats för hela årsraden: väljaren visar bara
              året, och listan som öppnas bär periodläget. */}
          {arsval && arsval.alternativ.length > 0 && <ArsValjare arsval={arsval} variant="mobil" />}
        </div>
        {/* v10:s mobilram har ingen plats för AgentStatus. Den visas ändå,
            kompakt (bara verbet): utan den syns det inte på mobilen att
            agenten arbetar. Vilande ritas som ingenting. */}
        {agent?.state && agent.state !== "vilande" && (
          <div className="shrink-0">
            <AgentStatus state={agent.state} pausadOrsak={agent.paused_reason} kompakt />
          </div>
        )}
        <div className="shrink-0">
          <PrickNav vyer={sida.vyer} aktivIndex={aktivIndex} onValj={onValjVy} storlek="mobil" />
        </div>
      </header>
    );
  }

  return (
    <header
      className="flex h-[52px] shrink-0 items-center justify-between border-b border-bok-linje bg-bok-yta px-5"
      style={{ position: "relative", zIndex: 6 }}
    >
      <div className="flex items-center gap-4">
        {/* Sidorna och vyerna står i sidonavigeringen (`SidNav`); headern
            bär bara namnet. Öppen fråga 1: var bolagsnamnet kommer ifrån.
            GET /overview bär det inte, så det står "BokAi". */}
        <span className="text-[15px] font-medium tracking-[-0.01em] text-bok-text">BokAi</span>
      </div>

      <div className="flex items-center gap-5">
        <span className="bok-mono text-[13px]" style={{ color: vyStatus.fg }}>
          {aktivVy.titel} · {vyStatus.text}
        </span>
        {arsval && arsval.alternativ.length > 0 ? (
          <ArsValjare arsval={arsval} variant="desktop" />
        ) : (
          <span className="bok-mono text-[13px] text-bok-text-dampad">{arsrad}</span>
        )}
        <AgentStatus state={agent?.state} pausadOrsak={agent?.paused_reason} />
      </div>
    </header>
  );
}
