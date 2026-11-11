import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { ChattBubbla } from "@/components/skal/ChattBubbla";
import type { UseTrad, UseTradAlternativ } from "@/hooks/useTrad";
import type { StromAlternativ } from "@/lib/chattyta/strom";

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
let tradAlternativ: UseTradAlternativ = {};
vi.mock("@/hooks/useTrad", async (original) => ({
  ...(await original<typeof import("@/hooks/useTrad")>()),
  useTrad: (_vk: string, _ar: string | null, alt: UseTradAlternativ = {}) => {
    tradAlternativ = alt;
    return tradSvar;
  },
}));
const oppnaStrom = vi.fn(
  (a: StromAlternativ) =>
    new Promise<void>((klar) => a.signal.addEventListener("abort", () => klar()))
);
vi.mock("@/lib/chattyta/strom", () => ({
  oppnaStrom: (a: StromAlternativ) => oppnaStrom(a),
}));

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

describe("ett agentsvar öppnar inte chatten, det syns på bubblan", () => {
  it("svar i den aktiva tråden medan panelen är stängd: prick, ingen panel; öppnad är det läst", () => {
    tradAlternativ = {};
    render(<ChattBubbla vyTitel="Rapporter" viewKey="bokslut.rapporter" vantandeBeslut={0} />);
    expect(screen.queryByTestId("chattbubbla-svar")).not.toBeInTheDocument();

    act(() => tradAlternativ.onAgentSvar?.());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByTestId("chattbubbla-svar")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /nytt svar/ }));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByTestId("chattbubbla-svar")).not.toBeInTheDocument();
  });

  it("svar medan panelen är öppen är redan läst", () => {
    tradAlternativ = {};
    render(<ChattBubbla vyTitel="Rapporter" viewKey="bokslut.rapporter" vantandeBeslut={0} />);
    fireEvent.click(screen.getByRole("button", { name: /Öppna chatten/ }));
    act(() => tradAlternativ.onAgentSvar?.());
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByTestId("chattbubbla-svar")).not.toBeInTheDocument();
  });

  it("svar i en lämnad vys tråd: prick på bubblan och en väg dit i panelen", () => {
    tradAlternativ = {};
    const gaTillTrad = vi.fn();
    const { rerender } = render(
      <ChattBubbla vyTitel="Löner" viewKey="betala.loner" vantandeBeslut={0} gaTillTrad={gaTillTrad} />
    );
    act(() =>
      tradAlternativ.onLamnadUtanSvar?.({ viewKey: "bocker.verifikationer", fiscalYearId: null, since: 4 })
    );
    const strom = oppnaStrom.mock.calls[oppnaStrom.mock.calls.length - 1][0];
    expect(strom).toMatchObject({ viewKey: "bocker.verifikationer", since: 4 });

    act(() => strom.onHandelse({ event: "message.created", data: { id: "streaming-r", run_id: "r" } }));
    expect(screen.queryByTestId("chattbubbla-svar")).not.toBeInTheDocument();
    act(() =>
      strom.onHandelse({ event: "message.completed", data: { id: "p-5", seq: 5, type: "agent_text" } })
    );
    expect(strom.signal.aborted).toBe(true);
    expect(screen.getByTestId("chattbubbla-svar")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /nytt svar i Verifikationer/ }));
    fireEvent.click(screen.getByRole("button", { name: "Nytt svar i Verifikationer →" }));
    expect(gaTillTrad).toHaveBeenCalledWith("bocker.verifikationer");

    rerender(
      <ChattBubbla vyTitel="Verifikationer" viewKey="bocker.verifikationer" vantandeBeslut={0} gaTillTrad={gaTillTrad} />
    );
    expect(screen.queryByRole("button", { name: /Nytt svar i/ })).not.toBeInTheDocument();
  });
});
