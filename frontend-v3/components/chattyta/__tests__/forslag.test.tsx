import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { VerifikationsForslag } from "@/components/chattyta/VerifikationsForslag";
import { parseInlagg } from "@/lib/chattyta/parse";
import { FIXTUR_DRAFT } from "@/lib/chattyta/__fixtures__/inlagg";
import type { DraftInlagg } from "@/lib/chattyta/typer";

/**
 * `VerifikationsForslag` utan knapp (C10). Fixturen går genom
 * `parseInlagg` så att testet läser samma form som tråden får — inte en
 * handbyggd kopia som kan glida isär från kontraktet i SPEC §4.3.
 */
function draft(): DraftInlagg {
  const inlagg = parseInlagg(FIXTUR_DRAFT);
  if (!inlagg || inlagg.type !== "draft") {
    throw new Error("FIXTUR_DRAFT parsas inte till draft");
  }
  return inlagg;
}

function rader(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>('[data-testid="konteringsrad"]'));
}

describe("VerifikationsForslag (testfall 24)", () => {
  it("visar rubrik och serverns metasträng ordagrant (testfall 24)", () => {
    render(<VerifikationsForslag inlagg={draft()} />);
    expect(screen.getByText("Kontorsmaterial, Clas Ohlson")).toBeInTheDocument();
    expect(screen.getByText("A · 2026-09-18")).toBeInTheDocument();
  });

  it("har kolumnrubrikerna Konto / Debet / Kredit, de högra två 92 px högerställda (testfall 24)", () => {
    render(<VerifikationsForslag inlagg={draft()} />);
    const konto = screen.getByText("Konto");
    const debet = screen.getByText("Debet");
    const kredit = screen.getByText("Kredit");
    for (const el of [konto, debet, kredit]) {
      expect(el.className).toContain("uppercase");
      expect(el.className).toContain("text-[10px]");
      expect(el.className).toContain("bok-mono");
    }
    for (const el of [debet, kredit]) {
      expect(el.className).toContain("w-[92px]");
      expect(el.className).toContain("text-right");
    }
  });

  it("visar konto, namn, debet och kredit per rad, i serverns ordning (testfall 24)", () => {
    const { container } = render(<VerifikationsForslag inlagg={draft()} />);
    const r = rader(container);
    expect(r).toHaveLength(3);

    const forvantat = [
      { konto: "6110", namn: "Kontorsmateriel", debet: "716,80", kredit: "" },
      { konto: "2640", namn: "Ingående moms", debet: "179,20", kredit: "" },
      { konto: "1930", namn: "Företagskonto", debet: "", kredit: "896,00" },
    ];
    forvantat.forEach((f, i) => {
      const rad = within(r[i]);
      expect(rad.getByText(f.konto)).toBeInTheDocument();
      expect(rad.getByText(f.namn)).toBeInTheDocument();
      const debetCell = r[i].querySelector('[data-kolumn="debet"]');
      const kreditCell = r[i].querySelector('[data-kolumn="kredit"]');
      // Mellanslaget i "896,00" kan vara ett hårt blanksteg ur Intl; jämför utan.
      const norm = (s: string | null | undefined) => (s ?? "").replace(/\s/g, " ");
      expect(norm(debetCell?.textContent)).toBe(f.debet);
      expect(norm(kreditCell?.textContent)).toBe(f.kredit);
    });
  });

  it("formaterar öre, räknar inte: inga summarader läggs till (testfall 24)", () => {
    const { container } = render(<VerifikationsForslag inlagg={draft()} />);
    // Klienten summerar inte debet/kredit (antagande 3). Bara serverns rader.
    expect(rader(container)).toHaveLength(3);
    expect(screen.queryByText(/^Summa/)).not.toBeInTheDocument();
  });

  it("visar fotnoten ordagrant, och utelämnar den när den är null (testfall 24)", () => {
    render(<VerifikationsForslag inlagg={draft()} />);
    expect(
      screen.getByText("Underlag: kvitto 2026-09-18 · kompletteringsflagga sätts inte")
    ).toBeInTheDocument();

    const utanFot = draft();
    utanFot.body = { ...utanFot.body, footnote: null };
    const { container } = render(<VerifikationsForslag inlagg={utanFot} />);
    expect(container.querySelector('[data-testid="forslag-fot"]')).toBeNull();
  });

  it("konsekvensnotisen är mono 12 i #52525b, inte metagrå #9ca3af (testfall 24)", () => {
    render(<VerifikationsForslag inlagg={draft()} />);
    const notis = screen.getByText(
      "Låses vid postning · period september öppen till 2026-10-12"
    );
    expect(notis.className).toContain("bok-mono");
    expect(notis.className).toContain("text-[12px]");
    // `--bok-text-dampad` är #52525b (globals.css).
    expect(notis.className).toContain("text-bok-text-dampad");
    // Notisen är inte metatext (komponenter.md). Metaklassen på den är ett fel.
    expect(notis.className).not.toMatch(/\btext-bok-meta\b/);
    expect(notis.className).not.toContain("9ca3af");
    expect(notis.getAttribute("style") ?? "").not.toMatch(/bok-meta|9ca3af/);
  });

  it("renderar inga knappar utan slot — C12 fyller knappraden (testfall 24)", () => {
    render(<VerifikationsForslag inlagg={draft()} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    // Notisen står kvar även utan knappar: varningen är inte knappens.
    expect(
      screen.getByText("Låses vid postning · period september öppen till 2026-10-12")
    ).toBeInTheDocument();
  });

  it("knappraden är en slot: det som skickas in hamnar bredvid notisen (testfall 24)", () => {
    render(
      <VerifikationsForslag
        inlagg={draft()}
        knappar={<button type="button">Posta</button>}
      />
    );
    const knapprad = screen.getByTestId("forslag-knapprad");
    expect(within(knapprad).getByRole("button", { name: "Posta" })).toBeInTheDocument();
    expect(
      within(knapprad).getByText("Låses vid postning · period september öppen till 2026-10-12")
    ).toBeInTheDocument();
  });

  it("kortet bär designens ram: vit yta, kant #d4d4d8, radius 12, max-bredd 560 (testfall 24)", () => {
    const { container } = render(<VerifikationsForslag inlagg={draft()} />);
    const kort = container.firstElementChild as HTMLElement;
    expect(kort.className).toContain("bg-bok-yta");
    expect(kort.className).toContain("border-bok-kant");
    expect(kort.className).toContain("rounded-[12px]");
    expect(kort.className).toContain("max-w-[560px]");
  });
});
