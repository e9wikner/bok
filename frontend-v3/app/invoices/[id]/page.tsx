"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import {
  ArrowLeft,
  Send,
  BookOpen,
  CreditCard,
  Receipt,
  AlertTriangle,
} from "lucide-react";

const STATUS_CONFIG: Record<string, { label: string; variant: any }> = {
  draft: { label: "Utkast", variant: "secondary" },
  sent: { label: "Skickad", variant: "default" },
  paid: { label: "Betald", variant: "success" },
  partial: { label: "Delbetalad", variant: "warning" },
  overdue: { label: "Förfallen", variant: "destructive" },
  cancelled: { label: "Makulerad", variant: "outline" },
  booked: { label: "Bokförd", variant: "success" },
};

const VAT_LABELS: Record<string, string> = {
  MP1: "25%",
  MP2: "12%",
  MP3: "6%",
  MF: "0%",
};

export default function InvoiceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [showPaymentForm, setShowPaymentForm] = useState(false);
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentDate, setPaymentDate] = useState(
    new Date().toISOString().split("T")[0]
  );
  const [paymentMethod, setPaymentMethod] = useState("bank_transfer");
  const [actionMessage, setActionMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  const {
    data: invoice,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["invoice", id],
    queryFn: () => api.getInvoice(id),
    enabled: !!id,
  });

  const sendMutation = useMutation({
    mutationFn: () => api.sendInvoice(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoice", id] });
      setActionMessage({ type: "success", text: "Fakturan har skickats" });
    },
    onError: () => {
      setActionMessage({
        type: "error",
        text: "Kunde inte skicka fakturan",
      });
    },
  });

  const bookMutation = useMutation({
    mutationFn: () => api.bookInvoice(id, invoice?.period_id || "default"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoice", id] });
      setActionMessage({ type: "success", text: "Fakturan har bokförts" });
    },
    onError: () => {
      setActionMessage({
        type: "error",
        text: "Kunde inte bokföra fakturan",
      });
    },
  });

  const paymentMutation = useMutation({
    mutationFn: (data: {
      amount: number;
      payment_date: string;
      payment_method: string;
    }) => api.registerPayment(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoice", id] });
      setShowPaymentForm(false);
      setPaymentAmount("");
      setActionMessage({
        type: "success",
        text: "Betalning registrerad",
      });
    },
    onError: () => {
      setActionMessage({
        type: "error",
        text: "Kunde inte registrera betalning",
      });
    },
  });

  useEffect(() => {
    if (!actionMessage) return;
    const t = setTimeout(() => setActionMessage(null), 5000);
    return () => clearTimeout(t);
  }, [actionMessage]);

  if (isLoading) {
    return (
      <div className="p-4 lg:p-8 space-y-6 max-w-[1000px] mx-auto">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (isError || !invoice) {
    return (
      <div className="p-4 lg:p-8 space-y-6 max-w-[1000px] mx-auto">
        <Link
          href="/invoices"
          className="text-sm text-primary hover:underline flex items-center gap-1"
        >
          <ArrowLeft className="h-4 w-4" /> Tillbaka till fakturor
        </Link>
        <Card>
          <CardContent className="p-12 text-center">
            <AlertTriangle className="h-12 w-12 mx-auto mb-4 text-red-500 opacity-50" />
            <p className="text-muted-foreground">
              Kunde inte hämta fakturan
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const effectiveStatus =
    invoice.is_overdue && invoice.status !== "paid"
      ? "overdue"
      : invoice.status;
  const statusConfig = STATUS_CONFIG[effectiveStatus] || STATUS_CONFIG.draft;
  const rows = invoice.rows || [];

  // Group VAT by code
  const vatByCode: Record<string, { exVat: number; vat: number }> = {};
  rows.forEach((r: any) => {
    const code = r.vat_code || "MF";
    if (!vatByCode[code]) vatByCode[code] = { exVat: 0, vat: 0 };
    vatByCode[code].exVat += r.amount_ex_vat || 0;
    vatByCode[code].vat += r.vat_amount || 0;
  });

  const handlePayment = () => {
    const amountInOre = Math.round(parseFloat(paymentAmount) * 100);
    if (!amountInOre || amountInOre <= 0) return;
    paymentMutation.mutate({
      amount: amountInOre,
      payment_date: paymentDate,
      payment_method: paymentMethod,
    });
  };

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1000px] mx-auto">
      {/* Back link */}
      <Link
        href="/invoices"
        className="text-sm text-primary hover:underline flex items-center gap-1"
      >
        <ArrowLeft className="h-4 w-4" /> Tillbaka till fakturor
      </Link>

      {/* Action message */}
      {actionMessage && (
        <div
          className={`p-3 rounded-lg text-sm ${
            actionMessage.type === "success"
              ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400"
              : "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400"
          }`}
        >
          {actionMessage.text}
        </div>
      )}

      {/* Invoice header */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between">
            <div>
              <CardTitle className="flex items-center gap-3 text-xl">
                <Receipt className="h-5 w-5 text-primary" />
                Faktura {invoice.invoice_number}
              </CardTitle>
              <p className="text-lg mt-2">{invoice.customer_name}</p>
              {invoice.customer_org_number && (
                <p className="text-sm text-muted-foreground">
                  Org.nr: {invoice.customer_org_number}
                </p>
              )}
            </div>
            <Badge variant={statusConfig.variant} className="text-sm">
              {statusConfig.label}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-muted-foreground">Fakturadatum</p>
              <p className="text-sm font-medium">
                {formatDate(invoice.invoice_date)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Förfallodatum</p>
              <p className="text-sm font-medium">
                {formatDate(invoice.due_date)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Betalt</p>
              <p className="text-sm font-medium">
                {formatCurrency(invoice.paid_amount || 0)}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Kvar att betala</p>
              <p className="text-sm font-medium">
                {formatCurrency(invoice.remaining_amount || 0)}
              </p>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex flex-wrap gap-2 mt-6 pt-4 border-t">
            {invoice.status === "draft" && (
              <Button
                onClick={() => sendMutation.mutate()}
                disabled={sendMutation.isPending}
                className="gap-2"
              >
                <Send className="h-4 w-4" />
                {sendMutation.isPending ? "Skickar..." : "Skicka faktura"}
              </Button>
            )}
            {invoice.status === "sent" && (
              <Button
                onClick={() => bookMutation.mutate()}
                disabled={bookMutation.isPending}
                variant="outline"
                className="gap-2"
              >
                <BookOpen className="h-4 w-4" />
                {bookMutation.isPending ? "Bokför..." : "Bokför"}
              </Button>
            )}
            {(invoice.status === "sent" || invoice.status === "partial") && (
              <Button
                onClick={() => setShowPaymentForm(!showPaymentForm)}
                variant="outline"
                className="gap-2"
              >
                <CreditCard className="h-4 w-4" />
                Registrera betalning
              </Button>
            )}
          </div>

          {/* Payment form */}
          {showPaymentForm && (
            <div className="mt-4 p-4 border rounded-lg space-y-3 bg-muted/30">
              <p className="text-sm font-medium">Registrera betalning</p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="text-xs text-muted-foreground">
                    Belopp (kr)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={paymentAmount}
                    onChange={(e) => setPaymentAmount(e.target.value)}
                    placeholder={String(
                      (invoice.remaining_amount || 0) / 100
                    )}
                    className="w-full mt-1 px-3 py-2 text-sm border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Datum</label>
                  <input
                    type="date"
                    value={paymentDate}
                    onChange={(e) => setPaymentDate(e.target.value)}
                    className="w-full mt-1 px-3 py-2 text-sm border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">
                    Betalningsmetod
                  </label>
                  <select
                    value={paymentMethod}
                    onChange={(e) => setPaymentMethod(e.target.value)}
                    className="w-full mt-1 px-3 py-2 text-sm border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="bank_transfer">Banköverföring</option>
                    <option value="swish">Swish</option>
                    <option value="card">Kort</option>
                    <option value="cash">Kontant</option>
                  </select>
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  onClick={handlePayment}
                  disabled={paymentMutation.isPending || !paymentAmount}
                  size="sm"
                >
                  {paymentMutation.isPending
                    ? "Sparar..."
                    : "Spara betalning"}
                </Button>
                <Button
                  onClick={() => setShowPaymentForm(false)}
                  variant="ghost"
                  size="sm"
                >
                  Avbryt
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Invoice rows */}
      <Card>
        <CardHeader>
          <CardTitle>Fakturarader</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-left p-4 font-medium text-muted-foreground">
                    Beskrivning
                  </th>
                  <th className="text-right p-4 font-medium text-muted-foreground">
                    Antal
                  </th>
                  <th className="text-right p-4 font-medium text-muted-foreground">
                    À-pris
                  </th>
                  <th className="text-center p-4 font-medium text-muted-foreground">
                    Moms
                  </th>
                  <th className="text-right p-4 font-medium text-muted-foreground">
                    Totalt
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row: any, i: number) => (
                  <tr
                    key={i}
                    className="border-b last:border-0 hover:bg-muted/30 transition-colors"
                  >
                    <td className="p-4">{row.description}</td>
                    <td className="p-4 text-right font-mono">
                      {row.quantity}
                    </td>
                    <td className="p-4 text-right font-mono">
                      {formatCurrency(row.unit_price || 0)}
                    </td>
                    <td className="p-4 text-center">
                      <Badge variant="outline">
                        {VAT_LABELS[row.vat_code] || row.vat_code}
                      </Badge>
                    </td>
                    <td className="p-4 text-right font-mono font-medium">
                      {formatCurrency(row.amount_inc_vat || 0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* VAT specification + Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* VAT per code */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Momsspecifikation</CardTitle>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left pb-2 font-medium text-muted-foreground">
                    Momskod
                  </th>
                  <th className="text-right pb-2 font-medium text-muted-foreground">
                    Underlag
                  </th>
                  <th className="text-right pb-2 font-medium text-muted-foreground">
                    Moms
                  </th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(vatByCode).map(([code, vals]) => (
                  <tr key={code} className="border-b last:border-0">
                    <td className="py-2">
                      {code} ({VAT_LABELS[code] || "?"})
                    </td>
                    <td className="py-2 text-right font-mono">
                      {formatCurrency(vals.exVat)}
                    </td>
                    <td className="py-2 text-right font-mono">
                      {formatCurrency(vals.vat)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>

        {/* Summary */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Summering</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Exkl. moms</span>
                <span className="font-mono">
                  {formatCurrency(invoice.amount_ex_vat || 0)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Moms</span>
                <span className="font-mono">
                  {formatCurrency(invoice.vat_amount || 0)}
                </span>
              </div>
              <div className="flex justify-between pt-2 border-t font-medium text-base">
                <span>Inkl. moms</span>
                <span className="font-mono">
                  {formatCurrency(invoice.amount_inc_vat || 0)}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
