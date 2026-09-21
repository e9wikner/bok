"use client";

import { useSyncExternalStore } from "react";

/**
 * Brytpunkten mellan desktoplayouten och mobilmönstret.
 *
 * README.md §Skärmar: "Under ungefär 1000 px ska vyn läggas över chatten
 * enligt mobilmönstret i stället för att pressas smalare." Vykolumnen är
 * fast 470 — under 1000 px finns det ingen chattkolumn kvar att krympa.
 *
 * `useSyncExternalStore` i stället för useState+useEffect: servern ser
 * `true` och klienten sin riktiga bredd, utan hydreringsvarning.
 */
const FRAGA = "(min-width: 1000px)";

function prenumerera(uppdatera: () => void) {
  const mq = window.matchMedia(FRAGA);
  mq.addEventListener("change", uppdatera);
  return () => mq.removeEventListener("change", uppdatera);
}

export function useBredSkarm(): boolean {
  return useSyncExternalStore(
    prenumerera,
    () => window.matchMedia(FRAGA).matches,
    () => true
  );
}
