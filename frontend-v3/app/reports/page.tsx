"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useIncomeStatement, useBalanceSheet, useTrialBalance, useGeneralLedger, useFiscalYears, useAccounts } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { TrendingUp, TrendingDown, Scale, FileSpreadsheet, BookOpen, Calendar, Download } from "lucide-react";

type ReportTab = "income" | "balance" | "trial" | "ledger";

const MONTHS = [
  { value: 0, label: "Hela året" },
  { value: 1, label: "Januari" },
  { value: 2, label: "Februari" },
  { value: 3, label: "Mars" },
  { value: 4, label: "April" },
  { value: 5, label: "Maj" },
  { value: 6, label: "Juni" },
  { value: 7, label: "Juli" },
  { value: 8, label: "Augusti" },
  { value: 9, label: "September" },
  { value: 10, label: "Oktober" },
  { value: 11, label: "November" },
  { value: 12, label: "December" },
];

export default function ReportsPage() {
  const [tab, setTab] = useState<ReportTab>("income");
  const [year, setYear] = useState<number>(new Date().getFullYear());
  const [month, setMonth] = useState<number>(0);
  const { data: fyData } = useFiscalYears();
  const [exporting, setExporting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Auto-clear error after 5 seconds
  useEffect(() => {
    if (!errorMessage) return;
    const timer = setTimeout(() => setErrorMessage(null), 5000);
    return () => clearTimeout(timer);
  }, [errorMessage]);

  const showError = useCallback((msg: string) => {
    console.error(msg);
    setErrorMessage(msg);
  }, []);

  // PDF export helper
  const handlePdfExport = async () => {
    setExporting(true);
    setErrorMessage(null);
    try {
      const periodsData = await api.getPeriods();
      const periods: any[] = periodsData?.periods || periodsData || [];

      if (periods.length === 0) {
        showError("Inga perioder hittades. Kontrollera att räkenskapsår är konfigurerade.");
        return;
      }

      // Find matching period
      let matchedPeriod;
      if (month) {
        matchedPeriod = periods.find((p: any) => {
          const start = new Date(p.start_date);
          return start.getFullYear() === year && start.getMonth() + 1 === month;
        });
      } else {
        matchedPeriod = periods.find((p: any) => new Date(p.start_date).getFullYear() === year);
      }

      if (!matchedPeriod) {
        const periodLabel = month
          ? `${MONTHS.find((m) => m.value === month)?.label || month} ${year}`
          : `${year}`;
        showError(`Ingen period hittad för ${periodLabel}. Kontrollera att perioden finns.`);
        return;
      }

      const periodId = matchedPeriod.id;

      const pdfEndpoint = tab === "income"
        ? `/api/v1/export/pdf/income-statement/${periodId}`
        : tab === "balance"
        ? `/api/v1/export/pdf/balance-sheet/${periodId}`
        : `/api/v1/export/pdf/trial-balance/${periodId}`;

      // Try PDF endpoint first, fall back to HTML
      const htmlEndpoint = pdfEndpoint.replace(/\/([^/]+)$/, "/$1/html");

      try {
        const blob = await api.getPdfExport(pdfEndpoint);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${tab}-${year}${month ? `-${String(month).padStart(2, "0")}` : ""}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      } catch {
        // Fallback: open HTML version in new tab
        window.open(
          `${process.env.NEXT_PUBLIC_API_URL || ""}${htmlEndpoint}`,
          "_blank"
        );
      }
    } catch {
      showError("Kunde inte exportera PDF. Försök igen senare.");
    } finally {
      setExporting(false);
    }
  };

  // Extract available years from fiscal years
  const fiscalYears = fyData?.fiscal_years || [];
  const availableYears: number[] = [];
  for (const fy of fiscalYears) {
    const startYear = new Date(fy.start_date).getFullYear();
    const endYear = new Date(fy.end_date).getFullYear();
    if (!availableYears.includes(startYear)) availableYears.push(startYear);
    if (!availableYears.includes(endYear)) availableYears.push(endYear);
  }
  if (availableYears.length === 0) {
    availableYears.push(new Date().getFullYear());
  }
  availableYears.sort((a, b) => b - a);

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
          { id: "ledger" as const, label: "Huvudbok", icon: BookOpen },
          { id: "trial" as const, label: "Råbalans", icon: FileSpreadsheet },
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

      {/* Year/Month selector */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Period:</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {availableYears.map((y) => (
                <Button
                  key={y}
                  variant={year === y ? "default" : "outline"}
                  size="sm"
                  onClick={() => setYear(y)}
                >
                  {y}
                </Button>
              ))}
            </div>
            {tab !== "balance" && (
              <div className="flex items-center gap-2">
                <select
                  value={month}
                  onChange={(e) => setMonth(Number(e.target.value))}
                  className="rounded-lg border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  {MONTHS.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {tab !== "ledger" && (
              <Button
                variant="outline"
                size="sm"
                onClick={handlePdfExport}
                disabled={exporting}
                className="gap-2 ml-auto"
              >
                <Download className="h-4 w-4" />
                {exporting ? "Exporterar..." : "Exportera PDF"}
              </Button>
            )}
          </div>
          {errorMessage && (
            <p className="text-sm text-red-600 dark:text-red-400 mt-2 px-1">{errorMessage}</p>
          )}
        </CardContent>
      </Card>

      {tab === "income" && (
        <IncomeStatementReport year={year} month={month || undefined} />
      )}
      {tab === "balance" && <BalanceSheetReport year={year} />}
      {tab === "ledger" && (
        <GeneralLedgerReport year={year} month={month || undefined} />
      )}
      {tab === "trial" && (
        <TrialBalanceReport year={year} period={month || undefined} />
      )}
    </div>
  );
}

function IncomeStatementReport({ year, month }: { year: number; month?: number }) {
  const { data, isLoading } = useIncomeStatement(year, month);

  if (isLoading) return <ReportSkeleton />;

  const revenue = data?.revenue || 0;
  const costs = data?.costs || 0;
  const financial = data?.financial || 0;
  const operatingProfit = data?.operating_profit || 0;
  const profit = data?.profit || 0;
  const revenueDetails: any[] = data?.revenue_details || [];
  const costDetails: any[] = data?.cost_details || [];
  const financialDetails: any[] = data?.financial_details || [];
  const period = data?.period || "";

  // Group costs by K2 categories
  const materialCosts = costDetails.filter((d: any) => d.code >= "4000" && d.code <= "4999");
  const externalCosts = costDetails.filter((d: any) => d.code >= "5000" && d.code <= "6999");
  const personnelCosts = costDetails.filter((d: any) => d.code >= "7000" && d.code <= "7699");
  const depreciations = costDetails.filter((d: any) => d.code >= "7700" && d.code <= "7999");

  const Section = ({ title, items, subtotal, bgClass, textClass }: {
    title: string; items: any[]; subtotal: number; bgClass: string; textClass: string;
  }) => (
    <div>
      <div className={`flex justify-between py-2 px-4 ${bgClass} rounded-t-lg font-medium`}>
        <span className={textClass}>{title}</span>
        <span className={`font-mono font-semibold ${textClass}`}>{formatCurrency(subtotal)}</span>
      </div>
      {items.length > 0 && (
        <div className="border-x border-b rounded-b-lg divide-y">
          {items.map((d: any) => (
            <div key={d.code} className="flex justify-between py-1.5 px-4 text-sm">
              <span className="text-muted-foreground">
                <span className="font-mono mr-2">{d.code}</span>{d.name}
              </span>
              <span className="font-mono">{formatCurrency(d.amount)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-primary" />
          Resultaträkning
        </CardTitle>
        <CardDescription>
          {period ? `Period: ${period}` : "Kostnadsslagsindelad enligt K2"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {/* Rörelseintäkter */}
          <Section title="Rörelseintäkter" items={revenueDetails} subtotal={revenue}
            bgClass="bg-emerald-50 dark:bg-emerald-950/20" textClass="text-emerald-700 dark:text-emerald-400" />

          {/* Rörelsekostnader */}
          {materialCosts.length > 0 && (
            <Section title="Råvaror och förnödenheter" items={materialCosts}
              subtotal={materialCosts.reduce((s: number, d: any) => s + d.amount, 0)}
              bgClass="bg-red-50 dark:bg-red-950/20" textClass="text-red-700 dark:text-red-400" />
          )}

          {externalCosts.length > 0 && (
            <Section title="Övriga externa kostnader" items={externalCosts}
              subtotal={externalCosts.reduce((s: number, d: any) => s + d.amount, 0)}
              bgClass="bg-red-50 dark:bg-red-950/20" textClass="text-red-700 dark:text-red-400" />
          )}

          {personnelCosts.length > 0 && (
            <Section title="Personalkostnader" items={personnelCosts}
              subtotal={personnelCosts.reduce((s: number, d: any) => s + d.amount, 0)}
              bgClass="bg-red-50 dark:bg-red-950/20" textClass="text-red-700 dark:text-red-400" />
          )}

          {depreciations.length > 0 && (
            <Section title="Avskrivningar" items={depreciations}
              subtotal={depreciations.reduce((s: number, d: any) => s + d.amount, 0)}
              bgClass="bg-red-50 dark:bg-red-950/20" textClass="text-red-700 dark:text-red-400" />
          )}

          {/* Rörelseresultat */}
          <div className="flex justify-between py-3 px-4 border-t-2 border-b font-bold">
            <span>Rörelseresultat</span>
            <span className={`font-mono ${operatingProfit >= 0 ? "text-emerald-600" : "text-red-600"}`}>
              {formatCurrency(operatingProfit)}
            </span>
          </div>

          {/* Finansiella poster */}
          {financialDetails.length > 0 && (
            <Section title="Finansiella poster" items={financialDetails} subtotal={financial}
              bgClass="bg-amber-50 dark:bg-amber-950/20" textClass="text-amber-700 dark:text-amber-400" />
          )}

          {/* Årets resultat */}
          <div className="flex justify-between py-4 px-4 border-t-2 mt-2">
            <span className="text-lg font-bold">Årets resultat</span>
            <span className={`text-lg font-bold font-mono ${profit >= 0 ? "text-emerald-600" : "text-red-600"}`}>
              {formatCurrency(profit)}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function BalanceSheetReport({ year }: { year: number }) {
  const { data, isLoading } = useBalanceSheet(year);

  if (isLoading) return <ReportSkeleton />;

  const balanced = data?.balanced ?? true;
  const hasIB = data?.has_ib_vouchers ?? false;

  // Account detail arrays from API with 3 columns
  const fixedAssetsDetails: any[] = data?.fixed_assets_details || [];
  const receivablesDetails: any[] = data?.receivables_details || [];
  const bankDetails: any[] = data?.bank_and_cash_details || [];
  const currentAssetsDetails: any[] = data?.current_assets_details || [];
  const equityDetails: any[] = data?.equity_details || [];
  const longTermDetails: any[] = data?.long_term_liabilities_details || [];
  const currentLiabDetails: any[] = data?.current_liabilities_details || [];

  // 3-column table component for account details
  const AccountTable3Col = ({ items, colorClass }: { items: any[]; colorClass: string }) => (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className={`${colorClass} text-xs`}>
            <th className="text-left p-2 font-medium">Konto</th>
            <th className="text-right p-2 font-medium w-24">IB</th>
            <th className="text-right p-2 font-medium w-24">Förändring</th>
            <th className="text-right p-2 font-medium w-24">UB</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {items.map((a: any) => (
            <tr key={a.code} className="hover:bg-muted/30">
              <td className="p-2">
                <span className="text-muted-foreground">
                  <span className="font-mono mr-2">{a.code}</span>{a.name}
                </span>
              </td>
              <td className="p-2 text-right font-mono">{formatCurrency(a.opening_balance || 0)}</td>
              <td className={`p-2 text-right font-mono ${(a.change || 0) > 0 ? 'text-emerald-600' : (a.change || 0) < 0 ? 'text-red-600' : ''}`}>
                {formatCurrency(a.change || 0)}
              </td>
              <td className="p-2 text-right font-mono font-medium">{formatCurrency(a.closing_balance || 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  // Summary row with 3 columns
  const Summary3Col = ({ opening, change, closing, label, colorClass }: {
    opening: number; change: number; closing: number; label: string; colorClass: string;
  }) => (
    <div className={`grid grid-cols-4 gap-2 py-2 px-3 ${colorClass} rounded font-medium text-sm`}>
      <span>{label}</span>
      <span className="font-mono text-right">{formatCurrency(opening)}</span>
      <span className={`font-mono text-right ${change > 0 ? 'text-emerald-700' : change < 0 ? 'text-red-700' : ''}`}>
        {formatCurrency(change)}
      </span>
      <span className="font-mono text-right">{formatCurrency(closing)}</span>
    </div>
  );

  // Section header with 3 column labels
  const SectionHeader3Col = ({ title, colorClass }: { title: string; colorClass: string }) => (
    <div className={`grid grid-cols-4 gap-2 py-2 px-3 ${colorClass} rounded-t font-medium text-sm`}>
      <span>{title}</span>
      <span className="text-right text-xs opacity-80">Ingående balans</span>
      <span className="text-right text-xs opacity-80">Förändring</span>
      <span className="text-right text-xs opacity-80">Utgående balans</span>
    </div>
  );

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Scale className="h-5 w-5 text-primary" />
              Balansräkning
              {!balanced && <Badge variant="destructive" className="ml-2">Obalanserad</Badge>}
              {!hasIB && <Badge variant="outline" className="ml-2">Saknar IB</Badge>}
            </CardTitle>
            <CardDescription>
              Balansräkning med ingående balans, förändring och utgående balans
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-8">
          {/* TILLGÅNGAR */}
          <div>
            <h3 className="font-bold text-blue-600 dark:text-blue-400 mb-3 text-lg">TILLGÅNGAR</h3>

            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">A. Anläggningstillgångar</h4>
            <SectionHeader3Col title="Materiella anläggningstillgångar" colorClass="bg-blue-50 dark:bg-blue-950/20 text-blue-700 dark:text-blue-400" />
            <div className="border-x border-b rounded-b mb-4">
              <AccountTable3Col items={fixedAssetsDetails} colorClass="bg-blue-50 dark:bg-blue-950/20 text-blue-700 dark:text-blue-400" />
            </div>
            <Summary3Col
              opening={data?.opening_fixed_assets || 0}
              change={data?.change_fixed_assets || 0}
              closing={data?.closing_fixed_assets || 0}
              label="Summa anläggningstillgångar"
              colorClass="bg-blue-100 dark:bg-blue-950/30 text-blue-800 dark:text-blue-300 text-sm"
            />

            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 mt-6">B. Omsättningstillgångar</h4>
            {currentAssetsDetails.length > 0 && (
              <>
                <SectionHeader3Col title="Övriga omsättningstillgångar" colorClass="bg-blue-50/50 dark:bg-blue-950/10 text-blue-700 dark:text-blue-400" />
                <div className="border-x border-b rounded-b mb-4">
                  <AccountTable3Col items={currentAssetsDetails} colorClass="bg-blue-50/50 dark:bg-blue-950/10 text-blue-700 dark:text-blue-400" />
                </div>
              </>
            )}
            <SectionHeader3Col title="Kundfordringar" colorClass="bg-blue-50/50 dark:bg-blue-950/10 text-blue-700 dark:text-blue-400" />
            <div className="border-x border-b rounded-b mb-4">
              <AccountTable3Col items={receivablesDetails} colorClass="bg-blue-50/50 dark:bg-blue-950/10 text-blue-700 dark:text-blue-400" />
            </div>
            <SectionHeader3Col title="Kassa och bank" colorClass="bg-blue-50/50 dark:bg-blue-950/10 text-blue-700 dark:text-blue-400" />
            <div className="border-x border-b rounded-b mb-4">
              <AccountTable3Col items={bankDetails} colorClass="bg-blue-50/50 dark:bg-blue-950/10 text-blue-700 dark:text-blue-400" />
            </div>

            <div className="grid grid-cols-4 gap-2 py-3 px-3 border-t-2 font-bold text-blue-700 dark:text-blue-400 mt-4">
              <span>SUMMA TILLGÅNGAR</span>
              <span className="font-mono text-right">{formatCurrency(data?.opening_assets || 0)}</span>
              <span className="font-mono text-right">{formatCurrency(data?.change_assets || 0)}</span>
              <span className="font-mono text-right">{formatCurrency(data?.closing_assets || 0)}</span>
            </div>
          </div>

          {/* EGET KAPITAL OCH SKULDER */}
          <div>
            <h3 className="font-bold text-purple-600 dark:text-purple-400 mb-3 text-lg">EGET KAPITAL OCH SKULDER</h3>

            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">A. Eget kapital</h4>
            <SectionHeader3Col title="Bundet och fritt eget kapital" colorClass="bg-purple-50 dark:bg-purple-950/20 text-purple-700 dark:text-purple-400" />
            <div className="border-x border-b rounded-b mb-4">
              <AccountTable3Col items={equityDetails} colorClass="bg-purple-50 dark:bg-purple-950/20 text-purple-700 dark:text-purple-400" />
            </div>
            <Summary3Col
              opening={data?.opening_equity || 0}
              change={data?.change_equity || 0}
              closing={data?.closing_equity || 0}
              label="Summa eget kapital"
              colorClass="bg-purple-100 dark:bg-purple-950/30 text-purple-800 dark:text-purple-300 text-sm"
            />

            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 mt-6">B. Långfristiga skulder</h4>
            <SectionHeader3Col title="Skulder till kreditinstitut" colorClass="bg-red-50 dark:bg-red-950/20 text-red-700 dark:text-red-400" />
            <div className="border-x border-b rounded-b mb-4">
              <AccountTable3Col items={longTermDetails} colorClass="bg-red-50 dark:bg-red-950/20 text-red-700 dark:text-red-400" />
            </div>
            <Summary3Col
              opening={data?.opening_long_term_liabilities || 0}
              change={data?.change_long_term_liabilities || 0}
              closing={data?.closing_long_term_liabilities || 0}
              label="Summa långfristiga skulder"
              colorClass="bg-red-100 dark:bg-red-950/30 text-red-800 dark:text-red-300 text-sm"
            />

            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 mt-6">C. Kortfristiga skulder</h4>
            <SectionHeader3Col title="Leverantörsskulder, moms m.m." colorClass="bg-red-50/50 dark:bg-red-950/10 text-red-700 dark:text-red-400" />
            <div className="border-x border-b rounded-b mb-4">
              <AccountTable3Col items={currentLiabDetails} colorClass="bg-red-50/50 dark:bg-red-950/10 text-red-700 dark:text-red-400" />
            </div>
            <Summary3Col
              opening={data?.opening_current_liabilities || 0}
              change={data?.change_current_liabilities || 0}
              closing={data?.closing_current_liabilities || 0}
              label="Summa kortfristiga skulder"
              colorClass="bg-red-100 dark:bg-red-950/30 text-red-800 dark:text-red-300 text-sm"
            />

            <div className="grid grid-cols-4 gap-2 py-3 px-3 border-t-2 font-bold text-purple-700 dark:text-purple-400 mt-4">
              <span>SUMMA EK OCH SKULDER</span>
              <span className="font-mono text-right">{formatCurrency(data?.opening_equity_liabilities || 0)}</span>
              <span className="font-mono text-right">{formatCurrency(data?.change_equity_liabilities || 0)}</span>
              <span className="font-mono text-right">{formatCurrency(data?.closing_equity_liabilities || 0)}</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function TrialBalanceReport({ year, period }: { year: number; period?: number }) {
  const { data, isLoading } = useTrialBalance(year, period);

  if (isLoading) return <ReportSkeleton />;

  const accounts = data?.accounts || [];
  const totalDebit = data?.total_debit || 0;
  const totalCredit = data?.total_credit || 0;
  const balanced = data?.balanced ?? true;
  const periodStr = data?.period || "";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileSpreadsheet className="h-5 w-5 text-primary" />
          Råbalans
          {!balanced && (
            <Badge variant="destructive" className="ml-2">Obalanserad</Badge>
          )}
        </CardTitle>
        <CardDescription>
          {periodStr ? `Period: ${periodStr} - ` : ""}Saldon per konto
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
          <p className="text-muted-foreground text-center py-8">Ingen data tillgänglig för vald period</p>
        )}
      </CardContent>
    </Card>
  );
}

function GeneralLedgerReport({ year, month }: { year: number; month?: number }) {
  const [selectedAccount, setSelectedAccount] = useState<string>("");
  const { data: accountsData } = useAccounts();
  const { data, isLoading } = useGeneralLedger(selectedAccount, year, month);
  const { data: trialBalanceData } = useTrialBalance(year, month || undefined);

  const allAccounts = accountsData?.accounts || [];
  // Only show accounts that have transactions in the selected period
  const activeAccountCodes = new Set((trialBalanceData?.accounts || []).map((a: any) => a.code));
  const accounts = allAccounts.filter((a: any) => activeAccountCodes.has(a.code));

  // Clear selected account if it has no transactions in the selected period
  useEffect(() => {
    if (selectedAccount && !activeAccountCodes.has(selectedAccount)) {
      setSelectedAccount("");
    }
  }, [selectedAccount, activeAccountCodes]);

  return (
    <div className="space-y-4">
      {/* Account selector */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <div className="flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Välj konto:</span>
            </div>
            <select
              value={selectedAccount}
              onChange={(e) => setSelectedAccount(e.target.value)}
              className="rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring min-w-[300px]"
            >
              <option value="">-- Välj ett konto --</option>
              {accounts.map((a: any) => (
                <option key={a.code} value={a.code}>
                  {a.code} — {a.name}
                </option>
              ))}
            </select>
          </div>
        </CardContent>
      </Card>

      {/* Ledger content */}
      {!selectedAccount ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <BookOpen className="h-12 w-12 mx-auto mb-4 opacity-30" />
            <p>Välj ett konto ovan för att visa huvudboken</p>
          </CardContent>
        </Card>
      ) : isLoading ? (
        <ReportSkeleton />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-primary" />
              Huvudbok: {data?.account_code} — {data?.account_name}
            </CardTitle>
            <CardDescription>
              {data?.transaction_count || 0} transaktioner
              {data?.period && data.period !== "all" ? ` • Period: ${data.period}` : ""}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {data?.transactions && data.transactions.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="text-left p-3 font-medium text-muted-foreground">Datum</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Ver.nr</th>
                      <th className="text-left p-3 font-medium text-muted-foreground">Beskrivning</th>
                      <th className="text-right p-3 font-medium text-muted-foreground">Debet</th>
                      <th className="text-right p-3 font-medium text-muted-foreground">Kredit</th>
                      <th className="text-right p-3 font-medium text-muted-foreground">Saldo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.transactions.map((tx: any, i: number) => (
                      <tr key={i} className="border-b last:border-0 hover:bg-muted/30">
                        <td className="p-3 text-muted-foreground">{tx.date}</td>
                        <td className="p-3">
                          <a
                            href={`/vouchers/${tx.voucher_id}`}
                            className="text-primary hover:underline font-medium"
                          >
                            {tx.voucher_number}
                          </a>
                        </td>
                        <td className="p-3">{tx.description}</td>
                        <td className="p-3 text-right font-mono">
                          {tx.debit ? formatCurrency(tx.debit) : ""}
                        </td>
                        <td className="p-3 text-right font-mono">
                          {tx.credit ? formatCurrency(tx.credit) : ""}
                        </td>
                        <td className="p-3 text-right font-mono font-medium">
                          {formatCurrency(tx.balance)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 font-bold">
                      <td className="p-3" colSpan={3}>Summa / Utgående saldo</td>
                      <td className="p-3 text-right font-mono">{formatCurrency(data.total_debit || 0)}</td>
                      <td className="p-3 text-right font-mono">{formatCurrency(data.total_credit || 0)}</td>
                      <td className="p-3 text-right font-mono text-primary">{formatCurrency(data.closing_balance || 0)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            ) : (
              <p className="text-muted-foreground text-center py-8">
                Inga transaktioner för detta konto i vald period
              </p>
            )}
          </CardContent>
        </Card>
      )}
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
