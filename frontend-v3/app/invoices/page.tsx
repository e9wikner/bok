"use client";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useInvoices } from "@/hooks/useData";
import { formatCurrency, formatDate } from "@/lib/utils";
import { Receipt, Clock, CheckCircle2, AlertTriangle, Send, Plus } from "lucide-react";
import Link from "next/link";

const STATUS_CONFIG: Record<string, { label: string; variant: any; icon: any }> = {
  draft: { label: "Utkast", variant: "secondary", icon: Clock },
  sent: { label: "Skickad", variant: "default", icon: Send },
  paid: { label: "Betald", variant: "success", icon: CheckCircle2 },
  overdue: { label: "Förfallen", variant: "destructive", icon: AlertTriangle },
  cancelled: { label: "Makulerad", variant: "outline", icon: null },
};

export default function InvoicesPage() {
  const { data, isLoading } = useInvoices();
  const invoices = data?.invoices || data || [];

  // Summary stats
  const totalAmount = invoices.reduce((s: number, i: any) => s + (i.amount_inc_vat || i.total_amount || 0), 0);
  const paidCount = invoices.filter((i: any) => i.status === "paid").length;
  const overdueCount = invoices.filter((i: any) => i.status === "overdue" || i.is_overdue).length;
  const totalPaid = invoices.reduce((s: number, i: any) => s + (i.paid_amount || 0), 0);
  const totalRemaining = totalAmount - totalPaid;

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1400px] mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">Fakturor</h1>
          <p className="text-muted-foreground mt-1">Hantera kundfakturor och betalningar</p>
        </div>
        <Link href="/invoices/new">
          <Button>
            <Plus className="h-4 w-4 mr-2" />
            Ny faktura
          </Button>
        </Link>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">Totalt fakturerat</p>
            <p className="text-2xl font-bold mt-1">{formatCurrency(totalAmount)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">Antal fakturor</p>
            <p className="text-2xl font-bold mt-1">{invoices.length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">Betalda</p>
            <p className="text-2xl font-bold text-emerald-600 mt-1">{paidCount}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">Förfallna</p>
            <p className="text-2xl font-bold text-red-600 mt-1">{overdueCount}</p>
            {totalRemaining > 0 && (
              <p className="text-xs text-muted-foreground mt-1">Utestående: {formatCurrency(totalRemaining)}</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Invoice list */}
      <Card>
        <CardHeader>
          <CardTitle>Alla fakturor</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : invoices.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left p-4 font-medium text-muted-foreground">Fakturanr</th>
                    <th className="text-left p-4 font-medium text-muted-foreground">Kund</th>
                    <th className="text-left p-4 font-medium text-muted-foreground">Datum</th>
                    <th className="text-left p-4 font-medium text-muted-foreground">Förfallodatum</th>
                    <th className="text-left p-4 font-medium text-muted-foreground">Status</th>
                    <th className="text-right p-4 font-medium text-muted-foreground">Belopp</th>
                    <th className="text-right p-4 font-medium text-muted-foreground">Betalt</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((inv: any) => {
                    const effectiveStatus = inv.is_overdue && inv.status !== "paid" ? "overdue" : inv.status;
                    const config = STATUS_CONFIG[effectiveStatus] || STATUS_CONFIG.draft;
                    const amount = inv.amount_inc_vat || inv.total_amount || 0;
                    const paid = inv.paid_amount || 0;
                    return (
                      <tr key={inv.id} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                        <td className="p-4 font-medium">
                          <Link href={`/invoices/${inv.id}`} className="flex items-center gap-2 text-primary hover:underline">
                            <Receipt className="h-4 w-4 text-muted-foreground" />
                            {inv.invoice_number || inv.id?.substring(0, 8)}
                          </Link>
                        </td>
                        <td className="p-4">{inv.customer_name}</td>
                        <td className="p-4 text-muted-foreground">{formatDate(inv.invoice_date)}</td>
                        <td className="p-4 text-muted-foreground">{formatDate(inv.due_date)}</td>
                        <td className="p-4">
                          <Badge variant={config.variant}>{config.label}</Badge>
                        </td>
                        <td className="p-4 text-right font-mono font-medium">
                          {formatCurrency(amount)}
                        </td>
                        <td className="p-4 text-right font-mono">
                          {paid > 0 ? (
                            <span className={paid >= amount ? "text-emerald-600" : "text-amber-600"}>
                              {formatCurrency(paid)}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">-</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-12 text-center text-muted-foreground">
              <Receipt className="h-12 w-12 mx-auto mb-4 opacity-30" />
              <p>Inga fakturor ännu</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
