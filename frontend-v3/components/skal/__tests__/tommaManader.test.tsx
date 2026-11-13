import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { VyInnehall } from "@/components/skal/VyInnehall";
import type { VyData } from "@/lib/skal/vydata";

/** En månad utan verifikationer står kvar för låsets skull, men går att dölja. */

const rad = { id: "a1", titel: "Hyra kontor", meta: "2026-05-01", hoger: "100 kr" };

const data = (sektioner: VyData["sektioner"]): VyData =>
  ({ lage: "normal", status: "ok", period: "2026", fot: "", sektioner }) as unknown as VyData;

const MANADER = [
  { titel: "Juni 2026", rader: [], tom: "inga postade verifikationer" },
  { titel: "Maj 2026", rader: [rad], tom: "inga postade verifikationer" },
  { titel: "April 2026", rader: [], tom: "inga postade verifikationer" },
];

describe("Dölj tomma månader", () => {
  it("döljer månader utan verifikationer och visar dem igen", async () => {
    const user = userEvent.setup();
    render(<VyInnehall vy={{ titel: "Verifikationer" }} data={data(MANADER)} />);
    expect(screen.getAllByTestId("vysektion-rubrik")).toHaveLength(3);

    await user.click(screen.getByRole("button", { name: "Dölj tomma månader" }));
    const rubriker = screen.getAllByTestId("vysektion-rubrik");
    expect(rubriker).toHaveLength(1);
    expect(rubriker[0]).toHaveTextContent("Maj 2026");

    await user.click(screen.getByRole("button", { name: "Visa tomma månader (2)" }));
    expect(screen.getAllByTestId("vysektion-rubrik")).toHaveLength(3);
  });

  it("visar ingen knapp när ingen månad är tom", () => {
    render(<VyInnehall vy={{ titel: "Verifikationer" }} data={data([MANADER[1]])} />);
    expect(screen.queryByRole("button", { name: /tomma månader/ })).toBeNull();
  });

  it("fäller ihop och ut en månads verifikationer med pilknappen", async () => {
    const user = userEvent.setup();
    render(<VyInnehall vy={{ titel: "Verifikationer" }} data={data([MANADER[1]])} sok={{ varde: "", onAndra: () => {} }} />);
    expect(screen.getByText("Hyra kontor")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Dölj verifikationerna i Maj 2026" }));
    expect(screen.queryByText("Hyra kontor")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Visa verifikationerna i Maj 2026" }));
    expect(screen.getByText("Hyra kontor")).toBeInTheDocument();
  });
});
