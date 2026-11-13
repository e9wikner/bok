import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SruVy } from "@/components/skal/SruVy";
import { arAnpassad, faltText, slaIhop, sruStatus } from "@/lib/skal/sru";
import { allaVyer } from "@/lib/skal/vyer";

/** SRU-kopplingen i skalet: konto → INK2R-fält, per räkenskapsår. */

const get = vi.fn();
const post = vi.fn();
const del = vi.fn();
vi.mock("@/lib/api", () => ({
  default: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
    delete: (...a: unknown[]) => del(...a),
  },
}));

const FALT = [
  { code: "7410", row: "3.1", label: "Nettoomsättning", section: "Resultat", accounts: "30-37" },
  { code: "7513", row: "3.9", label: "Övriga externa kostnader", section: "Resultat", accounts: "50-69" },
];
const KONTON = [
  { code: "3011", name: "Försäljning tjänster", account_type: "revenue", active: true },
  { code: "6110", name: "Kontorsmateriel", account_type: "expense", active: true },
];
const STANDARD = [
  { id: null, account_code: "3011", sru_field: "7410" },
  { id: null, account_code: "6110", sru_field: "7513" },
];

function svara(sparade: { id: string; account_code: string; sru_field: string }[]) {
  get.mockImplementation((url: string) => {
    if (url === "/api/v1/sru-fields") return Promise.resolve({ data: FALT });
    if (url === "/api/v1/accounts") return Promise.resolve({ data: { accounts: KONTON } });
    if (url === "/api/v1/accounts/with-transactions") return Promise.resolve({ data: { codes: ["6110"] } });
    if (url.endsWith("/sru-mappings/default")) return Promise.resolve({ data: STANDARD });
    if (url.endsWith("/sru-mappings")) return Promise.resolve({ data: sparade });
    return Promise.reject(new Error(url));
  });
}

const ALLA = /Visa alla konton/;

function visa(arId: string | null = "fy-2025") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SruVy titel="SRU-koppling" arId={arId} variant="desktop" />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  get.mockReset();
  post.mockReset().mockResolvedValue({ data: {} });
  del.mockReset().mockResolvedValue({ data: null });
});

describe("kartan", () => {
  it("SRU-kopplingen är en vy i Bokslut som chattar i Översiktens tråd", () => {
    const vy = allaVyer().find((v) => v.key === "bokslut.sru");
    expect(vy).toMatchObject({ sida: "bokslut", slug: "sru", trad: "bokslut.rapporter" });
  });
});

describe("kopplingarna", () => {
  it("låter årets sparade gå före standarden, och bara en avvikande räknas som anpassad", () => {
    const k = slaIhop(STANDARD, [
      { id: "m1", account_code: "6110", sru_field: "7410" },
      { id: "m2", account_code: "3011", sru_field: "7410" },
    ]);
    expect(k["6110"]).toEqual({ sparad: { id: "m1", falt: "7410" }, standard: "7513", galler: "7410" });
    expect(arAnpassad(k["6110"])).toBe(true);
    expect(arAnpassad(k["3011"])).toBe(false);
    expect(sruStatus({ falt: FALT, kopplingar: k }, false, "fy")).toEqual({ text: "1 anpassad", lage: "normal" });
    expect(sruStatus(undefined, false, null).text).toBe("inget räkenskapsår");
  });

  it("skriver fältet med sin rad och sitt namn", () => {
    expect(faltText(FALT, "7410")).toBe("3.1 Nettoomsättning");
    expect(faltText(FALT, null)).toBe("ingen koppling");
  });
});

describe("vyn", () => {
  it("sparar ett nytt fält för året och tar bort det för att gå tillbaka till standarden", async () => {
    svara([{ id: "m1", account_code: "6110", sru_field: "7410" }]);
    visa();

    fireEvent.click(await screen.findByLabelText(ALLA));
    expect(await screen.findByText("3.1 Nettoomsättning · anpassad")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Försäljning tjänster"));
    fireEvent.change(screen.getByLabelText("SRU-fält för 3011"), { target: { value: "7513" } });
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/api/v1/fiscal-years/fy-2025/sru-mappings", {
        account_code: "3011",
        sru_field: "7513",
      })
    );

    fireEvent.click(screen.getByText("Kontorsmateriel"));
    fireEvent.change(screen.getByLabelText("SRU-fält för 6110"), { target: { value: "" } });
    await waitFor(() => expect(del).toHaveBeenCalledWith("/api/v1/fiscal-years/fy-2025/sru-mappings/m1"));
  });

  it("visar bara de anpassade när rutan är ikryssad", async () => {
    svara([{ id: "m1", account_code: "6110", sru_field: "7410" }]);
    visa();
    fireEvent.click(await screen.findByLabelText(ALLA));
    await waitFor(() => expect(screen.getAllByTestId("sru-konto")).toHaveLength(2));
    fireEvent.click(screen.getByLabelText("Bara anpassade"));
    expect(screen.getAllByTestId("sru-konto")).toHaveLength(1);
    expect(screen.getByText("Kontorsmateriel")).toBeInTheDocument();
  });

  it("visar som standard bara konton med transaktioner under året, och alla på begäran", async () => {
    svara([]);
    visa();
    await waitFor(() => expect(screen.getAllByTestId("sru-konto")).toHaveLength(1));
    expect(screen.getByText("Kontorsmateriel")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/api/v1/accounts/with-transactions", { params: { fiscal_year_id: "fy-2025" } });

    fireEvent.click(screen.getByLabelText(ALLA));
    await waitFor(() => expect(screen.getAllByTestId("sru-konto")).toHaveLength(2));

    fireEvent.click(screen.getByLabelText(ALLA));
    await waitFor(() => expect(screen.getAllByTestId("sru-konto")).toHaveLength(1));
  });

  it("frågar innan årets kopplingar återställs", async () => {
    svara([]);
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    visa();
    const knapp = await screen.findByRole("button", { name: "Återställ standard" });
    fireEvent.click(knapp);
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(knapp);
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/fiscal-years/fy-2025/sru-mappings/reset-default"));
    confirm.mockRestore();
  });

  it("säger till när det inte finns något räkenskapsår", () => {
    visa(null);
    expect(screen.getByText("Det finns inget räkenskapsår att koppla.")).toBeInTheDocument();
  });
});
