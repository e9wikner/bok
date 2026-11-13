import { Suspense } from "react";
import { Skal } from "@/components/skal/Skal";

/**
 * Appen: skalet (modul `skal`), med sida och vy i ?sida=&vy= (`lib/skal/rutt.ts`).
 */
export default function Hem() {
  return (
    <Suspense fallback={null}>
      <Skal />
    </Suspense>
  );
}
