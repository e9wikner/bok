import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SidNav } from "@/components/skal/SidNav";

describe("SidNav", () => {
  it("visar alla sidor och vyer, och markerar den aktiva vyn", () => {
    render(<SidNav aktivVy="bocker.resultat" metaPerSida={{}} onValjVy={vi.fn()} />);
    for (const titel of ["Balansräkning", "Resultaträkning", "Verifikationer", "Fakturering", "Löner", "Översikt", "INK2", "Moms", "Årsredovisning", "Uppgifter"]) {
      expect(screen.getByRole("button", { name: titel })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "Resultaträkning" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Balansräkning" })).not.toHaveAttribute("aria-current");
  });

  it("visar serverns metarad ordagrant och väntar-pricken", () => {
    render(
      <SidNav
        aktivVy="bocker.balans"
        metaPerSida={{ betala: { waiting: true, meta: "Allt är avstämt sedan i morse" } }}
        onValjVy={vi.fn()}
      />
    );
    expect(screen.getByText("Allt är avstämt sedan i morse")).toBeInTheDocument();
    expect(screen.getByTestId("sidnav-vantar-betala")).toBeInTheDocument();
    expect(screen.queryByTestId("sidnav-vantar-bocker")).toBeNull();
  });

  it("ett tryck väljer vyn", async () => {
    const onValjVy = vi.fn();
    render(<SidNav aktivVy="bocker.balans" metaPerSida={{}} onValjVy={onValjVy} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Löner" }));
    expect(onValjVy).toHaveBeenCalledWith("betala.loner");
  });
});
