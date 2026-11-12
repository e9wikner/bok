import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ForslagStatusSvar } from "@/lib/chattyta/api";
import { verifikationerVy, type Verifikation, type Verifikationslista } from "@/lib/skal/bocker";
import { verifikationVy, type VerifikationDetalj } from "@/lib/skal/detalj";
import type { VyData, VyRadData } from "@/lib/skal/vydata";

/**
 * Godkänn utan underlag med ett tryck (migration 051), och `svara` på ett
 * väntande förslag.
 */

const post = vi.fn();
vi.mock("@/lib/api", () => ({ default: { post: (...a: unknown[]) => post(...a), get: vi.fn() } }));

const { VyRad } = await import("@/components/skal/VyRad");

const AR = { id: "fy", label: "2026", start: "2026-01-01", end: "2026-12-31" };

const v = (over: Partial<Verifikation>): Verifikation => ({
  id: "x",
  series: "A",
  number: 1,
  date: "2026-06-01",
  description: "Kontorsmaterial",
  status: "posted",
  total_debit: 100000,
  missing_attachment: false,
  age_days: 0,
  ...over,
});
const lista = (...vouchers: Verifikation[]): Verifikationslista => ({ total: vouchers.length, vouchers });
const sektion = (vy: VyData, titel: string): VyRadData[] =>
  vy.sektioner.find((s) => s.titel === titel)?.rader ?? [];

const forslag = (over: Partial<ForslagStatusSvar> = {}): ForslagStatusSvar => ({
  draft_id: "u1",
  post_id: "post-1",
  decision_id: null,
  correction_of: null,
  correction_note_id: null,
  status: "pending",
  replaced_by: null,
  posted_at: null,
  voucher: null,
  last_error_code: null,
  created_at: "2026-09-18T06:41:00",
  ...over,
});

describe("listan", () => {
  it("en rad i Saknar underlag kan godkännas utan underlag", () => {
    const a7 = v({ id: "a7", number: 7, missing_attachment: true, age_days: 3 });
    const vy = verifikationerVy(AR, lista(), lista(), { beslut: [], forslag: [], saknar: lista(a7) });
    expect(sektion(vy, "Saknar underlag")[0].underlagsval).toEqual({ voucherId: "a7" });
  });

  it("en godkänd verifikation säger varför i Postade och har ingen kvittolänk", () => {
    const a8 = v({
      id: "a8",
      number: 8,
      description: "Periodisering försäkring",
      underlag_waiver: { id: "w", reason: "none", waived_by: "stefan", created_at: "2026-06-02T10:00:00" },
    });
    const rad = sektion(verifikationerVy(AR, lista(a8), lista()), "Postade")[0];
    expect(rad.meta).toBe("A-8 · 2026-06-01 · inget underlag behövs");
    expect(rad.kvitto).toBeUndefined();
  });

  it("ett väntande förslag har `svara`, som visar kortet och fyller fältet", () => {
    const utkast = v({ id: "u1", status: "draft", number: null, description: "Hyra juni", date: "2026-06-05" });
    const vy = verifikationerVy(AR, lista(), lista(utkast), { beslut: [], forslag: [forslag()] });
    expect(sektion(vy, "Väntar på beslut")[0].fraga).toEqual({
      viewKey: "bocker.verifikationer",
      text: 'Om förslaget "Hyra juni" 2026-06-05: ',
      etikett: "svara",
      postId: "post-1",
    });
  });
});

describe("detaljen", () => {
  const detalj = (over: Partial<VerifikationDetalj>): VerifikationDetalj =>
    ({ ...v({ id: "a9", number: 9 }), rows: [], comment: null, ...over }) as VerifikationDetalj;
  const underlag = (vy: VyData) => sektion(vy, "Underlag")[0];

  it("saknar underlag: länkarna att godkänna", () => {
    expect(underlag(verifikationVy(detalj({ missing_attachment: true }))).underlagsval).toEqual({ voucherId: "a9" });
  });

  it("godkänd: vem och när, och ångra", () => {
    const rad = underlag(
      verifikationVy(
        detalj({
          underlag_waiver: { id: "w", reason: "later", waived_by: "stefan", created_at: "2026-06-02T10:00:00" },
        })
      )
    );
    expect(rad.meta).toBe("underlag kommer senare · godkänt av stefan 2026-06-02");
    expect(rad.underlagsval).toEqual({ voucherId: "a9", godkant: "later" });
    expect(rad.kvitto).toBeUndefined();
  });
});

describe("VyRad", () => {
  beforeEach(() => {
    post.mockReset().mockResolvedValue({ data: {} });
  });
  const rendera = (rad: React.ReactElement) =>
    render(<QueryClientProvider client={new QueryClient()}>{rad}</QueryClientProvider>);

  it.each([
    ["kommer senare", "later"],
    ["inget underlag", "none"],
  ])("`%s` godkänner med ett tryck", async (lank, reason) => {
    rendera(<VyRad titel="Hyra" meta="A-7 · kvitto saknas sedan 3 dgr" hoger="1" underlagsval={{ voucherId: "a7" }} />);
    fireEvent.click(screen.getByRole("button", { name: lank }));
    await waitFor(() => expect(screen.getByText("godkänt")).toBeInTheDocument());
    expect(post).toHaveBeenCalledWith("/api/v1/vouchers/a7/underlag-waiver", { reason });
  });

  it("`ångra` tar bort godkännandet", async () => {
    rendera(<VyRad titel="Underlag" hoger="" underlagsval={{ voucherId: "a7", godkant: "none" }} />);
    fireEvent.click(screen.getByRole("button", { name: "ångra" }));
    await waitFor(() => expect(screen.getByText("ångrat")).toBeInTheDocument());
    expect(post).toHaveBeenCalledWith("/api/v1/vouchers/a7/underlag-waiver/revoke");
  });

  it("ett fel säger det, och länkarna går att trycka igen", async () => {
    post.mockRejectedValue({ response: { status: 403, data: { detail: { code: "human_only" } } } });
    rendera(<VyRad titel="Hyra" hoger="1" underlagsval={{ voucherId: "a7" }} />);
    fireEvent.click(screen.getByRole("button", { name: "kommer senare" }));
    await waitFor(() => expect(screen.getByText(/gick inte/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "kommer senare" })).toBeEnabled();
  });
});
