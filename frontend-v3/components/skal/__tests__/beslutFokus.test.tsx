import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BeslutFokusProvider, svarsinledning } from "@/components/skal/BeslutFokus";
import { ChattKolumn } from "@/components/skal/ChattKolumn";
import { VyRad } from "@/components/skal/VyRad";
import type { UseTrad } from "@/hooks/useTrad";
import type { BeslutSvar } from "@/lib/chattyta/api";

// Nätet: `GET /decisions` ger beslutens nuvarande läge, `POST .../retry` försöket.
const get = vi.fn();
const post = vi.fn();
vi.mock("@/lib/api", () => ({
  default: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) },
}));

const skicka = vi.fn(async () => true);
const tradSvar = { inlagg: [], strommande: null, fel: null, skicka, nollstall: vi.fn() } as unknown as UseTrad;
vi.mock("@/hooks/useTrad", () => ({ useTrad: () => tradSvar }));

const VY = "bocker.verifikationer";

const underlag = (over: Partial<BeslutSvar> = {}): BeslutSvar => ({
  id: "intake:s1",
  view_key: VY,
  kind: "intake",
  status: "open",
  title: "OpenCode Go maj 97kr.pdf",
  amount_ore: null,
  reason: "Momsregeln framgår inte av underlaget.",
  consequence: "Inget är bokfört från det här underlaget förrän felet är åtgärdat.",
  source: { kind: "intake_source", id: "s1", date: "2026-10-01" },
  age_days: 10,
  thread_id: null,
  post_id: null,
  options: [],
  ...over,
});

let qc: QueryClient;

function rendera(beslut: BeslutSvar, barn?: ReactNode) {
  return render(
    <QueryClientProvider client={qc}>
      <BeslutFokusProvider>
        <VyRad titel={beslut.title} meta="agenten avstod" hoger="" variant="vantar" beslut={beslut} />
        <ChattKolumn vyTitel="Verifikationer" viewKey={VY} />
        {barn}
      </BeslutFokusProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  get.mockReset();
  post.mockReset();
  skicka.mockClear();
  window.localStorage.clear();
});

describe("ett beslut tas upp i chatten", () => {
  it("raden är en knapp; klicket visar beslutet med agentens förklaring i chatten", async () => {
    const b = underlag();
    get.mockResolvedValue({ data: { decisions: [b], total: 1 } });
    rendera(b);

    expect(screen.queryByTestId("beslut-fokus")).toBeNull();
    fireEvent.click(screen.getByTestId("vyrad-beslut"));

    const kort = await screen.findByTestId("beslut-fokus");
    expect(within(kort).getByText("Momsregeln framgår inte av underlaget.")).toBeTruthy();
    expect(within(kort).getByText("Agenten avstod · behöver ditt beslut")).toBeTruthy();
    expect(within(kort).getByRole("button", { name: "Försök igen" })).toBeTruthy();
  });

  it("Svara agenten fyller fältet och bifogar underlaget; sändningen bär källans id", async () => {
    const b = underlag();
    get.mockResolvedValue({ data: { decisions: [b], total: 1 } });
    rendera(b);
    fireEvent.click(screen.getByTestId("vyrad-beslut"));
    fireEvent.click(await screen.findByRole("button", { name: "Svara agenten" }));

    const falt = screen.getByRole("textbox") as HTMLInputElement;
    await waitFor(() => expect(falt.value).toBe(svarsinledning(b)));
    expect(screen.getByTestId("filchip").textContent).toContain("OpenCode Go maj 97kr.pdf");

    fireEvent.change(falt, { target: { value: `${falt.value}omvänd skattskyldighet` } });
    fireEvent.submit(falt.closest("form")!);

    await waitFor(() => expect(skicka).toHaveBeenCalled());
    expect(skicka).toHaveBeenCalledWith(
      "Om underlaget OpenCode Go maj 97kr.pdf: omvänd skattskyldighet",
      ["s1"]
    );
  });

  it("Försök igen anropar retry och stänger kortet", async () => {
    const b = underlag();
    get.mockResolvedValue({ data: { decisions: [b], total: 1 } });
    post.mockResolvedValue({ data: { pass_started: true } });
    rendera(b);
    fireEvent.click(screen.getByTestId("vyrad-beslut"));
    // Efter försöket svarar servern utan beslutet.
    get.mockResolvedValue({ data: { decisions: [], total: 0 } });
    fireEvent.click(await screen.findByRole("button", { name: "Försök igen" }));

    await waitFor(() => expect(screen.queryByTestId("beslut-fokus")).toBeNull());
    expect(post).toHaveBeenCalledWith("/api/v1/intake/s1/retry", {});
  });

  it("Avfärda anropar dismiss och stänger kortet", async () => {
    const b = underlag();
    get.mockResolvedValue({ data: { decisions: [b], total: 1 } });
    post.mockResolvedValue({ data: null });
    rendera(b);
    fireEvent.click(screen.getByTestId("vyrad-beslut"));
    fireEvent.click(await screen.findByRole("button", { name: "Avfärda" }));
    get.mockResolvedValue({ data: { decisions: [], total: 0 } });
    fireEvent.click(screen.getByTestId("avfarda-ja"));

    await waitFor(() => expect(screen.queryByTestId("beslut-fokus")).toBeNull());
    expect(post).toHaveBeenCalledWith("/api/v1/decisions/intake%3As1/dismiss");
  });

  it("ett beslut som inte längre är öppet visas inte", async () => {
    const b = underlag();
    get.mockResolvedValue({ data: { decisions: [{ ...b, status: "answered" }], total: 1 } });
    rendera(b);
    fireEvent.click(screen.getByTestId("vyrad-beslut"));

    await waitFor(() => expect(get).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByTestId("beslut-fokus")).toBeNull());
  });

  it("ett beslut i en annan vy ritas inte i den här chatten", () => {
    const b = underlag({ view_key: "bocker.bank" });
    get.mockResolvedValue({ data: { decisions: [b], total: 1 } });
    rendera(b);
    fireEvent.click(screen.getByTestId("vyrad-beslut"));
    expect(screen.queryByTestId("beslut-fokus")).toBeNull();
  });
});

describe("ett kort utanför tråden går att svara", () => {
  const lonekort = (): BeslutSvar =>
    underlag({
      id: "d1",
      view_key: VY,
      kind: "approval",
      title: "Bokför lön oktober 2026 · Anna Andersson",
      amount_ore: 3900000,
      source: null,
      thread_id: "t1",
      // Inlägget står inte i den laddade tråden (`tradSvar.inlagg` är tom).
      post_id: "p-utanfor",
      options: [
        {
          id: "o-bok",
          position: 1,
          title: "Bokför lönen",
          rationale: "Bokför lönen mot utbetalningen.",
          account: null,
          amount_ore: null,
          recommended: true,
          is_exit: false,
        },
        {
          id: "o-nej",
          position: 2,
          title: "Inte nu",
          rationale: "Ingenting bokförs.",
          account: null,
          amount_ore: null,
          recommended: false,
          is_exit: true,
        },
      ],
    });

  it("reservkortet bär beslutets alternativ, och ett tryck svarar", async () => {
    const b = lonekort();
    get.mockResolvedValue({ data: { decisions: [b], total: 1 } });
    post.mockResolvedValue({ data: { decision: { ...b, status: "answered" }, post: {} } });
    rendera(b);
    fireEvent.click(screen.getByTestId("vyrad-beslut"));

    const kort = await screen.findByTestId("beslut-fokus");
    fireEvent.click(within(kort).getByText("Bokför lönen"));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/api/v1/decisions/d1/answer", { option_id: "o-bok" })
    );
  });
});

describe("en rad utan kort ber agenten", () => {
  it("be agenten fyller vyns fält och skickar ingenting", async () => {
    get.mockResolvedValue({ data: { decisions: [], total: 0 } });
    render(
      <QueryClientProvider client={qc}>
        <BeslutFokusProvider>
          <VyRad
            titel="Anna Andersson"
            meta="ej bokförd · utbetalning 2026-10-25"
            hoger="39 000"
            variant="vantar"
            fraga={{ viewKey: VY, text: "Om lönen för Anna Andersson, oktober 2026: " }}
          />
          <ChattKolumn vyTitel="Verifikationer" viewKey={VY} />
        </BeslutFokusProvider>
      </QueryClientProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "be agenten" }));

    const falt = screen.getByRole("textbox") as HTMLInputElement;
    await waitFor(() => expect(falt.value).toBe("Om lönen för Anna Andersson, oktober 2026: "));
    expect(skicka).not.toHaveBeenCalled();
  });
});

describe("en rad som leder till en annan vy", () => {
  it("ett beslut där tas upp och vyn byts dit", async () => {
    const { DetaljProvider } = await import("@/components/skal/DetaljKontext");
    const oppna = vi.fn();
    const b = underlag({ id: "d1", view_key: "betala.loner", kind: "approval", source: null });
    get.mockResolvedValue({ data: { decisions: [b], total: 1 } });
    render(
      <QueryClientProvider client={qc}>
        <BeslutFokusProvider>
          <DetaljProvider value={{ stack: [], oppna, bakat: vi.fn(), stang: vi.fn() }}>
            <VyRad
              titel="Bokför lön oktober 2026"
              meta="lön · väntar i Löner"
              hoger=""
              variant="vantar"
              beslut={b}
              mal={{ typ: "vy", key: "betala.loner" }}
            />
            <ChattKolumn vyTitel="Löner" viewKey="betala.loner" />
          </DetaljProvider>
        </BeslutFokusProvider>
      </QueryClientProvider>
    );

    fireEvent.click(screen.getByTestId("vyrad-beslut"));

    expect(oppna).toHaveBeenCalledWith({ typ: "vy", key: "betala.loner" });
    expect(await screen.findByTestId("beslut-fokus")).toBeTruthy();
  });
});
