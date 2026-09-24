import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { VyRad } from "@/components/skal/VyRad";
import { aldersTon, ROD_FRAN_DAGAR } from "@/lib/chattyta/alder";

// ─── Testfall 22: tröskeln ────────────────────────────────────────────────

describe("aldersTon — age_days-tröskeln (testfall 22)", () => {
  it("aldersTon(6) är vantar, (7) och (30) är forfallen (testfall 22)", () => {
    expect(aldersTon(6)).toBe("vantar");
    expect(aldersTon(7)).toBe("forfallen");
    expect(aldersTon(30)).toBe("forfallen");
  });

  it("tröskeln är sju dagar, samma dag som påminnelsen (SPEC-chattyta.md §12.2)", () => {
    expect(ROD_FRAN_DAGAR).toBe(7);
    expect(aldersTon(ROD_FRAN_DAGAR - 1)).toBe("vantar");
    expect(aldersTon(ROD_FRAN_DAGAR)).toBe("forfallen");
  });

  it("ett beslut från i dag väntar", () => {
    expect(aldersTon(0)).toBe("vantar");
  });
});

// ─── Testfall 22: VyRad färgas med regeln ─────────────────────────────────

const metaFarg = (text: string) => screen.getByText(text).style.color;

describe("VyRad saknar/vantar färgas med aldersTon (testfall 22)", () => {
  it.each(["saknar", "vantar"] as const)(
    "%s med ageDays 6 har väntar-tonen (testfall 22)",
    (variant) => {
      render(<VyRad titel="Rad" meta="6 dagar" hoger="1" variant={variant} ageDays={6} />);
      expect(metaFarg("6 dagar")).toBe("var(--bok-vantar-meta)");
    }
  );

  it.each(["saknar", "vantar"] as const)(
    "%s med ageDays 7 och 30 har fel-tonen (testfall 22)",
    (variant) => {
      render(
        <>
          <VyRad titel="Rad" meta="7 dagar" hoger="1" variant={variant} ageDays={7} />
          <VyRad titel="Rad" meta="30 dagar" hoger="1" variant={variant} ageDays={30} />
        </>
      );
      expect(metaFarg("7 dagar")).toBe("var(--bok-fel-meta)");
      expect(metaFarg("30 dagar")).toBe("var(--bok-fel-meta)");
    }
  );

  it.each(["saknar", "vantar"] as const)("%s utan ageDays är oförändrad", (variant) => {
    render(<VyRad titel="Rad" meta="okänd ålder" hoger="1" variant={variant} />);
    expect(metaFarg("okänd ålder")).toBe("var(--bok-vantar-meta)");
  });

  it("andra varianter struntar i ageDays — regeln gäller bara saknar och vantar (§10)", () => {
    render(
      <>
        <VyRad titel="Rad" meta="normal" hoger="1" ageDays={30} />
        <VyRad titel="Rad" meta="påverkad" hoger="1" variant="paverkad" ageDays={30} />
      </>
    );
    expect(metaFarg("normal")).toBe("var(--bok-meta)");
    expect(metaFarg("påverkad")).toBe("var(--bok-vantar-meta)");
  });
});
