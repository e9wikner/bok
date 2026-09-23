import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { VyInnehall } from "@/components/skal/VyInnehall";
import { faktureringVy, lonerVy } from "@/lib/skal/betala";
import { allaVyer, sidan } from "@/lib/skal/vyer";

const fakturering = sidan("betala").vyer[0];
const loner = sidan("betala").vyer[1];

const FAKTUROR = faktureringVy({
  total: 1,
  invoices: [
    {
      id: "f1",
      invoice_number: 1042,
      customer_name: "Nordkraft AB",
      invoice_date: "2026-05-01",
      due_date: "2026-05-31",
      amount_inc_vat: 9375000,
      remaining_amount: 9375000,
      status: "overdue",
      is_overdue: true,
    },
  ],
});

const LONER = lonerVy({
  payroll_runs: [
    {
      id: "l1",
      year: 2026,
      month: 6,
      payment_date: "2026-06-25",
      status: "booked",
      payslip_count: 1,
      total_gross_salary: 6833800,
      total_net_salary: 5000000,
    },
  ],
});

describe("Fakturering och Löner är läsvyer utan skrivflöde (testfall 17)", () => {
  it("Fakturering har ingen knapp alls i vyn", () => {
    render(<VyInnehall vy={fakturering} data={FAKTUROR} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("Löner har ingen knapp alls i vyn", () => {
    render(<VyInnehall vy={loner} data={LONER} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("lovar inte en funktion som inte finns", () => {
    render(<VyInnehall vy={fakturering} data={FAKTUROR} />);
    // Ingen avstängd knapp, ingen "kommer snart". En yta som lovar en
    // funktion som inte finns är sämre än en yta som inte lovar den.
    expect(screen.queryByText(/kommer snart|snart tillgänglig|ej tillgänglig/i)).toBeNull();
    expect(document.querySelector("button[disabled]")).toBeNull();
  });

  it("säger i stället vad agenten gör och var skrivning sker i dag", () => {
    render(<VyInnehall vy={loner} data={LONER} />);
    expect(screen.getByText(/Godkännande görs tills vidare i den gamla lönevyn/)).toBeInTheDocument();
  });

  it("är de enda två vyerna som är märkta som läsvyer", () => {
    expect(allaVyer().filter((v) => v.lasvy).map((v) => v.titel)).toEqual([
      "Fakturering",
      "Löner",
    ]);
  });
});
