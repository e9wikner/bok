import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ForetagetVy } from "@/components/skal/ForetagetVy";
import type { CompanyInfo } from "@/lib/api";
import { foretagetStatus, formularFel, formularFran, saknasForFaktura, tillServer } from "@/lib/skal/foretaget";
import { allaVyer } from "@/lib/skal/vyer";

/** Företagets uppgifter i skalet: det fakturan och årsredovisningen behöver. */

const get = vi.fn();
const put = vi.fn();
vi.mock("@/lib/api", () => ({
  default: { get: (...a: unknown[]) => get(...a), put: (...a: unknown[]) => put(...a) },
}));

const KOMPLETT: CompanyInfo = {
  name: "Exempel AB",
  org_number: "556677-8899",
  address: "Storgatan 1",
  postnr: "111 22",
  postort: "Stockholm",
  seat: "Stockholm",
  vat_number: "SE556677889901",
  bankgiro: "123-4567",
  plusgiro: null,
  f_skatt: true,
};

function visa() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ForetagetVy titel="Företaget" variant="desktop" />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  get.mockReset();
  put.mockReset();
});

describe("kartan", () => {
  it("Företaget är en vy under Inställningar som chattar i Fakturerings tråd", () => {
    const vy = allaVyer().find((v) => v.key === "installningar.foretaget");
    expect(vy).toMatchObject({ sida: "installningar", slug: "foretaget", trad: "betala.fakturering" });
  });
});

describe("reglerna", () => {
  it("säger vad en faktura saknar, med serverns krav på momsnumret", () => {
    expect(saknasForFaktura(KOMPLETT)).toEqual([]);
    expect(saknasForFaktura({ ...KOMPLETT, seat: null, bankgiro: null, vat_number: "SE123" })).toEqual([
      "säte",
      "momsregistreringsnummer",
      "bankgiro eller plusgiro",
    ]);
    expect(foretagetStatus(KOMPLETT, false)).toEqual({ text: "klart för fakturor", lage: "klart" });
    expect(foretagetStatus({ ...KOMPLETT, seat: null }, false)).toEqual({
      text: "1 uppgift saknas för fakturor",
      lage: "vantar",
    });
  });

  it("skickar ett tomt fält som null och momsnumret utan mellanslag", () => {
    const f = { ...formularFran(KOMPLETT), postnr: "  ", vat_number: "se 5566778899 01" };
    const ut = tillServer(f);
    expect(ut.postnr).toBeNull();
    expect(ut.vat_number).toBe("SE556677889901");
    expect(ut.name).toBe("Exempel AB");
  });

  it("stoppar ett tomt namn och ett felformat momsnummer före servern", () => {
    expect(formularFel({ ...formularFran(KOMPLETT), name: " " })).toMatch(/Företagsnamnet/);
    expect(formularFel({ ...formularFran(KOMPLETT), vat_number: "SE12" })).toMatch(/Momsregistreringsnumret/);
    expect(formularFel(formularFran(KOMPLETT))).toBeNull();
  });
});

describe("vyn", () => {
  it("visar vad som saknas och sparar en ändring med PUT", async () => {
    get.mockResolvedValue({ data: { ...KOMPLETT, seat: null } });
    put.mockImplementation((_url: string, body: CompanyInfo) => Promise.resolve({ data: body }));
    visa();

    expect(await screen.findByText(/För att utfärda en faktura saknas: säte/)).toBeInTheDocument();
    const spara = screen.getByRole("button", { name: "Spara" });
    expect(spara).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Säte/), { target: { value: "Uppsala" } });
    expect(spara).toBeEnabled();
    fireEvent.click(spara);

    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put.mock.calls[0][0]).toBe("/api/v1/company-info");
    expect(put.mock.calls[0][1]).toMatchObject({ seat: "Uppsala", f_skatt: true, plusgiro: null });
    expect(await screen.findByText("sparat")).toBeInTheDocument();
    expect(screen.queryByText(/För att utfärda en faktura saknas/)).not.toBeInTheDocument();
  });

  it("visar serverns nej och står kvar med det inskrivna", async () => {
    get.mockResolvedValue({ data: KOMPLETT });
    put.mockRejectedValue({ response: { data: { detail: "Ogiltigt organisationsnummer" } } });
    visa();

    fireEvent.change(await screen.findByLabelText("Organisationsnummer"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Spara" }));
    expect(await screen.findByText("Ogiltigt organisationsnummer")).toBeInTheDocument();
    expect(screen.getByLabelText("Organisationsnummer")).toHaveValue("1");
  });
});
