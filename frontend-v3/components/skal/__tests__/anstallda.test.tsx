import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AnstalldaVy } from "@/components/skal/AnstalldaVy";
import type { PayrollEmployee } from "@/lib/api";
import {
  anstalldaStatus,
  kronorTillOre,
  procentTillBp,
  utbetalningsdatum,
  vanligasteUtbetalningsdag,
} from "@/lib/skal/anstallda";
import { allaVyer } from "@/lib/skal/vyer";

/** Anställda: där lönerna ställs in och månadens lönebesked skapas. */

const get = vi.fn();
const post = vi.fn();
const put = vi.fn();
const del = vi.fn();
vi.mock("@/lib/api", () => ({
  default: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
    put: (...a: unknown[]) => put(...a),
    delete: (...a: unknown[]) => del(...a),
  },
}));

const anna = (over: Partial<PayrollEmployee> = {}): PayrollEmployee => ({
  id: "e1",
  name: "Anna Andersson",
  personal_number: "19900101-1234",
  email: null,
  bank_account: null,
  active: true,
  salary_setting: {
    id: "s1",
    employee_id: "e1",
    gross_monthly_salary: 3250000,
    preliminary_tax: 780000,
    employer_fee_rate_bp: 3142,
    employer_fee_amount: null,
    calculated_employer_fee: 1021150,
    payment_day: 25,
    active: true,
  },
  ...over,
});

function visa(onGaTill = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <AnstalldaVy titel="Anställda" variant="desktop" onGaTill={onGaTill} />
    </QueryClientProvider>
  );
  return onGaTill;
}

beforeEach(() => {
  [get, post, put, del].forEach((f) => f.mockReset());
});

describe("kartan", () => {
  it("Anställda är en vy under Inställningar som chattar i Löners tråd", () => {
    const vy = allaVyer().find((v) => v.key === "installningar.anstallda");
    expect(vy).toMatchObject({ sida: "installningar", slug: "anstallda", trad: "betala.loner" });
  });
});

describe("talen", () => {
  it("läser kronor med mellanslag och komma som öre", () => {
    expect(kronorTillOre("32 500,50")).toBe(3250050);
    expect(kronorTillOre("")).toBeNull();
    expect(kronorTillOre("abc")).toBeNull();
    expect(procentTillBp("31,42")).toBe(3142);
  });

  it("flyttar utbetalningsdagen till månadens sista dag i en kort månad", () => {
    expect(utbetalningsdatum(2026, 2, 31)).toBe("2026-02-28");
    expect(utbetalningsdatum(2026, 11, 25)).toBe("2026-11-25");
  });

  it("föreslår den utbetalningsdag de flesta har", () => {
    const b = anna({ id: "e2" });
    b.salary_setting = { ...b.salary_setting!, payment_day: 27 };
    const c = anna({ id: "e3" });
    c.salary_setting = { ...c.salary_setting!, payment_day: 27 };
    expect(vanligasteUtbetalningsdag([anna(), b, c])).toBe(27);
    expect(vanligasteUtbetalningsdag([])).toBe(25);
  });

  it("statusen säger vem som saknar lön", () => {
    expect(anstalldaStatus([], false)).toEqual({ text: "inga anställda", lage: "tomt" });
    expect(anstalldaStatus([anna({ salary_setting: null })], false).text).toBe("1 utan lön inställd");
    expect(anstalldaStatus([anna()], false).text).toBe("1 anställd");
  });
});

describe("vyn", () => {
  it("utan anställda står formuläret för den första öppet", async () => {
    get.mockResolvedValue({ data: { employees: [] } });
    visa();
    expect(await screen.findByText(/Inga anställda än/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Lägg till anställd" })).toBeInTheDocument();
  });

  it("en ny anställd sparas med sin lön i öre och avgiften i baspunkter", async () => {
    get.mockResolvedValue({ data: { employees: [] } });
    post.mockResolvedValue({ data: anna({ salary_setting: null }) });
    put.mockResolvedValue({ data: anna() });
    visa();
    await screen.findByText(/Inga anställda än/);

    fireEvent.change(screen.getByLabelText("Namn"), { target: { value: "Anna Andersson" } });
    fireEvent.change(screen.getByLabelText("Bruttolön per månad, kr"), { target: { value: "32 500" } });
    fireEvent.change(screen.getByLabelText(/Skatt att dra/), { target: { value: "7800" } });
    fireEvent.click(screen.getByRole("button", { name: "Lägg till anställd" }));

    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toBe("/api/v1/payroll/employees");
    expect(post.mock.calls[0][1]).toMatchObject({ name: "Anna Andersson", active: true });
    expect(put.mock.calls[0]).toEqual([
      "/api/v1/payroll/employees/e1/salary",
      {
        gross_monthly_salary: 3250000,
        preliminary_tax: 780000,
        employer_fee_rate_bp: 3142,
        payment_day: 25,
        employer_fee_amount: null,
        active: true,
      },
    ]);
  });

  it("skatt större än bruttolönen skickas inte", async () => {
    get.mockResolvedValue({ data: { employees: [] } });
    visa();
    await screen.findByText(/Inga anställda än/);
    fireEvent.change(screen.getByLabelText("Namn"), { target: { value: "Bo" } });
    fireEvent.change(screen.getByLabelText("Bruttolön per månad, kr"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText(/Skatt att dra/), { target: { value: "200" } });
    fireEvent.click(screen.getByRole("button", { name: "Lägg till anställd" }));
    expect(await screen.findByText(/Skatten kan inte vara större/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("månadens lönebesked skapas som körning och genereras, och leder till Löner", async () => {
    get.mockResolvedValue({ data: { employees: [anna()] } });
    post
      .mockResolvedValueOnce({ data: { id: "r1", payslip_count: 0 } })
      .mockResolvedValueOnce({ data: { id: "r1", payslip_count: 1 } });
    const onGaTill = visa();
    await screen.findByText("Anna Andersson");
    fireEvent.change(screen.getByLabelText("Månad"), { target: { value: "2026-02" } });
    fireEvent.change(screen.getByLabelText(/^Utbetalningsdag/), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Skapa lönebesked" }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[0]).toEqual([
      "/api/v1/payroll/runs",
      { year: 2026, month: 2, payment_date: "2026-02-28" },
    ]);
    expect(post.mock.calls[1][0]).toBe("/api/v1/payroll/runs/r1/generate");
    fireEvent.click(await screen.findByRole("button", { name: /Till Löner/ }));
    expect(onGaTill).toHaveBeenCalledWith("betala.loner");
  });

  it("misslyckas lönebeskeden tas den tomma körningen bort", async () => {
    get.mockResolvedValue({ data: { employees: [anna()] } });
    post
      .mockResolvedValueOnce({ data: { id: "r1", payslip_count: 0 } })
      .mockRejectedValueOnce({ response: { data: { detail: { error: "Saknar personnummer", code: "x" } } } });
    del.mockResolvedValue({ data: {} });
    visa();
    await screen.findByText("Anna Andersson");
    fireEvent.click(screen.getByRole("button", { name: "Skapa lönebesked" }));
    expect(await screen.findByText("Saknar personnummer")).toBeInTheDocument();
    expect(del).toHaveBeenCalledWith("/api/v1/payroll/runs/r1");
  });

  it("en anställd som slutat markeras inaktiv, och lönen skickas inte om", async () => {
    get.mockResolvedValue({ data: { employees: [anna()] } });
    put.mockResolvedValue({ data: anna({ active: false }) });
    visa();
    fireEvent.click(await screen.findByText("Anna Andersson"));
    fireEvent.click(screen.getByRole("button", { name: "Har slutat" }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put.mock.calls[0][0]).toBe("/api/v1/payroll/employees/e1");
    expect(put.mock.calls[0][1]).toMatchObject({ active: false, name: "Anna Andersson" });
  });
});
