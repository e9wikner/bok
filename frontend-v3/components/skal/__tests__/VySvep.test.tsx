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

describe("piltangenterna (#57)", () => {
  function rendera(onIndexChange: (i: number) => void) {
    render(
      <VySvep
        sida={bocker}
        aktivIndex={1}
        onIndexChange={onIndexChange}
        renderVy={(vy, i) => (
          <div>
            {vy.titel}
            {i === 1 && <textarea aria-label="Verksamhetens art och inriktning" />}
            {i === 1 && <div contentEditable suppressContentEditableWarning aria-label="redigerbar" role="textbox" />}
          </div>
        )}
      />
    );
  }

  it("piltangent utanför textrutor byter vy", () => {
    const onIndexChange = vi.fn();
    rendera(onIndexChange);
    fireEvent.keyDown(screen.getByRole("group", { name: /Vyer i Böcker/ }), { key: "ArrowRight" });
    expect(onIndexChange).toHaveBeenCalledWith(2);
  });

  it("piltangent i en textruta flyttar markören, inte sidan", () => {
    const onIndexChange = vi.fn();
    rendera(onIndexChange);
    const ruta = screen.getByLabelText("Verksamhetens art och inriktning");
    const vanster = fireEvent.keyDown(ruta, { key: "ArrowLeft" });
    fireEvent.keyDown(ruta, { key: "ArrowRight" });
    expect(onIndexChange).not.toHaveBeenCalled();
    // Inte förhindrad: webbläsaren ska få flytta markören.
    expect(vanster).toBe(true);
  });

  it("piltangent i contentEditable byter inte vy", () => {
    const onIndexChange = vi.fn();
    rendera(onIndexChange);
    fireEvent.keyDown(screen.getByRole("textbox", { name: "redigerbar" }), { key: "ArrowRight" });
    expect(onIndexChange).not.toHaveBeenCalled();
  });

  it("piltangent med modifierare byter inte vy", () => {
    const onIndexChange = vi.fn();
    rendera(onIndexChange);
    fireEvent.keyDown(screen.getByRole("group", { name: /Vyer i Böcker/ }), { key: "ArrowRight", shiftKey: true });
    expect(onIndexChange).not.toHaveBeenCalled();
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
