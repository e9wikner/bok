import { notFound } from "next/navigation";
import { Suspense } from "react";
import { Skal } from "@/components/skal/Skal";
import { skalArPa } from "@/lib/skal/rutt";

/**
 * Det nya skalet (modul `skal`), BREDVID de 24 befintliga sidorna.
 *
 * Flaggan är en byggtidsvariabel utan växel i gränssnittet: utan
 * NEXT_PUBLIC_SKAL=1 finns rutten inte. De gamla sidorna står orörda och
 * tas bort vy för vy när motsvarigheten här är i bruk — ANALYS.md §8b,
 * beslutad väg (b), SPEC-skal.md §3.
 *
 * `/v4` är avsiktligt temporärt. När de gamla sidorna är borta blir skalet
 * `/` och den här rutten försvinner.
 */
export default function V4Page() {
  if (!skalArPa()) notFound();
  return (
    <Suspense fallback={null}>
      <Skal />
    </Suspense>
  );
}
