"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useVoucher } from "@/hooks/useData";
import { formatCurrency, formatDate } from "@/lib/utils";
import { ArrowLeft, FileText, Calendar, Hash, Brain } from "lucide-react";

export default function VoucherDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: voucher, isLoading } = useVoucher(id);

  if (isLoading) {
    return (
      <div className="p-4 lg:p-8 space-y-6 max-w-[1000px] mx-auto">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!voucher) {
    return (
      <div className="p-4 lg:p-8 max-w-[1000px] mx-auto">
        <p className="text-muted-foreground">Verifikationen hittades inte.</p>
        <Link href="/vouchers" className="text-primary hover:underline mt-2 inline-block">
          Tillbaka till verifikationer
        </Link>
      </div>
    );
  }

  const totalDebit = voucher.rows?.reduce(
    (s: number, r: any) => s + (r.debit || 0),
    0
  );
  const totalCredit = voucher.rows?.reduce(
    (s: number, r: any) => s + (r.credit || 0),
    0
  );
  const isBalanced = Math.abs((totalDebit || 0) - (totalCredit || 0)) < 0.01;

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1000px] mx-auto">
      {/* Back link */}
      <Link
        href="/vouchers"
        className="text-sm text-muted-foreground hover:text-foreground flex items-center gap-1 w-fit"
      >
        <ArrowLeft className="h-4 w-4" /> Tillbaka
      </Link>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">
              Verifikation {voucher.series || "A"}
              {voucher.number}
            </h1>
            <Badge
              variant={
                voucher.status === "posted"
                  ? "success"
                  : voucher.status === "draft"
                  ? "warning"
                  : "secondary"
              }
            >
              {voucher.status === "draft"
                ? "Utkast"
                : voucher.status === "posted"
                ? "Bokförd"
                : voucher.status}
            </Badge>
          </div>
          <p className="text-muted-foreground mt-1">{voucher.description}</p>
        </div>
        {voucher.created_by === "ai" && (
          <Badge variant="secondary" className="gap-1 w-fit">
            <Brain className="h-3 w-3" /> AI-genererad
          </Badge>
        )}
      </div>

      {/* Meta info */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <Calendar className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Datum</p>
              <p className="font-medium">{formatDate(voucher.date)}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <Hash className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Nummer</p>
              <p className="font-medium">
                {voucher.series || "A"}
                {voucher.number}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <FileText className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Rader</p>
              <p className="font-medium">{voucher.rows?.length || 0}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div
              className={`h-2.5 w-2.5 rounded-full ${
                isBalanced ? "bg-emerald-500" : "bg-red-500"
              }`}
            />
            <div>
              <p className="text-xs text-muted-foreground">Balans</p>
              <p className="font-medium">
                {isBalanced ? "I balans" : "Obalanserad"}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Rows table */}
      <Card>
        <CardHeader>
          <CardTitle>Konteringsrader</CardTitle>
          <CardDescription>
            Debet och kredit per konto
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-left p-3 font-medium text-muted-foreground">
                    Konto
                  </th>
                  <th className="text-left p-3 font-medium text-muted-foreground">
                    Kontonamn
                  </th>
                  <th className="text-right p-3 font-medium text-muted-foreground">
                    Debet
                  </th>
                  <th className="text-right p-3 font-medium text-muted-foreground">
                    Kredit
                  </th>
                </tr>
              </thead>
              <tbody>
                {voucher.rows?.map((row: any, i: number) => (
                  <tr
                    key={i}
                    className="border-b last:border-0 hover:bg-muted/30"
                  >
                    <td className="p-3 font-mono font-medium">
                      {row.account_code}
                    </td>
                    <td className="p-3 text-muted-foreground">
                      {row.account_name || "-"}
                    </td>
                    <td className="p-3 text-right font-mono">
                      {row.debit ? formatCurrency(row.debit) : "-"}
                    </td>
                    <td className="p-3 text-right font-mono">
                      {row.credit ? formatCurrency(row.credit) : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 font-bold">
                  <td className="p-3" colSpan={2}>
                    Summa
                  </td>
                  <td className="p-3 text-right font-mono">
                    {formatCurrency(totalDebit || 0)}
                  </td>
                  <td className="p-3 text-right font-mono">
                    {formatCurrency(totalCredit || 0)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Created info */}
      {voucher.created_at && (
        <p className="text-xs text-muted-foreground text-right">
          Skapad: {formatDate(voucher.created_at)}
        </p>
      )}
    </div>
  );
}
