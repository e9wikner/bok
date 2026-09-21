"use client";

import { AgentStatus } from "@/components/skal/AgentStatus";
import { PrickNav } from "@/components/skal/PrickNav";
import { SidVaeljare, type SidMeta } from "@/components/skal/SidVaeljare";
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
export function Header({
  variant,
  sida,
  aktivVy,
  aktivIndex,
  metaPerSida,
  arsrad,
  vyStatus,
  agent,
  onValjSida,
  onValjVy,
}: {
  variant: "desktop" | "mobil";
  sida: Sida;
  aktivVy: Vy;
  aktivIndex: number;
  metaPerSida: Partial<Record<Sidnyckel, SidMeta>>;
  /** T.ex. "Räkenskapsår 2026 · juni öppen". Serverns fält, klientens skiljetecken. */
  arsrad: string;
  vyStatus: { text: string; fg: string };
  agent?: AgentStatusData;
  onValjSida: (s: Sidnyckel) => void;
  onValjVy: (index: number) => void;
}) {
  if (variant === "mobil") {
    return (
      <header
        className="flex h-[56px] shrink-0 items-center justify-between gap-3 border-b border-bok-linje-svag bg-bok-yta px-[14px]"
        style={{ position: "relative", zIndex: 6 }}
      >
        <SidVaeljare aktiv={sida.key} metaPerSida={metaPerSida} onValj={onValjSida} variant="mobil" />
        {/* v10:s mobilram har ingen plats för AgentStatus, men komponenter.md
            är uttrycklig: pausad "ska visas så länge den är pausad, inte bara
            i felinlägget". Därför visas det ena läget som designen kräver ska
            synas, och inte de två som den inte säger något om. Avvikelsen
            står i tasks/skal/todo.md. */}
        {agent?.state === "pausad" && (
          <div className="shrink-0">
            <AgentStatus state={agent.state} pausadOrsak={agent.paused_reason} />
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
      className="flex h-[62px] shrink-0 items-center justify-between border-b border-bok-linje bg-bok-yta px-5"
      style={{ position: "relative", zIndex: 6 }}
    >
      <div className="flex items-center gap-4">
        <SidVaeljare
          aktiv={sida.key}
          metaPerSida={metaPerSida}
          onValj={onValjSida}
          variant="desktop"
        />
        {/* Öppen fråga 1: var bolagsnamnet kommer ifrån. GET /overview bär
            det inte, och enbolagsantagandet gör en väljare fel. Tills någon
            säger var namnet bor står det bara "BokAi" — skärmbildens
            "Wikner Teknik AB" är exempeldata, inte ett fält. */}
        <span className="text-[14px] text-bok-meta">BokAi</span>
      </div>

      <div className="flex items-center gap-5">
        <span className="bok-mono text-[13px]" style={{ color: vyStatus.fg }}>
          {aktivVy.titel} · {vyStatus.text}
        </span>
        <span className="bok-mono text-[13px] text-bok-text-dampad">{arsrad}</span>
        <AgentStatus state={agent?.state} pausadOrsak={agent?.paused_reason} />
      </div>
    </header>
  );
}
