"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Bot, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useInvoiceDrafts } from "@/hooks/useData";
import { formatCurrency, formatDate } from "@/lib/utils";

const statusOptions = [
  { value: "", label: "Alla" },
  { value: "needs_review", label: "Att granska" },
  { value: "draft", label: "Utkast" },
  { value: "sent", label: "Skickade" },
  { value: "rejected", label: "Avvisade" },
];

export default function InvoiceDraftsPage() {
  const [status, setStatus] = useState("needs_review");
  const [search, setSearch] = useState("");
  const { data, isLoading } = useInvoiceDrafts(status || undefined);
  const drafts = (data?.drafts || []).filter((draft: any) => {
    const haystack = `${draft.customer_name} ${draft.reference || ""}`.toLowerCase();
    return haystack.includes(search.toLowerCase());
  });

  return (
    <div className="mx-auto max-w-[1200px] space-y-6 p-4 lg:p-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight lg:text-3xl">
            <Bot className="h-6 w-6 text-primary" />
            Fakturautkast
          </h1>
          <p className="mt-1 text-muted-foreground">Utkast skapade av agenten innan de skickas och bokförs.</p>
        </div>
        <Link href="/invoices">
          <Button variant="outline">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Till fakturor
          </Button>
        </Link>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative sm:w-80">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                className="w-full rounded-lg border bg-background py-2 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Sök kund eller referens..."
              />
            </div>
            <div className="flex flex-wrap gap-2">
              {statusOptions.map((option) => (
                <Button
                  key={option.value}
                  variant={status === option.value ? "default" : "outline"}
                  size="sm"
                  onClick={() => setStatus(option.value)}
                >
                  {option.label}
                </Button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-3 p-6">
              {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
            </div>
          ) : drafts.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">Inga fakturautkast hittades.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="p-4 text-left font-medium text-muted-foreground">Kund</th>
                    <th className="p-4 text-left font-medium text-muted-foreground">Referens</th>
                    <th className="p-4 text-left font-medium text-muted-foreground">Datum</th>
                    <th className="p-4 text-left font-medium text-muted-foreground">Status</th>
                    <th className="p-4 text-right font-medium text-muted-foreground">Rader</th>
                    <th className="p-4 text-right font-medium text-muted-foreground">Belopp</th>
                  </tr>
                </thead>
                <tbody>
                  {drafts.map((draft: any) => (
                    <tr key={draft.id} className="border-b last:border-0 hover:bg-muted/30">
                      <td className="p-4">
                        <Link href={`/invoices/drafts/${draft.id}`} className="font-medium text-primary hover:underline">
                          {draft.customer_name}
                        </Link>
                      </td>
                      <td className="p-4">{draft.reference || "-"}</td>
                      <td className="p-4">{formatDate(draft.invoice_date)}</td>
                      <td className="p-4"><Badge variant="outline">{draft.status}</Badge></td>
                      <td className="p-4 text-right font-mono">{draft.row_count}</td>
                      <td className="p-4 text-right font-mono font-semibold">{formatCurrency(draft.amount_inc_vat || 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
