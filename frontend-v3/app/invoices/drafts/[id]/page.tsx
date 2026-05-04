"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Bot, CheckCircle2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useInvoiceDraft } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";

export default function InvoiceDraftPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const draftId = String(params.id);
  const { data: draft, isLoading } = useInvoiceDraft(draftId);
  const [working, setWorking] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const approve = async () => {
    setWorking("approve");
    setError(null);
    try {
      const result = await api.approveInvoiceDraft(draftId);
      await queryClient.invalidateQueries({ queryKey: ["invoice-drafts"] });
      await queryClient.invalidateQueries({ queryKey: ["invoices"] });
      router.push(`/invoices/${result.approved_invoice_id}`);
    } catch (err: any) {
      setError(err?.response?.data?.detail?.error || "Kunde inte godkänna och bokföra utkastet.");
    } finally {
      setWorking(null);
    }
  };

  const reject = async () => {
    setWorking("reject");
    setError(null);
    try {
      await api.rejectInvoiceDraft(draftId);
      await queryClient.invalidateQueries({ queryKey: ["invoice-drafts"] });
      router.push("/invoices");
    } catch (err: any) {
      setError(err?.response?.data?.detail?.error || "Kunde inte avvisa utkastet.");
    } finally {
      setWorking(null);
    }
  };

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[1100px] space-y-4 p-4 lg:p-8">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!draft) {
    return <div className="p-8 text-muted-foreground">Fakturautkastet hittades inte.</div>;
  }

  const canApprove = draft.status !== "booked" && draft.status !== "rejected";

  return (
    <div className="mx-auto max-w-[1100px] space-y-6 p-4 lg:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight lg:text-3xl">Fakturautkast</h1>
          <p className="mt-1 text-muted-foreground">Granska agentens utkast innan bokföring.</p>
        </div>
        <Badge variant={draft.status === "booked" ? "default" : "outline"}>{draft.status}</Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{draft.customer_name}</CardTitle>
          <CardDescription>
            {draft.reference || "Ingen referens"} · {formatDate(draft.invoice_date)} - {formatDate(draft.due_date)}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          <div>
            <p className="text-sm text-muted-foreground">Exkl. moms</p>
            <p className="font-mono text-xl font-semibold">{formatCurrency(draft.amount_ex_vat || 0)}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Moms</p>
            <p className="font-mono text-xl font-semibold">{formatCurrency(draft.vat_amount || 0)}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Att fakturera</p>
            <p className="font-mono text-xl font-semibold">{formatCurrency(draft.amount_inc_vat || 0)}</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-primary" />
            Agentens underlag
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>{draft.agent_notes?.summary || "Ingen sammanfattning angiven."}</p>
          {typeof draft.agent_notes?.confidence === "number" && (
            <p className="text-muted-foreground">Konfidens: {Math.round(draft.agent_notes.confidence * 100)}%</p>
          )}
          {draft.agent_notes?.warnings?.length > 0 && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
              {draft.agent_notes.warnings.map((warning: string) => (
                <p key={warning}>{warning}</p>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Fakturarader</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="p-3 text-left font-medium text-muted-foreground">Beskrivning</th>
                <th className="p-3 text-right font-medium text-muted-foreground">Antal</th>
                <th className="p-3 text-right font-medium text-muted-foreground">Pris</th>
                <th className="p-3 text-left font-medium text-muted-foreground">Moms</th>
                <th className="p-3 text-left font-medium text-muted-foreground">Konto</th>
                <th className="p-3 text-right font-medium text-muted-foreground">Total</th>
              </tr>
            </thead>
            <tbody>
              {draft.rows.map((row: any) => (
                <tr key={row.id} className="border-b last:border-0">
                  <td className="p-3">
                    <div>{row.description}</div>
                    {row.source_note && <div className="text-xs text-muted-foreground">{row.source_note}</div>}
                  </td>
                  <td className="p-3 text-right font-mono">{row.quantity}</td>
                  <td className="p-3 text-right font-mono">{formatCurrency(row.unit_price)}</td>
                  <td className="p-3">{row.vat_code}</td>
                  <td className="p-3 font-mono">{row.revenue_account}</td>
                  <td className="p-3 text-right font-mono font-medium">{formatCurrency(row.amount_inc_vat)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      {canApprove && (
        <div className="flex flex-wrap gap-2">
          <Button onClick={approve} disabled={!!working} className="gap-2">
            <CheckCircle2 className="h-4 w-4" />
            {working === "approve" ? "Bokför..." : "Godkänn och bokför"}
          </Button>
          <Button variant="outline" onClick={reject} disabled={!!working} className="gap-2">
            <XCircle className="h-4 w-4" />
            {working === "reject" ? "Avvisar..." : "Avvisa"}
          </Button>
        </div>
      )}
    </div>
  );
}
