import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LonebeskedVy } from "@/components/skal/LonebeskedVy";
import type { Lonebesked, Lonekorning } from "@/lib/skal/betala";
import { beskedLage, kanTasBort, lonebeskedStatus, pdfVag } from "@/lib/skal/lonebesked";
import { allaVyer } from "@/lib/skal/vyer";

/** Lönebeskeden i skalet: skicka, markera skickat, ta bort en obokförd körning, AGI:ns fält. */

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
const oppnaFil = vi.fn();
vi.mock("@/lib/chattyta/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/chattyta/api")>()),
  oppnaFil: (...a: unknown[]) => oppnaFil(...a),
}));

const besked = (over: Partial<Lonebesked> = {}): Lonebesked => ({
  id: "p1",
  employee_name: "Stefan",
  payment_date: "2026-02-25",
  gross_salary: 5200000,
  net_salary: 3900000,
  status: "generated",
  voucher_id: null,
  pdf_stored: true,
  pdf_sent_at: null,
  ...over,
});

const korning = (over: Partial<Lonekorning> = {}): Lonekorning => ({
  id: "r1",
  year: 2026,
  month: 2,
  payment_date: "2026-02-25",
  status: "generated",
  payslip_count: 1,
  total_gross_salary: 5200000,
  total_net_salary: 3900000,
  payslips: [besked()],
  agi: { year: 2026, month: 2, due_date: "2026-03-12", total_to_pay: 2933800, unbooked_payslips: 1, voucher_ids: {}, booked: false },
  ...over,
});

function visa(runs: Lonekorning[]) {
  get.mockImplementation((url: string) => {
    if (url === "/api/v1/payroll/runs") return Promise.resolve({ data: { payroll_runs: runs } });
    if (url === "/api/v1/payroll/agi/2026/2")
      return Promise.resolve({
        data: {
          year: 2026,
          month: 2,
          due_date: "2026-03-12",
          individuals: [{ employee_id: "e1", name: "Stefan", personal_number: "19800101-1234", gross_salary: 5200000, preliminary_tax: 1300000, employer_fee: 1633800 }],
          total_gross_salary: 5200000,
          total_preliminary_tax: 1300000,
          total_employer_fee: 1633800,
          total_to_pay: 2933800,
          unbooked_payslips: 1,
          voucher_ids: {},
          booked: false,
        },
      });
    return Promise.reject(new Error(url));
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LonebeskedVy titel="Lönebesked" arId="fy-2026" variant="desktop" />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  get.mockReset();
  post.mockReset().mockResolvedValue({ data: {} });
  del.mockReset().mockResolvedValue({ data: {} });
  oppnaFil.mockReset();
});

describe("kartan", () => {
  it("Lönebesked är en vy på Betala som chattar i Löners tråd", () => {
    expect(allaVyer().find((v) => v.key === "betala.lonebesked")).toMatchObject({ sida: "betala", trad: "betala.loner" });
  });
});

describe("reglerna", () => {
  it("säger om ett lönebesked är skickat och bokfört", () => {
    expect(beskedLage(besked())).toBe("inte skickat");
    expect(beskedLage(besked({ status: "sent", pdf_sent_at: "2026-02-26" }))).toBe("skickat");
    expect(beskedLage(besked({ status: "booked", voucher_id: "v", pdf_sent_at: "2026-02-26" }))).toBe("skickat och bokfört");
  });

  it("en körning med ett bokfört lönebesked kan inte tas bort", () => {
    expect(kanTasBort(korning())).toBe(true);
    expect(kanTasBort(korning({ payslips: [besked({ voucher_id: "v" })] }))).toBe(false);
  });

  it("öppnar den sparade PDF:en, annars en nyss renderad", () => {
    expect(pdfVag(besked())).toBe("/api/v1/payroll/payslips/p1/pdf");
    expect(pdfVag(besked({ pdf_stored: false }))).toBe("/api/v1/export/pdf/payslip/p1");
  });

  it("statusraden räknar de oskickade", () => {
    expect(lonebeskedStatus([korning()], false, "fy")).toEqual({ text: "1 inte skickat", lage: "vantar" });
    expect(lonebeskedStatus([], false, "fy").lage).toBe("tomt");
  });
});

describe("vyn", () => {
  it("öppnar PDF:en och markerar lönebeskedet skickat", async () => {
    visa([korning()]);
    fireEvent.click(await screen.findByRole("button", { name: "PDF" }));
    expect(oppnaFil).toHaveBeenCalledWith("/api/v1/payroll/payslips/p1/pdf");
    fireEvent.click(screen.getByRole("button", { name: "Markera skickat" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/payroll/payslips/p1/mark-sent"));
  });

  it("tar bort en obokförd körning efter en fråga, men erbjuder det inte för en bokförd", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { unmount } = visa([korning()]);
    fireEvent.click(await screen.findByRole("button", { name: "Ta bort" }));
    await waitFor(() => expect(del).toHaveBeenCalledWith("/api/v1/payroll/runs/r1"));
    unmount();

    visa([korning({ payslips: [besked({ voucher_id: "v", status: "booked" })] })]);
    await screen.findByText(/bokfört/);
    expect(screen.queryByRole("button", { name: "Ta bort" })).not.toBeInTheDocument();
    confirm.mockRestore();
  });

  it("fäller ut arbetsgivardeklarationens fält för månaden", async () => {
    visa([korning()]);
    fireEvent.click(await screen.findByRole("button", { name: /Arbetsgivardeklaration för februari 2026/ }));
    expect(await screen.findByText(/215: 19800101-1234/)).toBeInTheDocument();
    expect(screen.getByText(/Bokför månadens löner först/)).toBeInTheDocument();
  });
});
