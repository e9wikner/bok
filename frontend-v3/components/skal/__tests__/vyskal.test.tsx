import { describe, expect, it, vi, afterEach } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { VySektion } from "@/components/skal/VySektion";
import { VyRad, VyRadSkelett, NY_MARKERING_MS } from "@/components/skal/VyRad";
import { VyInnehall } from "@/components/skal/VyInnehall";
import { atgarderVy } from "@/lib/skal/bokslut";
import { FEL_VY, INGET_AR_VY, LADDAR_VY, type VyData } from "@/lib/skal/vydata";
import { sidan } from "@/lib/skal/vyer";

const BALANS: VyData = {
  lage: "normal",
  status: "balanserar",
  period: "2026-01-01 – 2026-12-31 · utgående balans",
  sektioner: [{ titel: "Tillgångar", rader: [{ id: "1930", titel: "Företagskonto", meta: "1930", hoger: "400 720" }] }],
  fot: "",
};

afterEach(() => {
  vi.useRealTimers();
});

describe("tom sektion utgår helt (testfall 13)", () => {
  it("renderar null när radlistan är tom — inte en rubrik", () => {
    const { container } = render(
      <VySektion titel="Väntar" antalRader={0}>
        <div>rad</div>
      </VySektion>
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText("Väntar")).not.toBeInTheDocument();
  });

  it("renderar rubriken när det finns rader", () => {
    render(
      <VySektion titel="Väntar" antalRader={1}>
        <div>rad</div>
      </VySektion>
    );
    expect(screen.getByText("Väntar")).toBeInTheDocument();
  });

  it("tomt läge ger en vy utan en enda sektionsrubrik", () => {
    const vy = sidan("bokslut").vyer[1];
    render(<VyInnehall vy={vy} data={atgarderVy({ count: 0, issues: [] })} />);
    expect(screen.getByText("Åtgärder och nyckeltal")).toBeInTheDocument();
    expect(screen.queryByText("Väntar")).not.toBeInTheDocument();
  });
});

describe("laddning är skelettrader (testfall 14)", () => {
  it("visar skelett, inte en spinner över hela ytan", () => {
    const vy = sidan("bocker").vyer[0];
    const { container } = render(
      <VyInnehall vy={vy} data={BALANS} laddar />
    );
    expect(screen.getByTestId("vyrad-skelett")).toBeInTheDocument();
    expect(container.querySelector(".animate-spin")).toBeNull();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    // Raderna själva är borta medan det laddar.
    expect(screen.queryByText("Företagskonto")).not.toBeInTheDocument();
  });

  it("har samma radhöjd som en riktig rad, så listan inte hoppar", () => {
    const { container: skelett } = render(<VyRadSkelett antal={1} />);
    const { container: riktig } = render(<VyRad titel="Företagskonto" meta="1930" hoger="400 720" />);
    const klass = (el: Element | null) => el?.className ?? "";
    expect(klass(skelett.querySelector('[data-testid="vyrad-skelett"] > div'))).toContain("py-[9px]");
    expect(klass(riktig.firstElementChild)).toContain("py-[9px]");
  });
});

describe("ny-markeringen är kortvarig (testfall 15)", () => {
  it("försvinner efter sin varaktighet, men raden ligger kvar", () => {
    vi.useFakeTimers();
    const { container, rerender } = render(
      <VyRad titel="Årsredovisning 2025" hoger="PDF" variant="ny" />
    );
    expect(container.firstElementChild).toHaveAttribute("data-ny", "true");

    act(() => {
      vi.advanceTimersByTime(NY_MARKERING_MS + 10);
    });
    rerender(<VyRad titel="Årsredovisning 2025" hoger="PDF" variant="ny" />);

    expect(container.firstElementChild).not.toHaveAttribute("data-ny");
    expect(screen.getByText("Årsredovisning 2025")).toBeInTheDocument();
  });

  it("varaktigheten står på ett enda ställe", () => {
    expect(typeof NY_MARKERING_MS).toBe("number");
    expect(NY_MARKERING_MS).toBeGreaterThan(0);
  });
});

describe("lägena som inte beror på vyn", () => {
  it("laddning, fel och inget räkenskapsår har var sitt läge", () => {
    expect(LADDAR_VY.lage).toBe("pagaende");
    expect(FEL_VY.lage).toBe("fel");
    expect(INGET_AR_VY.lage).toBe("tomt");
  });
});
