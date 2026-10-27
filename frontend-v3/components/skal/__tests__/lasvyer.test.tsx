import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { VyInnehall } from "@/components/skal/VyInnehall";
import type { BeslutSvar } from "@/lib/chattyta/api";
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

describe("Fakturering och Löner har ingen knapp i vyn (testfall 17)", () => {
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

  it("säger i stället hur en lön bokförs: i kortet agenten lägger fram", () => {
    render(<VyInnehall vy={loner} data={LONER} />);
    expect(screen.getByText(/Du bokför med ett tryck i kortet/)).toBeInTheDocument();
  });

  it("ingen vy är längre märkt som läsvy (SPEC-fakturering-f1.md testfall 38)", () => {
    // Fakturering skriver sedan F1 och Löner sedan lönebokföringen — i
    // tråden, genom kortet, inte med knappar i vyn. Vyn själv har
    // fortfarande ingen knapp (ovan).
    expect(allaVyer().filter((v) => v.lasvy).map((v) => v.titel)).toEqual([]);
  });

  it("ett lönekort som väntar är raden att klicka på, som ett beslut i Verifikationer", () => {
    const kort = {
      id: "d1",
      view_key: "betala.loner",
      kind: "approval",
      status: "open",
      title: "Bokför lön juni 2026 · Anna Andersson",
      amount_ore: 5000000,
      reason: "",
      consequence: "",
      source: null,
      age_days: 0,
      thread_id: null,
      post_id: null,
      options: [],
    } as unknown as BeslutSvar;
    render(<VyInnehall vy={loner} data={lonerVy({ payroll_runs: [] }, { beslut: [kort] })} />);
    const knapp = screen.getByTestId("vyrad-beslut");
    expect(knapp).toHaveTextContent("Bokför lön juni 2026 · Anna Andersson");
    expect(knapp).toHaveAttribute("title", "Ta upp i chatten");
    // Bokföringen sker i kortet i chatten, inte i vyn: raden är den enda knappen.
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });
});
