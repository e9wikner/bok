import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ChattBubbla } from "@/components/skal/ChattBubbla";
import type { UseTrad } from "@/hooks/useTrad";

const tradSvar: UseTrad = {
  inlagg: [],
  strommande: null,
  skicka: async () => true,
  laddar: false,
  fel: null,
  kontextFran: 0,
  nollstalldVid: null,
  nollstall: async () => true,
};
vi.mock("@/hooks/useTrad", () => ({ useTrad: () => tradSvar }));

describe("desktopens chatt är en bubbla", () => {
  it("börjar stängd; bubblan öppnar panelen med vyns fält", () => {
    render(<ChattBubbla vyTitel="Rapporter" viewKey="bokslut.rapporter" vantandeBeslut={0} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Öppna chatten för Rapporter" }));
    const panel = screen.getByRole("dialog", { name: "Chatt · Rapporter" });
    expect(panel).toBeVisible();
    expect(screen.getByLabelText(/Fråga om en post i rapporter/i)).toBeInTheDocument();
  });

  it("Escape stänger panelen", () => {
    render(<ChattBubbla vyTitel="Rapporter" viewKey="bokslut.rapporter" vantandeBeslut={0} />);
    fireEvent.click(screen.getByRole("button", { name: /Öppna chatten/ }));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("väntande beslut syns som ett märke på den stängda bubblan", () => {
    render(<ChattBubbla vyTitel="Verifikationer" viewKey="bocker.verifikationer" vantandeBeslut={3} />);
    expect(screen.getByTestId("chattbubbla-marke")).toHaveTextContent("3");
    expect(screen.getByRole("button", { name: /3 väntar på beslut/ })).toBeInTheDocument();
  });
});

describe("klick utanför stänger chatten", () => {
  it("ett klick i vyn stänger panelen, ett klick i panelen gör det inte", () => {
    render(
      <>
        <p>Vyn</p>
        <ChattBubbla vyTitel="Rapporter" viewKey="bokslut.rapporter" vantandeBeslut={0} />
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: /Öppna chatten/ }));
    fireEvent.pointerDown(screen.getByLabelText(/Fråga om en post i rapporter/i));
    expect(screen.getByRole("dialog")).toBeVisible();
    fireEvent.pointerDown(screen.getByText("Vyn"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("bubblan räknas inte som utanför: den stänger med ett klick, öppnar inte igen", () => {
    render(<ChattBubbla vyTitel="Rapporter" viewKey="bokslut.rapporter" vantandeBeslut={0} />);
    fireEvent.click(screen.getByRole("button", { name: /Öppna chatten/ }));
    const bubbla = screen.getAllByRole("button", { name: "Stäng chatten" }).at(-1)!;
    fireEvent.pointerDown(bubbla);
    fireEvent.click(bubbla);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
