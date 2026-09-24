"use client";

import { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import type { Sida, Vy } from "@/lib/skal/vyer";

/**
 * Raden AV vyer — designens horisontella scroll-snap-rad.
 *
 * OBS namnkrock: `komponenter.md`:s `VyRad` är en rad INNE i vyn. Den här
 * heter `VySvep` för att det bara ska finnas ett `VyRad`. SPEC-skal.md §6.
 *
 * "Horisontell scroll-snap-rad, svep eller prickar. INGET KARUSELLBIBLIOTEK.
 * Positionen läses av för att markera rätt prick." Riktningen spelar roll:
 * skrollpositionen är sanningen och aktiv vy härleds ur den — inte tvärtom.
 * Därför lyssnar vi på scroll och skrollar bara när index ändrats utifrån.
 */
export function VySvep({
  sida,
  aktivIndex,
  onIndexChange,
  renderVy,
}: {
  sida: Sida;
  aktivIndex: number;
  onIndexChange: (index: number) => void;
  renderVy: (vy: Vy, index: number) => React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const senasteIndex = useRef(aktivIndex);

  // Startposition: en länk till ?vy=verifikationer ska LANDA på den vyn,
  // inte på sidans första. Sätts direkt utan animering — ett svep som
  // användaren inte har gjort ska inte se ut som ett svep.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const placera = () => {
      // scroll-behavior: smooth gäller även programmatisk skrollning, och
      // en animerad startposition hinner avbrytas av snap-ankringen. Hoppa.
      const tidigare = el.style.scrollBehavior;
      el.style.scrollBehavior = "auto";
      el.scrollLeft = el.clientWidth * aktivIndex;
      el.style.scrollBehavior = tidigare;
      senasteIndex.current = aktivIndex;
    };
    placera();
    // Raden kan mätas innan barnen fått bredd; då klamras scrollLeft till 0
    // och vi landar på fel vy. Lägg om positionen efter första målningen.
    const id = requestAnimationFrame(placera);
    return () => cancelAnimationFrame(id);
    // Bara vid montering; komponenten monteras om per sida (key i `Skal`).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Skrolla bara när ändringen kom utifrån (prick, tangent, sidbyte).
  useEffect(() => {
    const el = ref.current;
    if (!el || senasteIndex.current === aktivIndex) return;
    senasteIndex.current = aktivIndex;
    el.scrollTo({ left: el.clientWidth * aktivIndex, behavior: "smooth" });
  }, [aktivIndex]);

  const vidScroll = useCallback(() => {
    const el = ref.current;
    // scrollWidth <= clientWidth betyder att raden ännu inte har mätts upp.
    // Ett scroll-event därifrån rapporterar alltid vy 0 och skulle skriva
    // över startpositionen.
    if (!el || el.clientWidth === 0 || el.scrollWidth <= el.clientWidth) return;
    const index = Math.round(el.scrollLeft / el.clientWidth);
    if (index === senasteIndex.current) return;
    senasteIndex.current = index;
    onIndexChange(index);
  }, [onIndexChange]);

  /** Tangentbordsekvivalenten till svepet (README.md §Tillgänglighet). */
  const vidTangent = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const steg = e.key === "ArrowRight" ? 1 : -1;
    const nytt = aktivIndex + steg;
    // Stannar vid kanterna. Vyer wrappar inte — sidan är gränsen.
    if (nytt < 0 || nytt >= sida.vyer.length) return;
    e.preventDefault();
    onIndexChange(nytt);
  };

  return (
    <div
      ref={ref}
      onScroll={vidScroll}
      onKeyDown={vidTangent}
      tabIndex={0}
      role="group"
      aria-label={`Vyer i ${sida.titel}`}
      className="bok-dold-skroll bok-svep flex min-h-0 flex-1 overflow-x-auto overflow-y-hidden outline-none"
      style={{ scrollSnapType: "x mandatory", scrollBehavior: "smooth" }}
    >
      {sida.vyer.map((vy, i) => (
        <div
          key={vy.key}
          data-view-key={vy.key}
          aria-hidden={i === aktivIndex ? undefined : "true"}
          className="flex w-full min-w-0 shrink-0 grow-0 basis-full flex-col"
          style={{ scrollSnapAlign: "start" }}
        >
          {renderVy(vy, i)}
        </div>
      ))}
    </div>
  );
}
