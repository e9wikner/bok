import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { VySvep } from "@/components/skal/VySvep";
import { sidan } from "@/lib/skal/vyer";

const bocker = sidan("bocker");
const BREDD = 800;

function medBredd(fn: () => void) {
  const original = {
    clientWidth: Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientWidth"),
    scrollWidth: Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollWidth"),
  };
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get: () => BREDD,
  });
  // Tre vyer breda: raden är uppmätt, vilket är villkoret för att ett
  // scroll-event ska tas på allvar.
  Object.defineProperty(HTMLElement.prototype, "scrollWidth", {
    configurable: true,
    get: () => BREDD * 3,
  });
  try {
    fn();
  } finally {
    if (original.clientWidth)
      Object.defineProperty(HTMLElement.prototype, "clientWidth", original.clientWidth);
    if (original.scrollWidth)
      Object.defineProperty(HTMLElement.prototype, "scrollWidth", original.scrollWidth);
  }
}

afterEach(() => vi.restoreAllMocks());

describe("svepradens startposition", () => {
  it("landar på vyn i URL:en, inte på sidans första", () => {
    medBredd(() => {
      const { container } = render(
        <VySvep
          sida={bocker}
          aktivIndex={2}
          onIndexChange={vi.fn()}
          renderVy={(vy) => <div>{vy.titel}</div>}
        />
      );
      const rad = container.querySelector('[role="group"]') as HTMLElement;
      expect(rad.scrollLeft).toBe(BREDD * 2);
    });
  });

  it("startar på noll när ingen vy är vald", () => {
    medBredd(() => {
      const { container } = render(
        <VySvep
          sida={bocker}
          aktivIndex={0}
          onIndexChange={vi.fn()}
          renderVy={(vy) => <div>{vy.titel}</div>}
        />
      );
      expect((container.querySelector('[role="group"]') as HTMLElement).scrollLeft).toBe(0);
    });
  });
});

describe("positionen är sanningen, inte klicket", () => {
  it("skrollning i sidled markerar rätt vy", () => {
    medBredd(() => {
      const onIndexChange = vi.fn();
      render(
        <VySvep
          sida={bocker}
          aktivIndex={0}
          onIndexChange={onIndexChange}
          renderVy={(vy) => <div>{vy.titel}</div>}
        />
      );
      const rad = screen.getByRole("group", { name: /Vyer i Böcker/ });
      rad.scrollLeft = BREDD; // ett svep, inget klick
      fireEvent.scroll(rad);
      expect(onIndexChange).toHaveBeenCalledWith(1);
    });
  });

  it("rapporterar inte om positionen inte bytte vy", () => {
    medBredd(() => {
      const onIndexChange = vi.fn();
      render(
        <VySvep
          sida={bocker}
          aktivIndex={0}
          onIndexChange={onIndexChange}
          renderVy={(vy) => <div>{vy.titel}</div>}
        />
      );
      const rad = screen.getByRole("group", { name: /Vyer i Böcker/ });
      rad.scrollLeft = 30; // rundas till samma vy
      fireEvent.scroll(rad);
      expect(onIndexChange).not.toHaveBeenCalled();
    });
  });
});
