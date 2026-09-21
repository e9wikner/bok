import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PrickNav } from "@/components/skal/PrickNav";
import { VySvep } from "@/components/skal/VySvep";
import { sidan } from "@/lib/skal/vyer";

const bocker = sidan("bocker");

describe("PrickNav är riktiga knappar (testfall 11)", () => {
  it("har en knapp per vy med vyns namn som aria-label", () => {
    render(<PrickNav vyer={bocker.vyer} aktivIndex={0} onValj={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Balansräkning" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resultaträkning" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Verifikationer" })).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(3);
  });

  it("markerar aktiv vy med aria-current", () => {
    render(<PrickNav vyer={bocker.vyer} aktivIndex={2} onValj={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Verifikationer" })).toHaveAttribute(
      "aria-current",
      "true"
    );
    expect(screen.getByRole("button", { name: "Balansräkning" })).not.toHaveAttribute(
      "aria-current"
    );
  });

  it("har en träffyta på 44 px trots att pricken är 7", () => {
    render(<PrickNav vyer={bocker.vyer} aktivIndex={0} onValj={vi.fn()} />);
    const knapp = screen.getByRole("button", { name: "Balansräkning" });
    expect(knapp.style.height).toBe("44px");
  });

  it("byter vy när man trycker på en prick", async () => {
    const user = userEvent.setup();
    const onValj = vi.fn();
    render(<PrickNav vyer={bocker.vyer} aktivIndex={0} onValj={onValj} />);
    await user.click(screen.getByRole("button", { name: "Verifikationer" }));
    expect(onValj).toHaveBeenCalledWith(2);
  });
});

describe("piltangenterna är svepets ekvivalent (testfall 12)", () => {
  function renderaSvep(aktivIndex: number, onIndexChange = vi.fn()) {
    render(
      <VySvep
        sida={bocker}
        aktivIndex={aktivIndex}
        onIndexChange={onIndexChange}
        renderVy={(vy) => <div>{vy.titel}</div>}
      />
    );
    return { grupp: screen.getByRole("group", { name: /Vyer i Böcker/ }), onIndexChange };
  }

  it("går framåt med högerpil", () => {
    const { grupp, onIndexChange } = renderaSvep(0);
    fireEvent.keyDown(grupp, { key: "ArrowRight" });
    expect(onIndexChange).toHaveBeenCalledWith(1);
  });

  it("går bakåt med vänsterpil", () => {
    const { grupp, onIndexChange } = renderaSvep(2);
    fireEvent.keyDown(grupp, { key: "ArrowLeft" });
    expect(onIndexChange).toHaveBeenCalledWith(1);
  });

  it("stannar vid sidans första vy", () => {
    const { grupp, onIndexChange } = renderaSvep(0);
    fireEvent.keyDown(grupp, { key: "ArrowLeft" });
    expect(onIndexChange).not.toHaveBeenCalled();
  });

  it("stannar vid sidans sista vy — vyer wrappar inte till nästa sida", () => {
    const { grupp, onIndexChange } = renderaSvep(2);
    fireEvent.keyDown(grupp, { key: "ArrowRight" });
    expect(onIndexChange).not.toHaveBeenCalled();
  });

  it("renderar sidans alla vyer i raden, inte bara den aktiva", () => {
    renderaSvep(0);
    expect(screen.getByText("Balansräkning")).toBeInTheDocument();
    expect(screen.getByText("Verifikationer")).toBeInTheDocument();
  });
});
