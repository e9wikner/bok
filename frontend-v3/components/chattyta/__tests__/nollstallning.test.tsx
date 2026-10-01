import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { delaVidGrans, NollstallKnapp, TidigareKonversation } from "@/components/chattyta/Nollstallning";
import { TradYta } from "@/components/skal/ChattKolumn";
import { parseInlagg } from "@/lib/chattyta/parse";
import type { Inlagg, RaInlagg } from "@/lib/chattyta/typer";
import { FIXTUR_AGENT_TEXT, FIXTUR_USER_TEXT } from "@/lib/chattyta/__fixtures__/inlagg";

const typad = (raw: RaInlagg) => parseInlagg(raw) as Inlagg;
const agent = (id: string, seq: number, text: string) =>
  typad({ ...FIXTUR_AGENT_TEXT, id, seq, body: { text }, traces: null, run_id: null });
const du = (id: string, seq: number, text: string) => typad({ ...FIXTUR_USER_TEXT, id, seq, body: { text } });

describe("delaVidGrans", () => {
  it("utan gräns hör allt till efter", () => {
    const inlagg = [agent("a", 1, "x")];
    expect(delaVidGrans(inlagg, 0)).toEqual({ fore: [], efter: inlagg });
  });

  it("delar på seq; optimistiska hör alltid till efter", () => {
    const lokal = { ...du("lokal-1", 1, "skrivs"), seq: -1 };
    const { fore, efter } = delaVidGrans([agent("a", 1, "x"), du("b", 2, "y"), du("c", 3, "z"), lokal], 2);
    expect(fore.map((i) => i.id)).toEqual(["a", "b"]);
    expect(efter.map((i) => i.id)).toEqual(["c", "lokal-1"]);
  });
});

describe("TidigareKonversation", () => {
  it("är hopfälld från början och fälls ut på tryck", () => {
    render(<TidigareKonversation inlagg={[agent("a", 1, "gammalt svar")]} nollstalldVid="2026-09-29T14:02:00" />);
    expect(screen.queryByText("gammalt svar")).not.toBeInTheDocument();

    const knapp = screen.getByRole("button", { name: /1 tidigare inlägg · visa/ });
    expect(knapp).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(knapp);

    expect(screen.getByText("gammalt svar")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /dölj/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("avdelaren säger när konversationen nollställdes", () => {
    render(<TidigareKonversation inlagg={[]} nollstalldVid="2026-09-29T14:02:00" />);
    expect(screen.getByRole("separator")).toHaveAccessibleName("Konversationen nollställd 2026-09-29 14:02");
    // Inget att fälla ut: ingen knapp.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("TradYta med en gräns", () => {
  it("fäller ihop det gamla ovanför avdelaren och visar det nya under", () => {
    render(
      <TradYta
        vyTitel="Balansräkning"
        viewKey="bocker.balans"
        trad={{
          inlagg: [agent("a", 1, "före gränsen"), du("b", 2, "efter gränsen")],
          strommande: null,
          fel: null,
          kontextFran: 1,
          nollstalldVid: "2026-09-29T14:02:00",
        }}
      />
    );
    expect(screen.queryByText("före gränsen")).not.toBeInTheDocument();
    expect(screen.getByText("efter gränsen")).toBeInTheDocument();
    const avdelare = screen.getByTestId("nollstallning-avdelare");
    const nytt = screen.getByText("efter gränsen");
    expect(avdelare.compareDocumentPosition(nytt) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("utan gräns ritas ingen avdelare", () => {
    render(
      <TradYta
        vyTitel="Balansräkning"
        viewKey="bocker.balans"
        trad={{ inlagg: [agent("a", 1, "hej")], strommande: null, fel: null }}
      />
    );
    expect(screen.queryByTestId("nollstallning-avdelare")).not.toBeInTheDocument();
  });
});

describe("NollstallKnapp", () => {
  it("frågar först, nollställer på ja", async () => {
    const onNollstall = vi.fn(async () => true);
    render(<NollstallKnapp onNollstall={onNollstall} arbetar={false} />);

    fireEvent.click(screen.getByRole("button", { name: /ny konversation/ }));
    expect(onNollstall).not.toHaveBeenCalled();
    expect(screen.getByText("Nollställ konversationen?")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "ja" }));
    await waitFor(() => expect(onNollstall).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole("button", { name: /ny konversation/ })).toBeInTheDocument());
  });

  it("avbryt nollställer ingenting", () => {
    const onNollstall = vi.fn(async () => true);
    render(<NollstallKnapp onNollstall={onNollstall} arbetar={false} />);
    fireEvent.click(screen.getByRole("button", { name: /ny konversation/ }));
    fireEvent.click(screen.getByRole("button", { name: "avbryt" }));
    expect(onNollstall).not.toHaveBeenCalled();
  });

  it("är avstängd medan agenten svarar", () => {
    render(<NollstallKnapp onNollstall={async () => true} arbetar />);
    expect(screen.getByRole("button", { name: /ny konversation/ })).toBeDisabled();
  });

  it("säger till när servern sa nej", async () => {
    render(<NollstallKnapp onNollstall={async () => false} arbetar={false} />);
    fireEvent.click(screen.getByRole("button", { name: /ny konversation/ }));
    fireEvent.click(screen.getByRole("button", { name: "ja" }));
    expect(await screen.findByText("kunde inte nollställas")).toBeInTheDocument();
  });
});
