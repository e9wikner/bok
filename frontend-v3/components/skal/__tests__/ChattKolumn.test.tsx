import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { ChattKolumn, TradYta } from "@/components/skal/ChattKolumn";
import { ChattList } from "@/components/skal/ChattList";
import type { UseTrad } from "@/hooks/useTrad";
import { parseInlagg } from "@/lib/chattyta/parse";
import type { Inlagg, RaInlagg } from "@/lib/chattyta/typer";
import {
  FIXTUR_AGENT_TEXT,
  FIXTUR_OPTIONS,
  FIXTUR_USER_TEXT,
  kropp,
} from "@/lib/chattyta/__fixtures__/inlagg";

// Tråden kommer ur `useTrad` sedan chattyta C5 — skalets egen mock är borta.
// Skalets tester prövar layouten, så hooken ersätts med ett fast svar.
const typad = (raw: RaInlagg) => parseInlagg(raw) as Inlagg;
const trad: Inlagg[] = [
  typad({ ...FIXTUR_AGENT_TEXT, body: { text: "Balansräkningen är uppdaterad per i morse." } }),
  typad(FIXTUR_USER_TEXT),
];

const tradSvar: UseTrad = {
  inlagg: trad,
  strommande: null,
  skicka: async () => true,
  laddar: false,
  fel: null,
};
const useTrad = vi.fn((_viewKey: string): UseTrad => tradSvar);
vi.mock("@/hooks/useTrad", () => ({ useTrad: (vk: string) => useTrad(vk) }));

beforeEach(() => {
  useTrad.mockClear();
  useTrad.mockImplementation(() => tradSvar);
});

describe("ChattFalt är ren text — inga förslagschips (spec §2.1)", () => {
  it("har ett textfält och ingen enda knapp under det", () => {
    const { container } = render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    const form = container.querySelector("form")!;
    expect(within(form).getByRole("textbox")).toBeInTheDocument();
    // Ett chip är ett förvalt yttrande. Designens egen regel är att
    // ingenting förväljs — lägg inte tillbaka dem.
    expect(within(form).queryAllByRole("button")).toHaveLength(0);
  });

  it("fältet har en etikett som namnger vyn", () => {
    render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    expect(screen.getByLabelText(/Fråga om en post i balansräkning/i)).toBeInTheDocument();
  });
});

describe("tråden kommer ur useTrad och ritas av chattytans renderare", () => {
  it("läser vyns tråd med vyns nyckel", () => {
    render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    expect(useTrad).toHaveBeenCalledWith("bocker.balans");
  });

  it("renderar agentens text och egen replik", () => {
    render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    expect(screen.getByText(/Balansräkningen är uppdaterad/)).toBeInTheDocument();
    expect(screen.getByText("Vad består kundfordringarna av?")).toBeInTheDocument();
  });

  it("annonserar genom trådens dolda live-region, inte hela ytan (chattyta testfall 31)", () => {
    render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    const trad = screen.getByLabelText("Tråd för Balansräkning");
    // Ytan som live-region läste upp varje delta ord för ord (SPEC-chattyta §11).
    expect(trad).not.toHaveAttribute("aria-live");
    expect(within(trad).getByTestId("trad-annons")).toHaveAttribute("aria-live", "polite");
  });

  it("skalet bygger inga kort själv — ett kontraktsbrott blir okant_kontrakt, inte ett halvt kort", () => {
    // Alla åtta typer har en renderare i `chattyta` sedan C13; raden återstår
    // bara för brott (SPEC-chattyta.md §4.4). Här: ett `options` med två
    // rekommenderade, som `parseInlagg` vägrar (§4.1).
    const tvaRekommenderade = typad({
      ...FIXTUR_OPTIONS,
      body: {
        ...kropp(FIXTUR_OPTIONS),
        options: (kropp(FIXTUR_OPTIONS).options as Record<string, unknown>[]).map((o) => ({
          ...o,
          recommended: true,
        })),
      },
    });
    expect(tvaRekommenderade.type).toBe("okant_kontrakt");
    useTrad.mockImplementation(() => ({ ...tradSvar, inlagg: [tvaRekommenderade] }));
    render(<ChattKolumn vyTitel="Verifikationer" viewKey="bocker.verifikationer" />);
    expect(
      screen.getByText(`kortet kunde inte visas · options · ${FIXTUR_OPTIONS.id}`)
    ).toBeInTheDocument();
  });

  it("tråden är bottenankrad", () => {
    render(<ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" />);
    const inre = screen.getByLabelText("Tråd för Balansräkning").firstElementChild!;
    expect(inre.className).toContain("justify-end");
    expect(inre.className).toContain("min-h-full");
  });

  it.each(["desktop", "mobil"] as const)(
    "tråden skrollar i stället för att klippa de äldsta inläggen (%s)",
    (variant) => {
      // Före rättelsen: `overflow-hidden` + `justify-end` på samma element.
      // En tråd högre än kolumnen tappade sina äldsta inlägg ovanför kanten,
      // och det fanns inget sätt att nå dem.
      render(
        <TradYta vyTitel="Verifikationer" viewKey="bocker.verifikationer" trad={tradSvar} variant={variant} />
      );
      const yta = screen.getByLabelText("Tråd för Verifikationer");
      expect(yta.className).toContain("overflow-y-auto");
      expect(yta.className).not.toContain("overflow-hidden");
      // Bottenankringen sitter på det inre elementet — på skrollelementet
      // självt gör `justify-end` överflödet ovanför oåtkomligt.
      expect(yta.className).not.toContain("justify-end");
    }
  );

  it("inläggen krymper inte när tråden är högre än ytan — ett kort klipps aldrig (chattyta C14)", () => {
    // Hittat vid visuell kontroll: ett kort med `overflow-hidden` fick
    // flexens `min-height: 0` och krympte, och AlternativListans sista rad —
    // vägen ut — klipptes bort. Gäller både desktop och mobil.
    const { rerender } = render(
      <TradYta vyTitel="Verifikationer" viewKey="bocker.verifikationer" trad={tradSvar} />
    );
    const inre = () => screen.getByLabelText("Tråd för Verifikationer").firstElementChild!;
    expect(inre().className).toContain("[&>*]:shrink-0");
    rerender(
      <TradYta vyTitel="Verifikationer" viewKey="bocker.verifikationer" trad={tradSvar} variant="mobil" />
    );
    expect(inre().className).toContain("[&>*]:shrink-0");
  });
});

describe("varje kolumns fält har sitt eget id", () => {
  it("två kolumner på skärmen: etiketten pekar på sin egen kolumns fält", () => {
    // Före rättelsen hade alla fält `id="skal-chattfalt"`, så etiketten i
    // andra kolumnen pekade på första kolumnens fält.
    render(
      <>
        <ChattKolumn vyTitel="Balansräkning" viewKey="bocker.balans" aktiv={false} />
        <ChattKolumn vyTitel="Resultaträkning" viewKey="bocker.resultat" aktiv={false} />
      </>
    );
    const balans = screen.getByLabelText(/i balansräkning/i);
    const resultat = screen.getByLabelText(/i resultaträkning/i);
    expect(balans).not.toBe(resultat);
    expect(balans.id).not.toBe(resultat.id);
    expect(document.querySelectorAll(`[id="${balans.id}"]`)).toHaveLength(1);
  });
});

describe("tråden följer med nedåt — men bara när man redan är längst ner", () => {
  /** jsdom räknar ingen layout; måtten sätts för hand. */
  function mat(el: HTMLElement, { hojd, synlig }: { hojd: number; synlig: number }) {
    Object.defineProperty(el, "scrollHeight", { configurable: true, get: () => hojd });
    Object.defineProperty(el, "clientHeight", { configurable: true, get: () => synlig });
  }
  const mer = (n: number): UseTrad => ({
    ...tradSvar,
    inlagg: [
      ...trad,
      ...Array.from({ length: n }, (_, i) =>
        typad({ ...FIXTUR_AGENT_TEXT, id: `ny-${i}`, seq: 10 + i })
      ),
    ],
  });

  it("ett nytt inlägg skrollar fram när man var längst ner", () => {
    const { rerender } = render(
      <TradYta vyTitel="Resultat" viewKey="bocker.resultat" trad={tradSvar} />
    );
    const yta = screen.getByLabelText("Tråd för Resultat");
    mat(yta, { hojd: 2000, synlig: 500 });
    rerender(<TradYta vyTitel="Resultat" viewKey="bocker.resultat" trad={mer(1)} />);
    expect(yta.scrollTop).toBe(2000);
  });

  it("den som skrollat upp för att läsa blir kvar där den är", () => {
    const { rerender } = render(
      <TradYta vyTitel="Resultat" viewKey="bocker.resultat" trad={tradSvar} />
    );
    const yta = screen.getByLabelText("Tråd för Resultat");
    mat(yta, { hojd: 2000, synlig: 500 });
    yta.scrollTop = 300; // långt från botten (2000 − 500 = 1500)
    yta.dispatchEvent(new Event("scroll"));
    rerender(<TradYta vyTitel="Resultat" viewKey="bocker.resultat" trad={mer(1)} />);
    expect(yta.scrollTop).toBe(300);
  });

  it("strömmande text följer också med", () => {
    const { rerender } = render(
      <TradYta vyTitel="Resultat" viewKey="bocker.resultat" trad={tradSvar} />
    );
    const yta = screen.getByLabelText("Tråd för Resultat");
    mat(yta, { hojd: 1200, synlig: 500 });
    rerender(
      <TradYta
        vyTitel="Resultat"
        viewKey="bocker.resultat"
        trad={{ ...tradSvar, strommande: { id: "streaming-r", run_id: "r", text: "Jag läser", activity: null } }}
      />
    );
    expect(yta.scrollTop).toBe(1200);
  });
});

describe("ChattList på mobilen (testfall 16)", () => {
  it("visar märket för väntande beslut även när chatten är minimerad", async () => {
    const { getByRole, getByTestId } = render(
      <ChattList vyTitel="Verifikationer" viewKey="bocker.verifikationer" vantandeBeslut={1} />
    );
    const knapp = getByRole("button", { name: "Visa eller minimera chatten" });
    expect(getByTestId("chattlist-marke")).toHaveTextContent("1 väntar");

    knapp.click();
    // Minimerad: tråden är borta, märket är kvar.
    expect(getByTestId("chattlist-marke")).toHaveTextContent("1 väntar");
  });

  it("märket bär väntar-färgen bara när något faktiskt väntar", () => {
    const { getByTestId, rerender } = render(
      <ChattList vyTitel="Verifikationer" viewKey="bocker.verifikationer" vantandeBeslut={1} />
    );
    expect(getByTestId("chattlist-marke").style.color).toContain("vantar");

    rerender(<ChattList vyTitel="Balansräkning" viewKey="bocker.balans" vantandeBeslut={0} />);
    expect(getByTestId("chattlist-marke").style.color).not.toContain("vantar");
  });

  it("utan väntande beslut räknar märket trådens inlägg", () => {
    const { getByTestId } = render(
      <ChattList vyTitel="Balansräkning" viewKey="bocker.balans" vantandeBeslut={0} />
    );
    expect(getByTestId("chattlist-marke")).toHaveTextContent(`${trad.length} inlägg`);
  });

  it("läser tråden en gång, inte en gång för listen och en för tråden i den", () => {
    render(<ChattList vyTitel="Balansräkning" viewKey="bocker.balans" vantandeBeslut={0} />);
    expect(new Set(useTrad.mock.calls.map(([vk]) => vk))).toEqual(new Set(["bocker.balans"]));
    // En rendering = ett anrop; två komponenter som båda anropar hooken
    // vore två strömmar mot samma tråd.
    expect(useTrad.mock.calls.length).toBe(1);
  });

  it("listen är minst 50 px hög, som designen kräver", () => {
    const { getByRole } = render(
      <ChattList vyTitel="Verifikationer" viewKey="bocker.verifikationer" vantandeBeslut={0} />
    );
    expect(getByRole("button", { name: "Visa eller minimera chatten" }).className).toContain(
      "min-h-[50px]"
    );
  });
});
