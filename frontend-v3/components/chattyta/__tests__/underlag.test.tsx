import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { FilInlagg } from "@/components/chattyta/FilInlagg";
import { JamforelseRader } from "@/components/chattyta/JamforelseRader";
import { parseInlagg } from "@/lib/chattyta/parse";
import { FIXTUR_RECEIPT, FIXTUR_USER_FILE } from "@/lib/chattyta/__fixtures__/inlagg";
import type { RaInlagg, ReceiptKropp, UserFileInlagg } from "@/lib/chattyta/typer";

/**
 * FU22 (SPEC-flode-underlag.md D7, §10.4; testfall 50): `note` i `receipt`,
 * och `FilInlagg`s länk till filen.
 */

const get = vi.fn();
vi.mock("@/lib/api", () => ({ default: { get: (...a: unknown[]) => get(...a) } }));

beforeEach(() => get.mockReset());

/** §9.1:s jämförelseinlägg, ordagrant. */
const JAMFORELSE: RaInlagg = {
  ...FIXTUR_RECEIPT,
  id: "p-20",
  body: {
    title: "Kvitto Elektronikhuset 2026-06-03 mot A-118",
    labels: ["kvitto", "A-118"],
    rows: [
      { key: "Belopp", text: "inklusive moms", left_ore: 460000, right_ore: 448000 },
      { key: "Moms", text: "ingående moms", left_ore: 89600, right_ore: 89600 },
    ],
    note: "Skillnaden på 120,00 kr motsvarar raden ”Pant” på underlaget.",
    voucher_id: "a118",
  },
};

const kvitto = (raw: RaInlagg): ReceiptKropp => {
  const i = parseInlagg(raw);
  if (!i || i.type !== "receipt") throw new Error(`inte ett receipt: ${JSON.stringify(i)}`);
  return i.body;
};

describe("parseInlagg: receipt.note (D7)", () => {
  it("en sträng släpps igenom ordagrant", () => {
    expect(kvitto(JAMFORELSE).note).toBe("Skillnaden på 120,00 kr motsvarar raden ”Pant” på underlaget.");
  });

  it("utan note som förut", () => {
    expect(kvitto(FIXTUR_RECEIPT).note).toBeUndefined();
  });

  it("fel typ ger samma fallback som andra fel: okant_kontrakt", () => {
    const trasig = { ...JAMFORELSE, body: { ...(JAMFORELSE.body as object), note: 42 } };
    const i = parseInlagg(trasig);
    expect(i?.type).toBe("okant_kontrakt");
    const nullNot = parseInlagg({ ...JAMFORELSE, body: { ...(JAMFORELSE.body as object), note: null } });
    expect(nullNot?.type).toBe("okant_kontrakt");
  });
});

describe("JamforelseRader ritar note (testfall 50)", () => {
  it("i mono 12 #52525b, som consequence, under raderna", () => {
    render(<JamforelseRader kropp={kvitto(JAMFORELSE)} />);
    const not = screen.getByTestId("jamforelse-not");
    expect(not).toHaveTextContent("Skillnaden på 120,00 kr motsvarar raden ”Pant” på underlaget.");
    expect(not.className).toMatch(/bok-mono/);
    expect(not.className).toMatch(/text-\[12px\]/);
    expect(not.className).toMatch(/text-bok-text-dampad/);
    // Båda talen står kvar; noten ersätter ingenting.
    expect(screen.getAllByTestId("jamforelse-rad")).toHaveLength(2);
  });

  it("utan note: ingen not", () => {
    render(<JamforelseRader kropp={kvitto(FIXTUR_RECEIPT)} />);
    expect(screen.queryByTestId("jamforelse-not")).toBeNull();
  });
});

describe("FilInlagg öppnar filen (§10.4)", () => {
  const fil = parseInlagg(FIXTUR_USER_FILE) as UserFileInlagg;
  const oppna = vi.fn();
  const skapaUrl = vi.fn(() => "blob:kvitto");
  const aterkalla = vi.fn();
  let fonster: { location: { href: string }; close: () => void };

  beforeEach(() => {
    fonster = { location: { href: "" }, close: vi.fn() };
    oppna.mockReset();
    oppna.mockReturnValue(fonster);
    vi.stubGlobal("open", oppna);
    URL.createObjectURL = skapaUrl as unknown as typeof URL.createObjectURL;
    URL.revokeObjectURL = aterkalla as unknown as typeof URL.revokeObjectURL;
  });
  afterEach(() => vi.unstubAllGlobals());

  it("hämtar GET /intake/{id}/file som blob genom apiClient (bearer), inte med en vanlig href", async () => {
    get.mockResolvedValue({ data: new Blob(["%PDF"], { type: "application/pdf" }) });
    render(<FilInlagg inlagg={fil} />);
    const lank = screen.getByRole("button", { name: "Öppna kvitto-clas-ohlson.pdf" });
    expect(lank.closest("a")).toBeNull();

    fireEvent.click(lank);
    // Fönstret öppnas i trycket, innan hämtningen, så att det inte blockeras.
    expect(oppna).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith("/api/v1/intake/i-7/file", { responseType: "blob" });
    await waitFor(() => expect(fonster.location.href).toBe("blob:kvitto"));
  });

  it("ett fel stänger fönstret och säger det på kortet", async () => {
    get.mockRejectedValueOnce(new Error("404"));
    render(<FilInlagg inlagg={fil} />);
    fireEvent.click(screen.getByRole("button", { name: "Öppna kvitto-clas-ohlson.pdf" }));
    await waitFor(() => expect(screen.getByText("filen kunde inte öppnas")).toBeInTheDocument());
    expect(fonster.close).toHaveBeenCalled();
  });
});
