"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useIncomeStatement, useBalanceSheet, useTrialBalance } from "@/hooks/useData";
import { formatCurrency } from "@/lib/utils";
import { BarChart3, TrendingUp, TrendingDown, Scale, FileSpreadsheet } from "lucide-react";

type ReportTab = "income" | "balance" | "trial";

export default function ReportsPage() {
  const [tab, setTab] = useState<ReportTab>("income");

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1400px] mx-auto">
      <div>
        <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">Rapporter</h1>
        <p className="text-muted-foreground mt-1">Finansiella rapporter och sammanställningar</p>
      </div>

      {/* Tab buttons */}
      <div className="flex flex-wrap gap-2">
        {[
          { id: "income" as const, label: "Resultaträkning", icon: TrendingUp },
          { id: "balance" as const, label: "Balansräkning", icon: Scale },
          { id: "trial" as const, label: "Huvudbok", icon: FileSpreadsheet },
        ].map((t) => (
          <Button
            key={t.id}
            variant={tab === t.id ? "default" : "outline"}
            onClick={() => setTab(t.id)}
            className="gap-2"
          >
            <t.icon className="h-4 w-4" />
            {t.label}
          </Button>
        ))}
      </div>

      {tab === "income" && <IncomeStatementReport />}
      {tab === "balance" && <BalanceSheetReport />}
      {tab === "trial" && <TrialBalanceReport />}
    </div>
  );
}

function IncomeStatementReport() {
  const { data, isLoading } = useIncomeStatement();

  if (isLoading) return <ReportSkeleton />;

  const revenue = data?.revenue || 0;
  const costs = data?.costs || 0;
  const profit = data?.profit || 0;
  const period = data?.period || "";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-primary" />
          Resultaträkning
        </CardTitle>
        <CardDescription>
          {period ? `Period: ${period}` : "Intäkter och kostnader"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="flex justify-between py-3 px-4 bg-emerald-50 dark:bg-emerald-950/20 rounded-lg">
            <span className="flex items-center gap-2 font-medium">
              <TrendingUp className="h-4 w-4 text-emerald-600" /> Intäkter
            </span>
            <span className="font-mono font-semibold text-emerald-600">
              {formatCurrency(revenue)}
            </span>
          </div>

          <div className="flex justify-between py-3 px-4 bg-red-50 dark:bg-red-950/20 rounded-lg">
            <span className="flex items-center gap-2 font-medium">
              <TrendingDown className="h-4 w-4 text-red-600" /> Kostnader
            </span>
            <span className="font-mono font-semibold text-red-600">
              {formatCurrency(costs)}
            </span>
          </div>

          <div className="border-t-2 pt-4">
            <div className="flex justify-between items-center">
              <span className="text-lg font-bold">Resultat</span>
              <span className={`text-lg font-bold font-mono ${profit >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                {formatCurrency(profit)}
              </span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function BalanceSheetReport() {
  const { data, isLoading } = useBalanceSheet();

  if (isLoading) return <ReportSkeleton />;

  const currentAssets = data?.current_assets || 0;
  const fixedAssets = data?.fixed_assets || 0;
  const totalAssets = data?.total_assets || 0;
  const currentLiabilities = data?.current_liabilities || 0;
  const longTermLiabilities = data?.long_term_liabilities || 0;
  const equityAmount = data?.equity || 0;
  const totalLiabilities = data?.total_liabilities || 0;
  const period = data?.period || "";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Scale className="h-5 w-5 text-primary" />
          Balansräkning
        </CardTitle>
        <CardDescription>
          {period ? `Period: ${period}` : "Tillgångar, skulder och eget kapital"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Assets */}
          <div className="space-y-3">
            <h3 className="font-semibold text-blue-600 dark:text-blue-400">Tillgångar</h3>
            <div className="space-y-2">
              <div className="flex justify-between py-2 px-3 bg-muted/30 rounded">
                <span className="text-sm">Omsättningstillgångar</span>
                <span className="font-mono text-sm">{formatCurrency(currentAssets)}</span>
              </div>
              <div className="flex justify-between py-2 px-3 bg-muted/30 rounded">
                <span className="text-sm">Anläggningstillgångar</span>
                <span className="font-mono text-sm">{formatCurrency(fixedAssets)}</span>
              </div>
            </div>
            <div className="flex justify-between py-2 px-3 border-t font-semibold">
              <span>Summa tillgångar</span>
              <span className="font-mono text-blue-600">{formatCurrency(totalAssets)}</span>
            </div>
          </div>

          {/* Liabilities + Equity */}
          <div className="space-y-6">
            <div className="space-y-3">
              <h3 className="font-semibold text-red-600 dark:text-red-400">Skulder</h3>
              <div className="space-y-2">
                <div className="flex justify-between py-2 px-3 bg-muted/30 rounded">
                  <span className="text-sm">Kortfristiga skulder</span>
                  <span className="font-mono text-sm">{formatCurrency(currentLiabilities)}</span>
                </div>
                <div className="flex justify-between py-2 px-3 bg-muted/30 rounded">
                  <span className="text-sm">Långfristiga skulder</span>
                  <span className="font-mono text-sm">{formatCurrency(longTermLiabilities)}</span>
                </div>
              </div>
              <div className="flex justify-between py-2 px-3 border-t font-semibold">
                <span>Summa skulder</span>
                <span className="font-mono text-red-600">{formatCurrency(totalLiabilities)}</span>
              </div>
            </div>
            <div className="space-y-3">
              <h3 className="font-semibold text-purple-600 dark:text-purple-400">Eget kapital</h3>
              <div className="flex justify-between py-2 px-3 border-t font-semibold">
                <span>Summa EK</span>
                <span className="font-mono text-purple-600">{formatCurrency(equityAmount)}</span>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function TrialBalanceReport() {
  const { data, isLoading } = useTrialBalance();

  if (isLoading) return <ReportSkeleton />;

  const accounts = data?.accounts || [];
  const totalDebit = data?.total_debit || 0;
  const totalCredit = data?.total_credit || 0;
  const balanced = data?.balanced ?? true;
  const period = data?.period || "";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileSpreadsheet className="h-5 w-5 text-primary" />
          Huvudbok
          {!balanced && (
            <Badge variant="destructive" className="ml-2">Obalanserad</Badge>
          )}
        </CardTitle>
        <CardDescription>
          {period ? `Period: ${period} - ` : ""}Saldon per konto
        </CardDescription>
      </CardHeader>
      <CardContent>
        {Array.isArray(accounts) && accounts.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-left p-3 font-medium text-muted-foreground">Konto</th>
                  <th className="text-left p-3 font-medium text-muted-foreground">Namn</th>
                  <th className="text-right p-3 font-medium text-muted-foreground">Debet</th>
                  <th className="text-right p-3 font-medium text-muted-foreground">Kredit</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a: any, i: number) => (
                  <tr key={i} className="border-b last:border-0 hover:bg-muted/30">
                    <td className="p-3 font-mono font-medium">{a.code}</td>
                    <td className="p-3">{a.name}</td>
                    <td className="p-3 text-right font-mono">{a.debit ? formatCurrency(a.debit) : "-"}</td>
                    <td className="p-3 text-right font-mono">{a.credit ? formatCurrency(a.credit) : "-"}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 font-bold">
                  <td className="p-3" colSpan={2}>Summa</td>
                  <td className="p-3 text-right font-mono">{formatCurrency(totalDebit)}</td>
                  <td className="p-3 text-right font-mono">{formatCurrency(totalCredit)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        ) : (
          <p className="text-muted-foreground text-center py-8">Ingen data tillgänglig</p>
        )}
      </CardContent>
    </Card>
  );
}

function AccountList({ accounts }: { accounts: any[] }) {
  if (!accounts || accounts.length === 0) {
    return <p className="text-sm text-muted-foreground">Inga poster</p>;
  }
  return (
    <div className="space-y-1">
      {accounts.map((a: any, i: number) => (
        <div key={i} className="flex justify-between py-1.5 px-2 hover:bg-muted/30 rounded text-sm">
          <span>
            <span className="font-mono text-muted-foreground mr-2">{a.account_code || a.code}</span>
            {a.account_name || a.name}
          </span>
          <span className="font-mono">{formatCurrency(Math.abs(a.balance || 0))}</span>
        </div>
      ))}
    </div>
  );
}

function ReportSkeleton() {
  return (
    <Card>
      <CardContent className="p-6 space-y-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-1/2" />
      </CardContent>
    </Card>
  );
}
