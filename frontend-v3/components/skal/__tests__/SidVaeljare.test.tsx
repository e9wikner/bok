import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SidVaeljare } from "@/components/skal/SidVaeljare";

const meta = {
  bocker: { waiting: true, meta: "1 väntar på dig" },
  betala: { waiting: false, meta: "Inget väntar" },
  bokslut: { waiting: false, meta: "Inget väntar" },
};

describe("SidVaeljare (testfall 10)", () => {
  it("fäller ut de tre sidorna i designens ordning", async () => {
    const user = userEvent.setup();
    render(<SidVaeljare aktiv="bocker" metaPerSida={meta} onValj={vi.fn()} variant="desktop" />);

    await user.click(screen.getByRole("button", { name: "Välj sida" }));
    const rader = screen.getAllByRole("menuitem");
    expect(rader.map((r) => r.textContent?.slice(0, 6))).toEqual(["Böcker", "Faktur", "Bokslu"]);
  });

  it("stängs med Escape", async () => {
    const user = userEvent.setup();
    render(<SidVaeljare aktiv="bocker" metaPerSida={meta} onValj={vi.fn()} variant="desktop" />);

    await user.click(screen.getByRole("button", { name: "Välj sida" }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("stängs med klick utanför", async () => {
    const user = userEvent.setup();
    render(<SidVaeljare aktiv="bocker" metaPerSida={meta} onValj={vi.fn()} variant="desktop" />);

    await user.click(screen.getByRole("button", { name: "Välj sida" }));
    await user.click(screen.getByTestId("sidvaljare-utanfor"));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("väljer en sida och stänger listan", async () => {
    const user = userEvent.setup();
    const onValj = vi.fn();
    render(<SidVaeljare aktiv="bocker" metaPerSida={meta} onValj={onValj} variant="desktop" />);

    await user.click(screen.getByRole("button", { name: "Välj sida" }));
    await user.click(screen.getByRole("menuitem", { name: /Bokslut/ }));
    expect(onValj).toHaveBeenCalledWith("bokslut");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("bär sidans metarad i väntar-färg när något väntar", async () => {
    render(<SidVaeljare aktiv="bocker" metaPerSida={meta} onValj={vi.fn()} variant="desktop" />);
    const knapp = screen.getByRole("button", { name: "Välj sida" });
    expect(knapp.textContent).toContain("1 väntar på dig");
    expect(knapp.querySelector(".text-bok-vantar-meta")).not.toBeNull();
  });

  it("har en träffyta på minst 44 px", () => {
    render(<SidVaeljare aktiv="bocker" metaPerSida={meta} onValj={vi.fn()} variant="desktop" />);
    expect(screen.getByRole("button", { name: "Välj sida" }).className).toContain("min-h-[44px]");
  });
});
