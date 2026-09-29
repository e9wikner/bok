import { describe, expect, it } from "vitest";

import { describeInvoiceError, formatQuantity, normaliseQuantity } from "@/lib/fakturering";

const fel = (detail: unknown) => ({ response: { data: { detail } } });

describe("fakturering F0 i de gamla sidorna", () => {
  it("skriver decimalt antal med komma eller punkt för backenden", () => {
    expect(normaliseQuantity("7,5")).toBe("7.5");
    expect(normaliseQuantity(" 7.25 ")).toBe("7.25");
    expect(normaliseQuantity(3)).toBe("3");
    expect(formatQuantity(7.5)).toBe("7,5");
  });

  it("company_info_incomplete räknar upp det som saknas", () => {
    const text = describeInvoiceError(
      fel({ code: "company_info_incomplete", missing: ["vat_number", "seat", "bankgiro_or_plusgiro"] }),
      "x",
    );
    expect(text).toContain("momsregistreringsnummer");
    expect(text).toContain("säte");
    expect(text).toContain("bankgiro eller plusgiro");
  });

  it("number_taken, period_locked och human_only blir begripliga", () => {
    expect(describeInvoiceError(fel({ code: "number_taken", invoice_number: "2026-1" }), "x")).toContain(
      "2026-1 är redan använt",
    );
    expect(describeInvoiceError(fel({ code: "period_locked", locked_by: "stefan" }), "x")).toContain(
      "låst (av stefan)",
    );
    expect(describeInvoiceError(fel({ code: "human_only" }), "x")).toContain("inloggad");
  });

  it("okänd kod ger serverns text, inget svar ger reservtexten", () => {
    expect(describeInvoiceError(fel({ code: "okand", error: "Något" }), "x")).toBe("Något");
    expect(describeInvoiceError(new Error("nät"), "Reserv")).toBe("Reserv");
  });
});
