import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  satteBredd(URSPRUNGLIG_BREDD);
});

// jsdom saknar scrollTo på element; svepraden (VySvep) anropar den.
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = vi.fn() as unknown as typeof Element.prototype.scrollTo;
}

/**
 * jsdom har ingen matchMedia. Stubben svarar mot window.innerWidth så att
 * brytpunkten 1000 px (desktop kontra mobilmönster) går att testa åt båda
 * hållen i stället för att alltid falla på samma sida.
 */
const URSPRUNGLIG_BREDD = window.innerWidth; // jsdom: 1024 → bred skärm
const lyssnare = new Set<() => void>();

window.matchMedia = ((query: string) => {
  const min = /\(min-width:\s*(\d+)px\)/.exec(query);
  const matchar = () => (min ? window.innerWidth >= Number(min[1]) : false);
  return {
    get matches() {
      return matchar();
    },
    media: query,
    onchange: null,
    addListener: (cb: () => void) => lyssnare.add(cb),
    removeListener: (cb: () => void) => lyssnare.delete(cb),
    addEventListener: (_: string, cb: () => void) => lyssnare.add(cb),
    removeEventListener: (_: string, cb: () => void) => lyssnare.delete(cb),
    dispatchEvent: () => false,
  };
}) as unknown as typeof window.matchMedia;

export function satteBredd(bredd: number) {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: bredd,
  });
  lyssnare.forEach((cb) => cb());
}
