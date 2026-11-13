import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { VyRad } from "@/components/skal/VyRad";
import { type Faktura, faktureringVy } from "@/lib/skal/betala";

/** En betalning på en utfärdad faktura, registrerad från Faktureringens rad. */

const post = vi.fn();
vi.mock("@/lib/api", () => ({
  default: { post: (...a: unknown[]) => post(...a), get: vi.fn() },
}));

const faktura = (over: Partial<Faktura>): Faktura => ({
  id: "f1",
  invoice_number: "2026-1",
  customer_name: "QRTECH",
  invoice_date: "2026-07-31",
  due_date: "2026-08-30",
  amount_inc_vat: 2800000,
  remaining_amount: 2800000,
  status: "sent",
  is_overdue: false,
  voucher_id: "v1",
  payment_voucher_ids: [],
  ...over,
});

beforeEach(() => post.mockReset().mockResolvedValue({ data: {} }));

describe("raden", () => {
  it("en obetald faktura får länken, en betald inte", () => {
    const vy = faktureringVy({
      total: 2,
      invoices: [faktura({}), faktura({ id: "f2", status: "paid", remaining_amount: 0 })],
    });
    const rader = vy.sektioner.flatMap((s) => s.rader);
    expect(rader.find((r) => r.id === "f1")?.betalning).toEqual({ invoiceId: "f1", kvar: 2800000 });
    expect(rader.find((r) => r.id === "f2")?.betalning).toBeUndefined();
  });

  it("fäller ut dag och belopp, förifyllt med det som återstår, och registrerar i öre", async () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <VyRad titel="QRTECH" meta="2026-1" hoger="28 000" betalning={{ invoiceId: "f1", kvar: 2800000 }} />
      </QueryClientProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: "registrera betalning" }));
    expect(screen.getByLabelText("Belopp")).toHaveValue("28000,00");
    fireEvent.change(screen.getByLabelText("Betalningsdag"), { target: { value: "2026-09-15" } });
    fireEvent.change(screen.getByLabelText("Belopp"), { target: { value: "10000" } });
    fireEvent.click(screen.getByRole("button", { name: "registrera" }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/api/v1/invoices/f1/payment", {
        amount: 1000000,
        payment_date: "2026-09-15",
        payment_method: "bank_transfer",
      })
    );
    await waitFor(() => expect(screen.queryByLabelText("Belopp")).not.toBeInTheDocument());
  });

  it("låter inte mer än det som återstår registreras", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <VyRad titel="QRTECH" hoger="" betalning={{ invoiceId: "f1", kvar: 100 }} />
      </QueryClientProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: "registrera betalning" }));
    fireEvent.change(screen.getByLabelText("Belopp"), { target: { value: "5" } });
    expect(screen.getByRole("button", { name: "registrera" })).toBeDisabled();
  });
});
