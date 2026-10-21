import { beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { VyInnehall } from "@/components/skal/VyInnehall";
import { useVyer } from "@/hooks/useVyer";
import { sidan } from "@/lib/skal/vyer";

/**
 * Sökrutan i Verifikationer: listan filtreras för varje tangent, bästa
 * träffen överst, och sökningen når årets alla postade — inte bara de
 * sidor som hunnit skrollas fram.
 */

const get = vi.fn();
vi.mock("@/lib/api", () => ({ default: { get: (...a: unknown[]) => get(...a) } }));

const AR = { id: "fy", label: "2026", start: "2026-01-01", end: "2026-12-31" };

const verifikation = (n: number, description: string) => ({
  id: `a${n}`,
  series: "A",
  number: n,
  date: "2026-05-01",
  description,
  status: "posted",
  total_debit: 100 * n,
  missing_attachment: false,
  age_days: 0,
});

/** 60 postade, senast först; Telia ligger på andra sidan. */
const POSTADE = [
  verifikation(60, "Hyra kontor"),
  ...Array.from({ length: 58 }, (_, i) => verifikation(59 - i, `Inköp ${59 - i}`)),
  verifikation(1, "Telia mobil"),
];

function svaraGet(url: string, config?: { params?: Record<string, unknown> }) {
  const p = config?.params ?? {};
  if (url === "/api/v1/vouchers") {
    if (p.status === "draft" || p.missing_attachment === true) {
      return Promise.resolve({ data: { total: 0, vouchers: [] } });
    }
    const offset = Number(p.offset ?? 0);
    const limit = p.limit === undefined ? POSTADE.length : Number(p.limit);
    return Promise.resolve({ data: { total: POSTADE.length, vouchers: POSTADE.slice(offset, offset + limit) } });
  }
  if (url === "/api/v1/decisions") return Promise.resolve({ data: { decisions: [], total: 0 } });
  if (url === "/api/v1/drafts") return Promise.resolve({ data: { drafts: [], total: 0 } });
  return Promise.reject(new Error(`oväntat GET ${url}`));
}

const VERIFIKATIONER = sidan("bocker").vyer.find((v) => v.key === "bocker.verifikationer")!;

function Vyn() {
  const [sokterm, setSokterm] = useState("");
  const { data, laddar } = useVyer(AR, "bocker", sokterm)["bocker.verifikationer"];
  return (
    <div data-testid="vyn">
      <VyInnehall vy={VERIFIKATIONER} data={data} laddar={laddar} sok={{ varde: sokterm, onAndra: setSokterm }} />
    </div>
  );
}

let qc: QueryClient;
const rendera = () =>
  render(
    <QueryClientProvider client={qc}>
      <Vyn />
    </QueryClientProvider>
  );
const vyn = () => within(screen.getByTestId("vyn"));
const ruta = () => vyn().getByRole("searchbox", { name: "Sök bland verifikationerna" });
/** Radernas titlar, i ordning. Utan `DetaljProvider` är titeln ett spann. */
const titelElement = () => [...screen.getByTestId("vyn").querySelectorAll("[data-variant] > span > :first-child")];
const titlar = () => titelElement().map((e) => e.textContent);

beforeEach(() => {
  get.mockReset();
  get.mockImplementation(svaraGet);
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

describe("Sökrutan i Verifikationer", () => {
  it("utan sökterm är listan som förut och bara första sidan hämtas", async () => {
    rendera();
    await waitFor(() => expect(titlar()).toHaveLength(50));
    expect(ruta()).toHaveValue("");
    expect(vyn().getByText("Laddar fler…")).toBeInTheDocument();
    expect(get.mock.calls.some(([, c]) => c?.params?.status === "posted" && c.params.missing_attachment === false && c.params.limit === undefined)).toBe(false);
  });

  it("filtrerar för varje tangent och når verifikationer bortom hämtade sidor", async () => {
    const user = userEvent.setup();
    rendera();
    await waitFor(() => expect(titlar()).toHaveLength(50));

    await user.type(ruta(), "t");
    await user.type(ruta(), "el");
    await waitFor(() => expect(titlar()).toEqual(["Telia mobil"]));
    expect(vyn().getAllByText("1 träff").length).toBeGreaterThan(0);
    expect(vyn().queryByText("Laddar fler…")).toBeNull();
    // Årets alla postade, i ett anrop utan limit.
    expect(get).toHaveBeenCalledWith(
      "/api/v1/vouchers",
      expect.objectContaining({
        params: expect.objectContaining({ status: "posted", missing_attachment: false, limit: undefined, offset: undefined }),
      })
    );
    // De matchade tecknen är markerade.
    const markerat = titelElement()[0].querySelectorAll("mark");
    expect([...markerat].map((m) => m.textContent)).toEqual(["Tel"]);
  });

  it("rankar bästa träffen överst och Esc ger tillbaka listan", async () => {
    const user = userEvent.setup();
    rendera();
    await waitFor(() => expect(titlar()).toHaveLength(50));

    await user.type(ruta(), "hyr");
    await waitFor(() => expect(titlar()[0]).toBe("Hyra kontor"));

    await user.type(ruta(), "qqq");
    await waitFor(() => expect(vyn().getAllByText("inga träffar").length).toBeGreaterThan(0));
    expect(titlar()).toEqual([]);

    await user.keyboard("{Escape}");
    expect(ruta()).toHaveValue("");
    await waitFor(() => expect(titlar()).toHaveLength(50));
  });
});
