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

const LAGEN: Record<Exclude<AgentState, "vilande">, { text: string; prick: string; fg: string }> = {
  arbetar: { text: "Agenten arbetar", prick: "#16a34a", fg: "#15803d" },
  postar: { text: "Agenten postar", prick: "#2563d9", fg: "#1b49a3" },
  pausad: { text: "Agenten pausad", prick: "#dc2626", fg: "#b91c1c" },
};

export function AgentStatus({
  state,
  pausadOrsak,
}: {
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
      title={state === "pausad" && pausadOrsak ? pausadOrsak : undefined}
    >
      <span
        aria-hidden="true"
        className="h-[7px] w-[7px] rounded-full"
        style={{ background: lage.prick }}
      />
      {lage.text}
    </div>
  );
}
