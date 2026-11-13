import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { KunderVy } from "@/components/skal/KunderVy";
import { artikelMeta, kronorTillOre, kundMeta, kunderStatus } from "@/lib/skal/kunder";
import { allaVyer } from "@/lib/skal/vyer";

/** Kunder och artiklar i skalet: registren fakturorna skrivs ur. */

const get = vi.fn();
const post = vi.fn();
vi.mock("@/lib/api", () => ({
  default: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) },
}));

const KUND = {
  id: "c1",
  name: "QRTECH Aktiebolag",
  org_number: "556000-0001",
  email: "faktura@qrtech.example",
  address: "Box 100",
  payment_terms_days: 30,
};
const ARTIKEL = {
  id: "a1",
  article_number: "K1",
  name: "Konsulttimme",
  unit: "h",
  unit_price: 95000,
  vat_code: "MP1",
  revenue_account: "3011",
};

function visa() {
  get.mockImplementation((url: string) =>
    Promise.resolve({ data: url === "/api/v1/customers" ? { customers: [KUND] } : { articles: [ARTIKEL] } })
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <KunderVy titel="Kunder och artiklar" variant="desktop" />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  get.mockReset();
  post.mockReset().mockResolvedValue({ data: {} });
});

describe("kartan", () => {
  it("Kunder och artiklar är en vy på Betala som chattar i Fakturerings tråd", () => {
    expect(allaVyer().find((v) => v.key === "betala.kunder")).toMatchObject({ trad: "betala.fakturering" });
  });
});

describe("texterna", () => {
  it("visar kundens villkor och artikelns pris-uppgifter", () => {
    expect(kundMeta(KUND)).toBe("556000-0001 · 30 dagar · faktura@qrtech.example");
    expect(artikelMeta(ARTIKEL)).toBe("K1 · per h · moms 25 % · 3011");
    expect(kunderStatus([KUND], [ARTIKEL], false).text).toBe("1 kund · 1 artikel");
  });

  it("läser ett pris i kronor, med komma eller punkt", () => {
    expect(kronorTillOre("950")).toBe(95000);
    expect(kronorTillOre("950,50")).toBe(95050);
    expect(kronorTillOre("9 500.5")).toBe(950050);
    expect(kronorTillOre("abc")).toBeNull();
  });
});

describe("vyn", () => {
  it("listar registren och sparar en ny kund", async () => {
    visa();
    expect(await screen.findByText("QRTECH Aktiebolag")).toBeInTheDocument();
    expect(screen.getByText("Konsulttimme")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Ny kund" }));
    fireEvent.change(screen.getByLabelText("Namn"), { target: { value: "Ny Kund AB" } });
    fireEvent.change(screen.getByLabelText("Betalningsvillkor (dagar)"), { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: "Spara kund" }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/api/v1/customers", {
        name: "Ny Kund AB",
        org_number: null,
        email: null,
        address: null,
        payment_terms_days: 20,
      })
    );
  });

  it("stoppar en artikel med ett pris som inte är ett belopp", async () => {
    visa();
    fireEvent.click(await screen.findByRole("button", { name: "Ny artikel" }));
    fireEvent.change(screen.getByLabelText("Artikelnummer"), { target: { value: "K2" } });
    fireEvent.change(screen.getByLabelText("Namn"), { target: { value: "Resa" } });
    fireEvent.change(screen.getByLabelText("Pris exkl. moms (kr)"), { target: { value: "mycket" } });
    fireEvent.click(screen.getByRole("button", { name: "Spara artikel" }));
    expect(await screen.findByText(/Priset är ett belopp/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });
});
