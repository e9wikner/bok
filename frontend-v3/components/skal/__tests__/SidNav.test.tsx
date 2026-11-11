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

  it("fliken där något väntar bär antalet", () => {
    render(
      <SidNav
        aktivVy="bocker.balans"
        metaPerSida={{ bocker: { waiting: true, meta: "2 väntar på dig" } }}
        antalPerVy={{ "bocker.verifikationer": 2, "bocker.balans": 0 }}
        onValjVy={vi.fn()}
      />
    );
    expect(screen.getByTestId("sidnav-antal-bocker.verifikationer")).toHaveTextContent("2");
    expect(screen.getByRole("button", { name: "Verifikationer, 2 väntar på dig" })).toBeInTheDocument();
    expect(screen.queryByTestId("sidnav-antal-bocker.balans")).toBeNull();
  });

  it("bokslutets kontroller står under vyn de gäller, inte under sidan", () => {
    render(
      <SidNav
        aktivVy="bocker.balans"
        metaPerSida={{ bokslut: { waiting: true, meta: "6 att åtgärda i bokslutet" } }}
        metaPerVy={{
          "bokslut.uppgifter": { waiting: true, meta: "5 uppgifter saknas" },
          "bokslut.ink2": { waiting: true, meta: "Bokförd skatt skiljer sig från beräknad" },
        }}
        onValjVy={vi.fn()}
      />
    );
    expect(screen.getByTestId("sidnav-rad-bokslut.uppgifter")).toHaveTextContent("5 uppgifter saknas");
    expect(screen.getByTestId("sidnav-rad-bokslut.ink2")).toHaveTextContent("Bokförd skatt skiljer sig från beräknad");
    expect(screen.queryByText("6 att åtgärda i bokslutet")).toBeNull();
    expect(screen.getByTestId("sidnav-vantar-bokslut")).toBeInTheDocument();
  });

  it("ett annat år där något väntar står överst och byter år", async () => {
    const onValjAr = vi.fn();
    render(
      <SidNav
        aktivVy="bocker.balans"
        metaPerSida={{}}
        andraAr={[{ id: "ar-2026", label: "2026", waiting: 2, meta: "2 väntar på dig" }]}
        onValjVy={vi.fn()}
        onValjAr={onValjAr}
      />
    );
    await userEvent.setup().click(screen.getByTestId("sidnav-annat-ar-ar-2026"));
    expect(onValjAr).toHaveBeenCalledWith("ar-2026");
    expect(screen.getByText("Räkenskapsår 2026")).toBeInTheDocument();
  });
});
