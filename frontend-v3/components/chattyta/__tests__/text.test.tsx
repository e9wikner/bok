import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { FilInlagg, filMeta } from "@/components/chattyta/FilInlagg";
import { SkriverIndikator } from "@/components/chattyta/SkriverIndikator";
import { TradInlagg, klockslag } from "@/components/chattyta/TradInlagg";
import { SKRIVER_ETIKETTER, skriverText } from "@/lib/chattyta/etiketter";
import { parseInlagg } from "@/lib/chattyta/parse";
import type {
  AgentTextInlagg,
  Inlagg,
  UserFileInlagg,
  UserTextInlagg,
} from "@/lib/chattyta/typer";
import {
  FIXTUR_AGENT_TEXT,
  FIXTUR_USER_FILE,
  FIXTUR_USER_TEXT,
  kropp,
  medKropp,
} from "@/lib/chattyta/__fixtures__/inlagg";
import type { RaInlagg } from "@/lib/chattyta/typer";

// Renderarna tar bara det `parseInlagg` släppt igenom (SPEC §4.1) — testerna
// går därför samma väg i stället för att bygga typade inlägg för hand.
function typad<T extends Inlagg>(raw: RaInlagg): T {
  const inlagg = parseInlagg(raw);
  if (!inlagg) throw new Error(`fixturen ${raw.id} tolkades inte`);
  return inlagg as T;
}

const agent = () => typad<AgentTextInlagg>(FIXTUR_AGENT_TEXT);
const du = () => typad<UserTextInlagg>(FIXTUR_USER_TEXT);
const fil = () => typad<UserFileInlagg>(FIXTUR_USER_FILE);

// ─── TradInlagg/agent ─────────────────────────────────────────────────────

describe("TradInlagg/agent (komponenter.md, SPEC §5)", () => {
  it("metaraden är `agenten · HH:MM` i lokal tid", () => {
    // Utan tidszon tolkas ISO-strängen som lokal tid (ECMAScript), så
    // testet håller oavsett maskinens TZ.
    const inlagg = typad<AgentTextInlagg>({ ...FIXTUR_AGENT_TEXT, created_at: "2026-09-18T06:41:00" });
    render(<TradInlagg inlagg={inlagg} />);
    expect(screen.getByText("agenten · 06:41")).toBeInTheDocument();
  });

  it("klockslaget räknas om från serverns UTC till lokal tid", () => {
    const d = new Date("2026-09-18T06:41:00+00:00");
    const forvantat = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    expect(klockslag("2026-09-18T06:41:00+00:00")).toBe(forvantat);
  });

  it("ett oläsbart `created_at` ger bara `agenten`, aldrig `NaN:NaN`", () => {
    const inlagg = { ...agent(), created_at: "inte ett datum" };
    render(<TradInlagg inlagg={inlagg} />);
    expect(screen.getByText("agenten")).toBeInTheDocument();
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });

  it("metaraden är mono 11 versal etikett i metagrått; kolumnen har gap 13", () => {
    const { container } = render(<TradInlagg inlagg={agent()} />);
    const kolumn = container.firstElementChild!;
    expect(kolumn).toHaveClass("flex", "flex-col", "gap-[13px]");
    const meta = screen.getByText(/^agenten/);
    // bok-etikett = mono, letter-spacing 0.08em, versalt (globals.css).
    expect(meta).toHaveClass("bok-etikett", "text-[11px]", "text-bok-meta");
  });

  it("texten är 15/1.6, max 54ch, text-wrap pretty — ordagrant ur kroppen", () => {
    render(<TradInlagg inlagg={agent()} />);
    const text = screen.getByText(String(kropp(FIXTUR_AGENT_TEXT).text));
    expect(text).toHaveClass("text-[15px]", "leading-[1.6]", "max-w-[54ch]", "[text-wrap:pretty]");
  });

  it("`traces[]` ritas inte — inga spår-chip (SPEC-lasbarhet M4)", () => {
    // Fixturen bär två spår; servern skickar dem, klienten visar dem inte.
    expect(agent().traces).toHaveLength(2);
    const { container } = render(<TradInlagg inlagg={agent()} />);
    expect(screen.queryByTestId("sparchip")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sparchip-rad")).not.toBeInTheDocument();
    expect(container).not.toHaveTextContent("bankhändelser lästa");
    expect(container).not.toHaveTextContent("verifikation postad");
  });

  it("en radlista (C9) ritas under texten när den skickas in", () => {
    render(<TradInlagg inlagg={agent()} radLista={<div data-testid="radlista" />} />);
    const text = screen.getByText(String(kropp(FIXTUR_AGENT_TEXT).text));
    const radlista = screen.getByTestId("radlista");
    expect(text.compareDocumentPosition(radlista) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

// ─── TradInlagg/du ────────────────────────────────────────────────────────

describe("TradInlagg/du (komponenter.md)", () => {
  it("högerställd bubbla: max 74 %, #eef0f3, radius 14 14 4 14, padding 12/16, 15/1.55", () => {
    const { container } = render(<TradInlagg inlagg={du()} />);
    expect(container.firstElementChild).toHaveClass("flex", "justify-end");
    const bubbla = screen.getByText("Vad består kundfordringarna av?");
    expect(bubbla).toHaveClass(
      "max-w-[74%]",
      "bg-bok-bubbla",
      "rounded-[14px_14px_4px_14px]",
      "px-4",
      "py-3",
      "text-[15px]",
      "leading-[1.55]"
    );
  });

  it("har ingen metarad och inga spår", () => {
    render(<TradInlagg inlagg={du()} />);
    expect(screen.queryByText(/agenten/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("sparchip")).not.toBeInTheDocument();
  });
});

// ─── FilInlagg ────────────────────────────────────────────────────────────

describe("FilInlagg (komponenter.md, SPEC §5)", () => {
  it("visar filnamnet och `218 kB · 1 sida`", () => {
    render(<FilInlagg inlagg={fil()} />);
    expect(screen.getByText("kvitto-clas-ohlson.pdf")).toBeInTheDocument();
    expect(screen.getByText("218 kB · 1 sida")).toBeInTheDocument();
  });

  it.each([
    [218000, 1, "218 kB · 1 sida"],
    [218000, 3, "218 kB · 3 sidor"],
    [218000, null, "218 kB"],
    [512, null, "512 B"],
    [1_250_000, 2, "1,3 MB · 2 sidor"],
    [999_600, null, "1 MB"],
  ])("filMeta(%s, %s) = %s", (bytes, sidor, forvantat) => {
    expect(filMeta(bytes, sidor)).toBe(forvantat);
  });

  it("högerställd kolumn med gap 8; filkortet #eef0f3, radius 14, padding 12/16", () => {
    const { container } = render(<FilInlagg inlagg={fil()} />);
    expect(container.firstElementChild).toHaveClass("flex", "flex-col", "items-end", "gap-2");
    const kort = screen.getByTestId("filkort");
    expect(kort).toHaveClass("bg-bok-bubbla", "rounded-[14px]", "px-4", "py-3");
  });

  it("sidikonen är 30×38, kant #c7c7cc, radius 4, vit — och dold för skärmläsare", () => {
    render(<FilInlagg inlagg={fil()} />);
    const ikon = screen.getByTestId("sidikon");
    expect(ikon).toHaveClass(
      "h-[38px]",
      "w-[30px]",
      "border",
      "border-bok-kant-streckad",
      "rounded",
      "bg-bok-yta"
    );
    expect(ikon).toHaveAttribute("aria-hidden", "true");
  });

  it("filnamn 14, filmeta mono 11 #6b7280", () => {
    render(<FilInlagg inlagg={fil()} />);
    expect(screen.getByText("kvitto-clas-ohlson.pdf")).toHaveClass("text-[14px]");
    expect(screen.getByText("218 kB · 1 sida")).toHaveClass("bok-mono", "text-[11px]", "text-bok-text-svag");
  });

  it("ingen förhandsvisning: inget img, ingen iframe, ingen länk", () => {
    const { container } = render(<FilInlagg inlagg={fil()} />);
    expect(container.querySelector("img, iframe, object, embed, a")).toBeNull();
  });

  it("ett PDF utan sidantal visar bara storleken", () => {
    const utanSidor = typad<UserFileInlagg>(medKropp(FIXTUR_USER_FILE, { ...kropp(FIXTUR_USER_FILE), pages: null }));
    render(<FilInlagg inlagg={utanSidor} />);
    expect(screen.getByText("218 kB")).toBeInTheDocument();
  });
});

// ─── SkriverIndikator ─────────────────────────────────────────────────────

describe("SkriverIndikator — delta {activity} (testfall 11)", () => {
  it("utan activity än säger den `Läser…` (testfall 11)", () => {
    render(<SkriverIndikator />);
    expect(screen.getByTestId("skriver-text")).toHaveTextContent(/^Läser…$/);
  });

  it("byter text när en ny activity kommer (testfall 11)", () => {
    const { rerender } = render(<SkriverIndikator activity="las_bankhandelser" />);
    expect(screen.getByTestId("skriver-text")).toHaveTextContent(/^Läser bankhändelser…$/);
    rerender(<SkriverIndikator activity="posta_verifikation" />);
    expect(screen.getByTestId("skriver-text")).toHaveTextContent(/^Postar verifikation…$/);
  });

  it("säger vad som görs, aldrig vad som är gjort — `activity` sänds när verktyget ANROPAS", () => {
    // En indikator som säger `verifikation postad` medan postningen pågår
    // påstår något om huvudboken som inte har hänt än.
    for (const verktyg of Object.keys(SKRIVER_ETIKETTER)) {
      render(<SkriverIndikator activity={verktyg} />);
      const text = screen.getByTestId("skriver-text").textContent ?? "";
      expect(text).toBe(SKRIVER_ETIKETTER[verktyg]);
      expect(text).not.toMatch(/(läst|lästa|hämtad|postad|registrerat)$/);
      expect(text.endsWith("…")).toBe(true);
      cleanup();
    }
  });

  it.each([undefined, null, "", "   "])(
    "aldrig tom — activity %j ger `Läser…` (testfall 11)",
    (activity) => {
      render(<SkriverIndikator activity={activity} />);
      expect(screen.getByTestId("skriver-text")).toHaveTextContent(/^Läser…$/);
    }
  );

  it("ett okänt verktyg visas med sitt namn, som `build_trace` gör (testfall 11)", () => {
    render(<SkriverIndikator activity="nytt_verktyg" />);
    expect(screen.getByTestId("skriver-text")).toHaveTextContent("nytt_verktyg");
  });

  it("metarad `agenten` ovanför, som agentinlägget", () => {
    render(<SkriverIndikator />);
    expect(screen.getByText("agenten")).toHaveClass("bok-etikett", "text-[11px]", "text-bok-meta");
  });

  it("tre prickar 5×5 i #a1a1aa, #c4c4c8, #e0e0e4 med gap 4, dolda för skärmläsare", () => {
    render(<SkriverIndikator />);
    const prickar = screen.getByTestId("skriver-prickar");
    expect(prickar).toHaveClass("flex", "gap-1");
    expect(prickar).toHaveAttribute("aria-hidden", "true");
    const barn = Array.from(prickar.children) as HTMLElement[];
    expect(barn).toHaveLength(3);
    barn.forEach((p) => expect(p).toHaveClass("h-[5px]", "w-[5px]", "rounded-full"));
    expect(barn.map((p) => p.style.background)).toEqual([
      "rgb(161, 161, 170)",
      "rgb(196, 196, 200)",
      "rgb(224, 224, 228)",
    ]);
  });

  it("texten är 15 #52525b", () => {
    render(<SkriverIndikator />);
    expect(screen.getByTestId("skriver-text")).toHaveClass("text-[15px]", "text-bok-text-dampad");
  });
});

// ─── Varje verktyg har en presensetikett ─────────────────────────────────

/**
 * Verktygsnamnen ur `services/agent_tools.py::_TOOL_SPECS`, lästa ur källan
 * (som `parse.test.ts` läser specen). Varje post i tabellen börjar med
 * namnet på en egen rad, indraget åtta steg.
 */
function serverVerktyg(): string[] {
  const kalla = readFileSync(path.resolve(__dirname, "../../../../services/agent_tools.py"), "utf8");
  const start = kalla.indexOf("_TOOL_SPECS:");
  const slut = kalla.indexOf("\n)\n", start);
  expect(start).toBeGreaterThan(-1);
  expect(slut).toBeGreaterThan(start);
  return Array.from(kalla.slice(start, slut).matchAll(/^ {8}"([a-z_]+)",$/gm), (m) => m[1]);
}

describe("varje agentverktyg har en presensetikett (SPEC-lasbarhet §4.3)", () => {
  it("SKRIVER_ETIKETTER täcker exakt verktygen i agent_tools.py", () => {
    const verktyg = serverVerktyg();
    // Ett trasigt mönster ska inte ge ett tomt, trivialt grönt test.
    expect(verktyg).toEqual(
      expect.arrayContaining(["las_kontoplan", "posta_verifikation", "be_om_beslut", "koppla_underlag"])
    );
    expect(Object.keys(SKRIVER_ETIKETTER).sort()).toEqual([...verktyg].sort());
  });

  it("de fyra som saknades har sina etiketter", () => {
    expect(skriverText("tolka_underlag")).toBe("Tolkar underlaget…");
    expect(skriverText("be_om_beslut")).toBe("Lägger fram ett beslut…");
    expect(skriverText("koppla_underlag")).toBe("Kopplar underlaget…");
    expect(skriverText("foresla_verifikation")).toBe("Föreslår en verifikation…");
  });

  it("skriverText är aldrig tom", () => {
    for (const a of [undefined, null, "", " ", "las_kontoplan", "okänt"]) {
      expect(skriverText(a).trim()).not.toBe("");
    }
  });
});
