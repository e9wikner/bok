import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { VyInnehall } from "@/components/skal/VyInnehall";
import type { VyData } from "@/lib/skal/vydata";

/** En månad utan verifikationer visas inte. */

const rad = { id: "a1", titel: "Hyra kontor", meta: "2026-05-01", hoger: "100 kr" };

const data = (sektioner: VyData["sektioner"]): VyData =>
  ({ lage: "normal", status: "ok", period: "2026", fot: "", sektioner }) as unknown as VyData;

describe("Tomma månader", () => {
  it("visar bara månader med verifikationer", () => {
    render(
      <VyInnehall
        vy={{ titel: "Verifikationer" }}
        data={data([
          { titel: "Juni 2026", rader: [], tom: "inga postade verifikationer" },
          { titel: "Maj 2026", rader: [rad], tom: "inga postade verifikationer" },
          { titel: "April 2026", rader: [], tom: "inga postade verifikationer" },
        ])}
      />
    );
    const rubriker = screen.getAllByTestId("vysektion-rubrik");
    expect(rubriker).toHaveLength(1);
    expect(rubriker[0]).toHaveTextContent("Maj 2026");
    expect(screen.queryByRole("button", { name: /tomma månader/ })).toBeNull();
  });
});
