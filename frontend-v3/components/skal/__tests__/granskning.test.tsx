import { readFileSync } from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DetaljProvider } from "@/components/skal/DetaljKontext";
import { FAST_TEXT, GranskningVy } from "@/components/skal/GranskningVy";
import {
  type Anmarkning,
  type Tackning,
  allvarligast,
  antalText,
  beloppKr,
  granskarePa,
  granskningStatus,
  ingangUrl,
  somRapport,
  somRapportrad,
  somTackning,
  sorteraAnmarkningar,
  tackningsrader,
  uppladdadText,
} from "@/lib/skal/granskning";
import { allaVyer } from "@/lib/skal/vyer";

/** Granskningen under Bokslut: rapporterna som externa agenter laddat upp, och täckningen. */

const get = vi.fn();
const post = vi.fn();
vi.mock("@/lib/api", () => ({
  default: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
    defaults: { baseURL: "http://bok.lan:8000" },
  },
}));

// Intl skriver ett hårt mellanslag som tusentalsavgränsare.
const mellanslag = (s: string | null) => (s ?? "").replace(/[  ]/g, " ");

const anm = (over: Partial<Anmarkning>): Anmarkning => ({
  id: "f",
  position: 0,
  severity: "observation",
  area: "moms",
  title: "",
  description: "",
  rule: null,
  amount_ore: null,
  suggested_correction: null,
  vouchers: [],
  ...over,
});

const RAPPORTRAD = {
  id: "r1",
  fiscal_year_id: "fy-2025",
  reviewer_agent: "Claude Code",
  reviewer_model: "claude-opus-5-5",
  instruction_sha256: "abc",
  instruction_outdated: false,
  uploaded_by: "review_key",
  uploaded_at: "2026-11-20 09:15:00",
  counts: { material: 1, should_fix: 1, observation: 0 },
};

const RAPPORT = {
  ...RAPPORTRAD,
  summary_markdown: "Jag granskade **hela året**.\n\n- urval: alla stora poster",
  examined_voucher_count: 42,
  findings: [
    {
      id: "f2",
      position: 0,
      severity: "should_fix",
      area: "periodisering",
      title: "Hyran för januari bokförd i december",
      description: "Fakturan avser januari.",
      rule: null,
      amount_ore: null,
      suggested_correction: null,
      vouchers: [],
    },
    {
      id: "f1",
      position: 1,
      severity: "material",
      area: "moms",
      title: "Utländsk tjänst bokförd utan omvänd moms",
      description: "Tjänsten köptes från ett bolag i Irland.",
      rule: "ML 1 kap. 2 § första st. 2",
      amount_ore: 125000,
      suggested_correction: "Boka 2645/2614 med 25 % på 5 000 kr.",
      vouchers: [{ id: "v12", number: "A12", date: "2025-03-04" }],
    },
  ],
};

const TACKNING: Tackning = {
  report_count: 3,
  vouchers: [
    {
      voucher_id: "v1",
      number: "A1",
      date: "2025-01-10",
      description: "Kontorsmaterial",
      examined_by_count: 3,
      flagged_by: [{ report_id: "r1", reviewer_agent: "Claude Code", reviewer_model: "opus", severity: "observation" }],
    },
    {
      voucher_id: "v2",
      number: "A2",
      date: "2025-02-01",
      description: "Konsulttjänst från Irland",
      examined_by_count: 3,
      flagged_by: [
        { report_id: "r1", reviewer_agent: "Claude Code", reviewer_model: "opus", severity: "should_fix" },
        { report_id: "r2", reviewer_agent: "Codex", reviewer_model: "gpt", severity: "material" },
        // Samma granskare två gånger är en granskare.
        { report_id: "r3", reviewer_agent: "Claude Code", reviewer_model: "opus", severity: "material" },
      ],
    },
    {
      voucher_id: "v3",
      number: "A3",
      date: "2025-01-05",
      description: "Ingen anmärkning",
      examined_by_count: 2,
      flagged_by: [],
    },
    {
      voucher_id: "v4",
      number: "A4",
      date: "2025-03-01",
      description: "Representation",
      examined_by_count: 1,
      flagged_by: [{ report_id: "r2", reviewer_agent: "Codex", reviewer_model: "gpt", severity: "material" }],
    },
  ],
};

function svara({
  rapporter = [RAPPORTRAD],
  rapport = RAPPORT,
  tackning = TACKNING as unknown,
}: { rapporter?: unknown[]; rapport?: unknown; tackning?: unknown } = {}) {
  get.mockImplementation((url: string) => {
    if (url.startsWith("/api/v1/review/reports?")) return Promise.resolve({ data: { reports: rapporter } });
    if (url.startsWith("/api/v1/review/reports/")) return Promise.resolve({ data: rapport });
    if (url.startsWith("/api/v1/review/coverage?")) return Promise.resolve({ data: tackning });
    return Promise.reject(new Error(url));
  });
}

function visa({ arId = "fy-2025" as string | null, oppna = vi.fn() } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utfall = render(
    <QueryClientProvider client={qc}>
      <DetaljProvider value={{ stack: [], oppna, bakat: vi.fn(), stang: vi.fn() }}>
        <GranskningVy titel="Granskning" arId={arId} variant="desktop" />
      </DetaljProvider>
    </QueryClientProvider>
  );
  return { ...utfall, oppna };
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

describe("kartan", () => {
  it("granskningen är en vy under Bokslut som chattar i Översiktens tråd", () => {
    const vy = allaVyer().find((v) => v.key === "bokslut.granskning");
    expect(vy).toMatchObject({ sida: "bokslut", slug: "granskning", titel: "Granskning", trad: "bokslut.rapporter" });
  });
});

describe("det vyn räknar", () => {
  it("sorterar anmärkningarna efter allvarlighet och sedan rapportens ordning", () => {
    const sorterade = sorteraAnmarkningar([
      anm({ id: "o", severity: "observation", position: 0 }),
      anm({ id: "s2", severity: "should_fix", position: 3 }),
      anm({ id: "m", severity: "material", position: 4 }),
      anm({ id: "s1", severity: "should_fix", position: 1 }),
    ]);
    expect(sorterade.map((a) => a.id)).toEqual(["m", "s1", "s2", "o"]);
    expect(allvarligast(["observation", "material", "should_fix"])).toBe("material");
    expect(allvarligast([])).toBeNull();
  });

  it("skriver öre som kronor, med svenska tecken", () => {
    expect(mellanslag(beloppKr(125000))).toBe("1 250 kr");
    expect(mellanslag(beloppKr(125050))).toBe("1 250,50 kr");
    expect(mellanslag(beloppKr(-500000))).toBe("−5 000 kr");
    expect(beloppKr(null)).toBeNull();
  });

  it("läser serverns UTC-tid utan zon och visar den i lokal tid", () => {
    const d = new Date("2026-11-20T09:15:00Z");
    const tva = (n: number) => String(n).padStart(2, "0");
    const lokal = `${d.getFullYear()}-${tva(d.getMonth() + 1)}-${tva(d.getDate())} ${tva(d.getHours())}:${tva(d.getMinutes())}`;
    expect(uppladdadText("2026-11-20 09:15:00")).toBe(lokal);
    expect(uppladdadText("2026-11-20T09:15:00Z")).toBe(lokal);
    expect(uppladdadText("")).toBe("");
  });

  it("räknar anmärkningarna per allvarlighet i ord", () => {
    expect(antalText({ material: 2, should_fix: 1, observation: 1 })).toBe("2 väsentliga · 1 bör rättas · 1 iakttagelse");
    expect(antalText({ material: 0, should_fix: 0, observation: 0 })).toBe("inga anmärkningar");
  });

  it("täckningen tar bara verifikationer med anmärkning, flest olika granskare först", () => {
    const rader = tackningsrader(TACKNING);
    expect(rader.map((r) => r.number)).toEqual(["A2", "A4", "A1"]);
    // A2: två granskare, inte tre; Claude Code med sin allvarligaste anmärkning.
    expect(rader[0].granskare.map((g) => [g.agent, g.severity])).toEqual([
      ["Claude Code", "material"],
      ["Codex", "material"],
    ]);
    expect(granskarePa(TACKNING.vouchers[2])).toEqual([]);
  });

  it("bygger ingångens adress ur API:ts bas, eller sidans egen", () => {
    expect(ingangUrl("http://bok.lan:8000/", "http://x:3000")).toBe("http://bok.lan:8000/api/v1/review/entrypoint");
    expect(ingangUrl("", "http://hubbabubba:3000")).toBe("http://hubbabubba:3000/api/v1/review/entrypoint");
    expect(ingangUrl(undefined, "http://hubbabubba:3000")).toBe("http://hubbabubba:3000/api/v1/review/entrypoint");
  });

  it("statusraden säger hur många rapporter och väsentliga anmärkningar året har", () => {
    const r = somRapportrad(RAPPORTRAD);
    expect(granskningStatus([r, r], false, "fy")).toEqual({ text: "2 rapporter · 2 väsentliga", lage: "vantar" });
    expect(granskningStatus([], false, "fy").lage).toBe("tomt");
    expect(granskningStatus(undefined, true, "fy").lage).toBe("fel");
    expect(granskningStatus(undefined, false, null).text).toBe("inget räkenskapsår");
  });

  it("tål saknade fält i svaren", () => {
    const r = somRapport({ id: "x", findings: [{ id: "f", severity: "okänd" }] });
    expect(r.counts).toEqual({ material: 0, should_fix: 0, observation: 0 });
    expect(r.instruction_outdated).toBe(false);
    expect(r.findings[0]).toMatchObject({ severity: "observation", vouchers: [], rule: null, amount_ore: null });
  });

  it("läser serverns svar som api/routes/review.py skickar dem", () => {
    const r = somRapport({
      id: "r1",
      reviewer: { agent: "Claude Code", model: "claude-opus-5-5" },
      counts: { material: 1, should_fix: 0, observation: 0 },
      findings: [
        {
          id: "f1",
          position: 1,
          severity: "material",
          vouchers: [{ id: "v1", series: "A", number: 12, voucher_number: "A-12", date: "2026-03-05" }],
        },
      ],
    });
    expect(r.reviewer_agent).toBe("Claude Code");
    expect(r.reviewer_model).toBe("claude-opus-5-5");
    expect(r.findings[0].vouchers[0]).toEqual({ id: "v1", number: "A-12", date: "2026-03-05" });

    const t = somTackning({
      report_count: 2,
      vouchers: [
        {
          id: "v1",
          voucher_number: "A-12",
          date: "2026-03-05",
          description: "Hyra",
          examined_count: 2,
          flagged_count: 1,
          flagged_by: [{ report_id: "r1", agent: "Claude Code", model: "m", severities: ["observation", "material"] }],
        },
      ],
    });
    expect(t.vouchers[0]).toMatchObject({ voucher_id: "v1", number: "A-12", examined_by_count: 2 });
    expect(t.vouchers[0].flagged_by[0]).toEqual({
      report_id: "r1",
      reviewer_agent: "Claude Code",
      reviewer_model: "m",
      severity: "material",
    });
  });
});

describe("vyn", () => {
  it("visar den fasta texten överst och listar rapporterna", async () => {
    svara({ rapporter: [RAPPORTRAD, { ...RAPPORTRAD, id: "r2", reviewer_agent: "Codex", reviewer_model: "gpt", instruction_outdated: true, uploaded_at: "2026-11-21 10:00:00" }] });
    visa();

    const fast = screen.getByText(FAST_TEXT);
    expect(fast).toBeInTheDocument();
    const rader = await screen.findAllByTestId("granskningsrapport");
    // Fasta texten står före allt annat innehåll.
    expect(fast.compareDocumentPosition(rader[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // Senast uppladdade först.
    expect(within(rader[0]).getByText("Codex · gpt")).toBeInTheDocument();
    expect(within(rader[0]).getByText("granskad mot en äldre instruktion")).toBeInTheDocument();
    expect(within(rader[1]).getByText("Claude Code · claude-opus-5-5")).toBeInTheDocument();
    expect(within(rader[1]).queryByText("granskad mot en äldre instruktion")).not.toBeInTheDocument();
    expect(within(rader[1]).getByTestId("antal-material")).toHaveTextContent("1 väsentlig");
    expect(within(rader[1]).getByTestId("antal-should_fix")).toHaveTextContent("1 bör rättas");
    expect(within(rader[1]).getByTestId("antal-observation")).toHaveTextContent("0 iakttagelse");
    expect(get).toHaveBeenCalledWith("/api/v1/review/reports?fiscal_year_id=fy-2025");
  });

  it("utan rapport kopierar en knapp ett uppdrag med en tillfällig nyckel", async () => {
    svara({ rapporter: [] });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    post.mockResolvedValue({
      data: { id: "t1", prompt: "Granska räkenskapsåret 2025 ... Bearer bokrev_abc", expires_at: "2026-11-21T14:05:00+00:00" },
    });
    visa();
    fireEvent.click(await screen.findByRole("button", { name: "Kopiera uppdrag till agent" }));

    expect(await screen.findByTestId("granskning-kopierad")).toHaveTextContent(/Kopierat · nyckeln gäller till \d\d:\d\d/);
    expect(post).toHaveBeenCalledWith("/api/v1/review/tokens", {
      fiscal_year_id: "fy-2025",
      entrypoint_url: "http://bok.lan:8000/api/v1/review/entrypoint",
    });
    expect(writeText).toHaveBeenCalledWith("Granska räkenskapsåret 2025 ... Bearer bokrev_abc");
    expect(screen.getByTestId("granskning-uppdrag")).toHaveTextContent("bokrev_abc");

    fireEvent.click(screen.getByRole("button", { name: "Återkalla" }));
    expect(await screen.findByText("Nyckeln är återkallad")).toBeInTheDocument();
    expect(post).toHaveBeenLastCalledWith("/api/v1/review/tokens/t1/revoke");
    expect(screen.queryByTestId("granskning-uppdrag")).not.toBeInTheDocument();
  });

  it("utan urklipp står uppdraget kvar att markera", async () => {
    svara({ rapporter: [] });
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockRejectedValue(new Error("nej")) },
      configurable: true,
    });
    post.mockResolvedValue({ data: { id: "t1", prompt: "uppdraget", expires_at: "2026-11-21T14:05:00+00:00" } });
    visa();
    fireEvent.click(await screen.findByRole("button", { name: "Kopiera uppdrag till agent" }));
    expect(await screen.findByTestId("granskning-uppdrag")).toHaveTextContent("uppdraget");
    expect(screen.getByTestId("granskning-kopierad")).not.toHaveTextContent("Kopierat");
  });

  it("med rapporter går en ny granskning också att starta", async () => {
    svara();
    visa();
    await screen.findAllByTestId("granskningsrapport");
    expect(screen.getByTestId("starta-granskning")).toBeInTheDocument();
  });

  it("en rapport visar sammanfattningen som markdown och anmärkningarna i allvarlighetsordning", async () => {
    svara();
    const { oppna } = visa();
    fireEvent.click(await screen.findByTestId("granskningsrapport"));

    const sammanfattning = await screen.findByTestId("granskning-sammanfattning");
    expect(within(sammanfattning).getByText("hela året").tagName).toBe("STRONG");
    expect(within(sammanfattning).getByRole("list")).toBeInTheDocument();
    expect(screen.getByText(/prövade 42 verifikationer/)).toBeInTheDocument();

    const anmarkningar = screen.getAllByTestId("anmarkning");
    expect(anmarkningar).toHaveLength(2);
    expect(within(anmarkningar[0]).getByText("Väsentlig")).toBeInTheDocument();
    expect(within(anmarkningar[0]).getByText("Moms")).toBeInTheDocument();
    expect(within(anmarkningar[0]).getByText("Utländsk tjänst bokförd utan omvänd moms")).toBeInTheDocument();
    expect(within(anmarkningar[0]).getByText("ML 1 kap. 2 § första st. 2")).toBeInTheDocument();
    expect(mellanslag(within(anmarkningar[0]).getByText(/kr$/).textContent)).toBe("1 250 kr");
    expect(within(anmarkningar[0]).getByText("Boka 2645/2614 med 25 % på 5 000 kr.")).toBeInTheDocument();
    expect(within(anmarkningar[1]).getByText("Bör rättas")).toBeInTheDocument();
    expect(within(anmarkningar[1]).getByText("Periodisering")).toBeInTheDocument();

    fireEvent.click(within(anmarkningar[0]).getByRole("button", { name: "A12" }));
    expect(oppna).toHaveBeenCalledWith({ typ: "ver", id: "v12" });
    expect(get).toHaveBeenCalledWith("/api/v1/review/reports/r1");

    fireEvent.click(screen.getByRole("button", { name: "← Alla rapporter" }));
    expect(await screen.findByTestId("granskningsrapport")).toBeInTheDocument();
  });

  it("står kvar i rapporten när vyn monteras om, som efter en öppnad verifikation", async () => {
    svara();
    const forsta = visa();
    fireEvent.click(await screen.findByTestId("granskningsrapport"));
    await screen.findByTestId("granskning-sammanfattning");
    forsta.unmount();

    visa();
    expect(await screen.findByTestId("granskning-sammanfattning")).toBeInTheDocument();
  });

  it("Täckning visar verifikationerna med anmärkning, flest granskare först, och länkar dem", async () => {
    svara();
    const { oppna } = visa();
    await screen.findByTestId("granskningsrapport");
    fireEvent.click(screen.getByRole("button", { name: "Täckning" }));

    const rader = await screen.findAllByTestId("tackningsrad");
    expect(rader.map((r) => within(r).getAllByRole("cell")[0].textContent)).toEqual(["A2", "A4", "A1"]);
    const celler = within(rader[0]).getAllByRole("cell");
    expect(celler[1]).toHaveTextContent("2025-02-01");
    expect(celler[2]).toHaveTextContent("Konsulttjänst från Irland");
    expect(celler[3]).toHaveTextContent("3 av 3");
    expect(within(celler[4]).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Claude Code · opus väsentlig",
      "Codex · gpt väsentlig",
    ]);
    expect(screen.queryByText("Ingen anmärkning")).not.toBeInTheDocument();

    fireEvent.click(within(rader[1]).getByRole("button", { name: "A4" }));
    expect(oppna).toHaveBeenCalledWith({ typ: "ver", id: "v4" });
    expect(get).toHaveBeenCalledWith("/api/v1/review/coverage?fiscal_year_id=fy-2025");
  });

  it("utan räkenskapsår frågar den ingenting", () => {
    visa({ arId: null });
    expect(screen.getByText("Det finns inget räkenskapsår att granska.")).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });
});

describe("orden (docs/granskning.md §1)", () => {
  const FORBJUDET = /revision|revisor/i; // täcker också "revisionsberättelse"
  const filer = ["components/skal/GranskningVy.tsx", "lib/skal/granskning.ts"];

  it.each(filer)("%s säger inte revision eller revisor, utom i den fasta texten", (fil) => {
    const kalla = readFileSync(path.resolve(__dirname, "../../..", fil), "utf8");
    const utanFastText = kalla.split(FAST_TEXT).join("");
    const traffar = utanFastText.split("\n").filter((rad) => FORBJUDET.test(rad));
    expect(traffar).toEqual([]);
  });

  it("den fasta texten står i källan ordagrant och bara en gång", () => {
    expect(FAST_TEXT).toBe(
      "Granskningen är styrelsens egen kontroll. Den är inte en revision och ersätter inte en revisor."
    );
    const kalla = readFileSync(path.resolve(__dirname, "../GranskningVy.tsx"), "utf8");
    expect(kalla.split(FAST_TEXT)).toHaveLength(2);
  });

  it("den ritade vyn säger dem bara i den fasta texten", async () => {
    svara();
    const { container } = visa();
    fireEvent.click(await screen.findByTestId("granskningsrapport"));
    await screen.findByTestId("granskning-sammanfattning");
    expect((container.textContent ?? "").split(FAST_TEXT).join("")).not.toMatch(FORBJUDET);

    fireEvent.click(screen.getByRole("button", { name: "Täckning" }));
    await screen.findAllByTestId("tackningsrad");
    expect((container.textContent ?? "").split(FAST_TEXT).join("")).not.toMatch(FORBJUDET);
  });
});
