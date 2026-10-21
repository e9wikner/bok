import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TradInlagg } from "@/components/chattyta/TradInlagg";
import { parseInlagg } from "@/lib/chattyta/parse";
import type { AgentTextInlagg, RaInlagg, UserTextInlagg } from "@/lib/chattyta/typer";
import { FIXTUR_AGENT_TEXT, FIXTUR_USER_TEXT, medKropp } from "@/lib/chattyta/__fixtures__/inlagg";

// SPEC-lasbarhet §4.4, M5: agentens text ritas som markdown (react-markdown
// + remark-gfm), utan rå HTML. Användarens inlägg förblir ren text.

function agentMed(text: string): AgentTextInlagg {
  const inlagg = parseInlagg(medKropp(FIXTUR_AGENT_TEXT, { text }) as RaInlagg);
  if (!inlagg) throw new Error("fixturen tolkades inte");
  return inlagg as AgentTextInlagg;
}

function duMed(text: string): UserTextInlagg {
  const inlagg = parseInlagg(medKropp(FIXTUR_USER_TEXT, { text }) as RaInlagg);
  if (!inlagg) throw new Error("fixturen tolkades inte");
  return inlagg as UserTextInlagg;
}

const TABELL = [
  "| Konto | Belopp |",
  "|---|---:|",
  "| 1930 | 1 250,00 |",
  "| 2440 | -1 250,00 |",
].join("\n");

describe("TradInlagg/agent — markdown (SPEC-lasbarhet §4.4, M5)", () => {
  it("en GFM-tabell blir en <table>, inte tecken", () => {
    const { container } = render(<TradInlagg inlagg={agentMed(TABELL)} />);
    const tabell = container.querySelector("table");
    expect(tabell).not.toBeNull();
    expect(tabell!.querySelectorAll("th")).toHaveLength(2);
    expect(tabell!.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(container).not.toHaveTextContent("|");
  });

  it("tabellen har full bredd, tunna linjer, mindre text och skrollar vågrätt", () => {
    const { container } = render(<TradInlagg inlagg={agentMed(TABELL)} />);
    const tabell = container.querySelector("table")!;
    expect(tabell).toHaveClass("w-full");
    expect(tabell.parentElement).toHaveClass("overflow-x-auto");
    const cell = tabell.querySelector("td")!;
    expect(cell).toHaveClass("border-bok-linje");
    expect(tabell.className).toMatch(/text-\[1[2-4]px\]/);
  });

  it("`**x**` blir <strong>", () => {
    render(<TradInlagg inlagg={agentMed("Beloppet är **1 250 kr**.")} />);
    const fet = screen.getByText("1 250 kr");
    expect(fet.tagName).toBe("STRONG");
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument();
  });

  it("punkt- och numrerade listor blir <li>", () => {
    const { container } = render(
      <TradInlagg inlagg={agentMed("Två val:\n\n- bokför nu\n- vänta\n\n1. ett\n2. två")} />
    );
    expect(container.querySelector("ul")).not.toBeNull();
    expect(container.querySelector("ol")).not.toBeNull();
    expect(container.querySelectorAll("li")).toHaveLength(4);
    expect(screen.getByText("bokför nu").tagName).toBe("LI");
  });

  it("inline-kod blir <code>", () => {
    render(<TradInlagg inlagg={agentMed("Kontot `2440` används.")} />);
    expect(screen.getByText("2440").tagName).toBe("CODE");
  });

  it("flera stycken blir flera <p> med samma stil som förut", () => {
    const { container } = render(<TradInlagg inlagg={agentMed("Första.\n\nAndra.")} />);
    const stycken = container.querySelectorAll("p");
    expect(stycken).toHaveLength(2);
    stycken.forEach((p) =>
      expect(p).toHaveClass("m-0", "max-w-[54ch]", "text-[15px]", "leading-[1.6]")
    );
  });

  it("länkar öppnas i ny flik med rel=noopener noreferrer", () => {
    render(<TradInlagg inlagg={agentMed("Se [Skatteverket](https://www.skatteverket.se).")} />);
    const lank = screen.getByRole("link", { name: "Skatteverket" });
    expect(lank).toHaveAttribute("href", "https://www.skatteverket.se");
    expect(lank).toHaveAttribute("target", "_blank");
    expect(lank).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("en javascript:-länk får ingen körbar href", () => {
    render(<TradInlagg inlagg={agentMed("[klicka](javascript:alert(1))")} />);
    const lank = screen.getByText("klicka");
    expect(lank.getAttribute("href") ?? "").not.toMatch(/javascript:/i);
  });

  it("rå HTML blir inga element — varken <script> eller annat", () => {
    const { container } = render(
      <TradInlagg
        inlagg={agentMed('Hej <script>alert("x")</script> och <b>fet</b> <img src="x" onerror="alert(1)">')}
      />
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[onerror]")).toBeNull();
  });
});

describe("TradInlagg/du — förblir ren text (SPEC-lasbarhet §4.4)", () => {
  it("markdown i användarens inlägg visas som tecken", () => {
    const { container } = render(<TradInlagg inlagg={duMed("Är det **fel** | eller?\n\n- a")} />);
    expect(container.querySelector("strong, table, li, ul, p")).toBeNull();
    expect(container).toHaveTextContent("Är det **fel** | eller?");
  });
});
