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

  const revenues = data?.revenues || data?.revenue_accounts || [];
  const expenses = data?.expenses || data?.expense_accounts || [];
  const totalRevenue = data?.total_revenue || revenues.reduce((s: number, r: any) => s + (r.balance || r.amount || 0), 0);
  const totalExpense = data?.total_expenses || expenses.reduce((s: number, e: any) => s + Math.abs(e.balance || e.amount || 0), 0);
  const result = data?.net_income ?? totalRevenue - totalExpense;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-primary" />
          Resultaträkning
        </CardTitle>
        <CardDescription>Intäkter och kostnader</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          {/* Revenue */}
          <div>
            <h3 className="font-semibold text-emerald-600 dark:text-emerald-400 mb-3 flex items-center gap-2">
              <TrendingUp className="h-4 w-4" /> Intäkter
            </h3>
            {revenues.length > 0 ? (
              <div className="space-y-1">
                {revenues.map((r: any, i: number) => (
                  <div key={i} className="flex justify-between py-1.5 px-2 hover:bg-muted/30 rounded">
                    <span className="text-sm">
                      <span className="font-mono text-muted-foreground mr-2">{r.account_code || r.code}</span>
                      {r.account_name || r.name}
                    </span>
                    <span className="font-mono text-sm">{formatCurrency(Math.abs(r.balance || r.amount || 0))}</span>
                  </div>
                ))}
                <div className="flex justify-between py-2 px-2 border-t font-semibold">
                  <span>Summa intäkter</span>
                  <span className="font-mono text-emerald-600">{formatCurrency(totalRevenue)}</span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Inga intäkter</p>
            )}
          </div>

          {/* Expenses */}
          <div>
            <h3 className="font-semibold text-red-600 dark:text-red-400 mb-3 flex items-center gap-2">
              <TrendingDown className="h-4 w-4" /> Kostnader
            </h3>
            {expenses.length > 0 ? (
              <div className="space-y-1">
                {expenses.map((e: any, i: number) => (
                  <div key={i} className="flex justify-between py-1.5 px-2 hover:bg-muted/30 rounded">
                    <span className="text-sm">
                      <span className="font-mono text-muted-foreground mr-2">{e.account_code || e.code}</span>
                      {e.account_name || e.name}
                    </span>
                    <span className="font-mono text-sm">{formatCurrency(Math.abs(e.balance || e.amount || 0))}</span>
                  </div>
                ))}
                <div className="flex justify-between py-2 px-2 border-t font-semibold">
                  <span>Summa kostnader</span>
                  <span className="font-mono text-red-600">{formatCurrency(totalExpense)}</span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Inga kostnader</p>
            )}
          </div>

          {/* Result */}
          <div className="border-t-2 pt-4">
            <div className="flex justify-between items-center">
              <span className="text-lg font-bold">Resultat</span>
              <span className={`text-lg font-bold font-mono ${result >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                {formatCurrency(result)}
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

  const assets = data?.assets || [];
  const liabilities = data?.liabilities || [];
  const equity = data?.equity || [];
  const totalAssets = data?.total_assets || assets.reduce((s: number, a: any) => s + (a.balance || 0), 0);
  const totalLiabilities = data?.total_liabilities || liabilities.reduce((s: number, l: any) => s + Math.abs(l.balance || 0), 0);
  const totalEquity = data?.total_equity || equity.reduce((s: number, e: any) => s + Math.abs(e.balance || 0), 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Scale className="h-5 w-5 text-primary" />
          Balansräkning
        </CardTitle>
        <CardDescription>Tillgångar, skulder och eget kapital</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Assets */}
          <div>
            <h3 className="font-semibold text-blue-600 dark:text-blue-400 mb-3">Tillgångar</h3>
            <AccountList accounts={assets} />
            <div className="flex justify-between py-2 px-2 border-t font-semibold mt-2">
              <span>Summa tillgångar</span>
              <span className="font-mono">{formatCurrency(totalAssets)}</span>
            </div>
          </div>

          {/* Liabilities + Equity */}
          <div className="space-y-6">
            <div>
              <h3 className="font-semibold text-red-600 dark:text-red-400 mb-3">Skulder</h3>
              <AccountList accounts={liabilities} />
              <div className="flex justify-between py-2 px-2 border-t font-semibold mt-2">
                <span>Summa skulder</span>
                <span className="font-mono">{formatCurrency(totalLiabilities)}</span>
              </div>
            </div>
            <div>
              <h3 className="font-semibold text-purple-600 dark:text-purple-400 mb-3">Eget kapital</h3>
              <AccountList accounts={equity} />
              <div className="flex justify-between py-2 px-2 border-t font-semibold mt-2">
                <span>Summa EK</span>
                <span className="font-mono">{formatCurrency(totalEquity)}</span>
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

  const accounts = data?.accounts || data?.rows || data || [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileSpreadsheet className="h-5 w-5 text-primary" />
          Huvudbok
        </CardTitle>
        <CardDescription>Saldon per konto</CardDescription>
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
                  <th className="text-right p-3 font-medium text-muted-foreground">Saldo</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a: any, i: number) => (
                  <tr key={i} className="border-b last:border-0 hover:bg-muted/30">
                    <td className="p-3 font-mono font-medium">{a.account_code || a.code}</td>
                    <td className="p-3">{a.account_name || a.name}</td>
                    <td className="p-3 text-right font-mono">{a.total_debit != null ? formatCurrency(a.total_debit) : "-"}</td>
                    <td className="p-3 text-right font-mono">{a.total_credit != null ? formatCurrency(a.total_credit) : "-"}</td>
                    <td className="p-3 text-right font-mono font-medium">{formatCurrency(a.balance || a.saldo || 0)}</td>
                  </tr>
                ))}
              </tbody>
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
