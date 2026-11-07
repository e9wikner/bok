"use client";

import type { AgentState } from "@/lib/skal/api";

/**
 * `AgentStatus` (komponenter.md): prick 7×7 + text 13.
 *
 * Tre namngivna lägen. Det fjärde, `vilande`, är det vanliga fallet att
 * ingenting händer — designen ritar det som ingen indikator alls.
 *
 * Pausad ska visas så länge den är pausad, "inte bara i felinlägget".
 */

const LAGEN: Record<
  Exclude<AgentState, "vilande">,
  { text: string; kort: string; prick: string; fg: string }
> = {
  arbetar: { text: "Agenten arbetar", kort: "Arbetar", prick: "#16a34a", fg: "#15803d" },
  postar: { text: "Agenten postar", kort: "Postar", prick: "#2563d9", fg: "#1b49a3" },
  pausad: { text: "Agenten pausad", kort: "Pausad", prick: "#dc2626", fg: "#b91c1c" },
};

/** Serverns `paused_reason` som en mening. En okänd kod visas som den är. */
const ORSAKER: Record<string, string> = {
  agent_runtime_disabled: "Agenten är avstängd på servern.",
  agent_runtime_not_started: "Agenten har inte startat på servern.",
  llm_rate_limited: "Språkmodellens gräns är nådd. Agenten fortsätter när gränsen släpper.",
};

export function pausOrsak(kod: string): string {
  return ORSAKER[kod] ?? kod;
}

export function AgentStatus({
  state,
  pausadOrsak,
  kompakt = false,
}: {
  /**
   * Mobilens header: bara verbet ("Pausad"). Med sex vyprickar på Bokslut
   * räckte inte bredden till hela texten, och året lades ovanpå den.
   */
  kompakt?: boolean;
  /**
   * `undefined` när statusanropet inte gick fram. Då visas INGENTING —
   * aldrig "pausad". Pausad är ett riktigt läge med en orsak, och att gissa
   * det ur ett nätverksfel vore en lögn i produkttonen. SPEC-skal.md §8.
   */
  state?: AgentState;
  pausadOrsak?: string | null;
}) {
  if (!state || state === "vilande") return null;
  const lage = LAGEN[state];
  if (!lage) return null;

  return (
    <div
      className="flex items-center gap-[7px] text-[13px]"
      style={{ color: lage.fg }}
      title={state === "pausad" && pausadOrsak ? pausOrsak(pausadOrsak) : kompakt ? lage.text : undefined}
    >
      <span
        aria-hidden="true"
        className="h-[7px] w-[7px] rounded-full"
        style={{ background: lage.prick }}
      />
      {kompakt ? lage.kort : lage.text}
    </div>
  );
}
