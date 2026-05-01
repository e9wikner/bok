"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, Building2, Calculator, Calendar, CheckCircle2, Download, FileSpreadsheet, FileText } from "lucide-react";
import { api } from "@/lib/api";
import { useFiscalYears } from "@/hooks/useData";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

type TabType = "ink2" | "ink2r" | "ink2s";

interface SourceAccountValue {
  account: string;
  name?: string;
  value: number;
}

interface DeclarationRow {
  code: string;
  label: string;
  sru_fields: string[];
  value?: number | null;
  sign?: "+" | "-" | "(+) =" | "(-) =" | null;
  note?: string | null;
  source_accounts: SourceAccountValue[];
}

interface DeclarationSection {
  title: string;
  rows: DeclarationRow[];
}

interface DeclarationTab {
  id: TabType;
  label: string;
  description: string;
}

interface INK2Declaration {
  fiscal_year_id: string;
  company: {
    name: string;
    org_number: string;
  };
  fiscal_year: {
    start: string;
    end: string;
  };
  tabs: DeclarationTab[];
  summary: {
    accounting_result: number;
    taxable_result: number;
    blankettstruktur: string;
  };
  sections: Record<TabType, DeclarationSection[]>;
  validation?: {
    errors: string[];
    warnings: string[];
    is_valid: boolean;
  };
}

const TAB_ICONS = {
  ink2: FileText,
  ink2r: FileSpreadsheet,
  ink2s: Calculator,
};

const TAB_INTROS: Record<TabType, { title: string; description: string }> = {
  ink2: {
    title: "INK2 - Huvudblankett",
    description: "Underlag och summeringar enligt huvudblanketten.",
  },
  ink2r: {
    title: "INK2R - Räkenskapsschema",
    description: "Balansräkning och resultaträkning med Skatteverkets fältnummer 2.1-3.27.",
  },
  ink2s: {
    title: "INK2S - Skattemässiga justeringar",
    description: "Fält 4.1-4.21 enligt blanketten. Tomma justeringsfält visas för att rapporten ska följa blankettens struktur.",
  },
};

export default function Ink2Page() {
  const [activeTab, setActiveTab] = useState<TabType>("ink2");
  const [selectedYear, setSelectedYear] = useState<string>("");
  const [declaration, setDeclaration] = useState<INK2Declaration | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const { data: fiscalYearsData } = useFiscalYears();

  const fiscalYears = useMemo(
    () => (Array.isArray(fiscalYearsData) ? fiscalYearsData : fiscalYearsData?.fiscal_years || []),
    [fiscalYearsData],
  );

  useEffect(() => {
    if (fiscalYears.length > 0 && !selectedYear) {
      setSelectedYear(fiscalYears[0].id);
    }
  }, [fiscalYears, selectedYear]);

  const loadDeclaration = useCallback(async (fiscalYearId: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.getINK2Declaration(fiscalYearId);
      setDeclaration(response);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Kunde inte ladda INK2-data");
      setDeclaration(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedYear) return;
    loadDeclaration(selectedYear);
  }, [loadDeclaration, selectedYear]);

  const handleExport = async () => {
    if (!selectedYear) return;
    setExporting(true);
    setError(null);
    try {
      const response = await api.exportSRU(selectedYear);
      const blob = new Blob([response.data], { type: "application/zip" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const year = declaration?.fiscal_year?.start ? declaration.fiscal_year.start.substring(0, 4) : "INK2";
      a.download = `INK2_${year}_SRU.zip`;
      a.click();
      URL.revokeObjectURL(url);
      setSuccess("SRU-filer nedladdade");
      setTimeout(() => setSuccess(null), 3000);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Export misslyckades");
    } finally {
      setExporting(false);
    }
  };

  const formatAmount = (value?: number | null, options?: { showSign?: boolean }): string => {
    if (!value) return "";
    const sign = options?.showSign ? (value < 0 ? "-" : "+") : "";
    return sign + new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(Math.abs(Math.round(value))) + " kr";
  };

  const formatDate = (dateStr: string): string => {
    if (!dateStr || dateStr.length !== 8) return dateStr;
    return `${dateStr.substring(0, 4)}-${dateStr.substring(4, 6)}-${dateStr.substring(6, 8)}`;
  };

  const renderDeclarationSection = (section: DeclarationSection) => (
    <section key={section.title} className="overflow-hidden rounded-lg border border-border bg-background">
      <div className="border-b border-border bg-muted/70 px-4 py-3">
        <h3 className="text-sm font-semibold text-foreground sm:text-base">{section.title}</h3>
      </div>
      <div>
        {section.rows.map((row, index) => {
          const hasValue = !!row.value;
          const accounts = row.source_accounts || [];
          return (
            <div
              key={`${section.title}-${row.code}-${index}`}
              className={`grid grid-cols-[3.25rem_minmax(0,1fr)] gap-3 border-b border-border/50 px-4 py-3 last:border-b-0 sm:grid-cols-[3.25rem_minmax(0,1fr)_8.5rem] ${
                hasValue ? "bg-primary/5" : ""
              }`}
            >
              <div className="font-mono text-sm font-semibold leading-6 text-muted-foreground">{row.code}</div>
              <div className="min-w-0">
                <div className="text-sm leading-6 text-foreground">{row.label}</div>
                {accounts.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {accounts.map((account) => (
                      <span
                        key={`${row.code}-${account.account}`}
                        className="inline-flex items-center gap-1 rounded border border-border bg-muted/60 px-1.5 py-0.5 font-mono text-[11px] leading-4 text-muted-foreground"
                        title={account.name}
                      >
                        <span>{account.account}</span>
                        <span className={account.value < 0 ? "text-destructive" : "text-emerald-600"}>
                          {formatAmount(account.value, { showSign: true })}
                        </span>
                      </span>
                    ))}
                  </div>
                )}
                {row.note && <div className="mt-1 text-xs text-muted-foreground">{row.note}</div>}
              </div>
              <div className="col-span-2 flex items-center justify-between gap-2 sm:col-span-1 sm:block sm:text-right">
                {row.sign && <span className="font-mono text-xs text-muted-foreground sm:block">{row.sign}</span>}
                <span className={`font-mono text-sm tabular-nums ${hasValue ? "font-semibold text-foreground" : "text-muted-foreground"}`}>
                  {formatAmount(row.value)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );

  const renderDeclarationSections = (sections: DeclarationSection[]) => (
    <div className="grid gap-4 xl:grid-cols-2">
      {sections.map(renderDeclarationSection)}
    </div>
  );

  const renderSummaryCard = () => (
    <Card className="border-primary/20 bg-primary/5">
      <CardContent className="grid gap-4 p-4 md:grid-cols-3">
        <div>
          <div className="text-xs text-muted-foreground">Bokfört resultat</div>
          <div className="font-mono text-lg font-semibold">{formatAmount(declaration?.summary.accounting_result)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Skattemässigt resultat</div>
          <div className="font-mono text-lg font-semibold">{formatAmount(declaration?.summary.taxable_result)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Blankettstruktur</div>
          <div className="text-sm font-medium">{declaration?.summary.blankettstruktur}</div>
        </div>
      </CardContent>
    </Card>
  );

  const renderActiveTab = () => {
    if (!declaration) return null;
    const intro = TAB_INTROS[activeTab];
    return (
      <div className="space-y-4">
        {activeTab === "ink2" && renderSummaryCard()}
        {activeTab !== "ink2" && (
          <Card>
            <CardHeader>
              <CardTitle>{intro.title}</CardTitle>
              <CardDescription>{intro.description}</CardDescription>
            </CardHeader>
          </Card>
        )}
        {renderDeclarationSections(declaration.sections?.[activeTab] || [])}
      </div>
    );
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Inkomstdeklaration 2</h1>
          <p className="text-sm text-muted-foreground">
            Webbaserad rapport med samma fält, rubriker och indelning som Skatteverkets INK2-blankett.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {fiscalYears.length > 0 && (
            <div className="flex items-center gap-2 rounded-lg border bg-background px-3 py-2 shadow-sm">
              <Calendar className="h-4 w-4 text-muted-foreground" />
              <select
                value={selectedYear}
                onChange={(event) => setSelectedYear(event.target.value)}
                className="bg-transparent text-sm font-medium text-foreground focus:outline-none"
              >
                {fiscalYears.map((fy: any) => (
                  <option key={fy.id} value={fy.id}>
                    Räkenskapsår {new Date(fy.start_date).getFullYear()}
                  </option>
                ))}
              </select>
            </div>
          )}
          <Button onClick={handleExport} disabled={!declaration || exporting} className="gap-2">
            <Download className="h-4 w-4" />
            {exporting ? "Exporterar..." : "Ladda ner SRU"}
          </Button>
        </div>
      </div>

      {declaration && (
        <Card className="border-primary/20 bg-gradient-to-r from-primary/10 to-primary/5">
          <CardContent className="p-4">
            <div className="flex flex-wrap items-center gap-6 text-sm">
              <div className="flex items-center gap-2">
                <Building2 className="h-5 w-5 text-primary" />
                <div>
                  <span className="block text-xs text-muted-foreground">Företag</span>
                  <span className="font-semibold text-foreground">{declaration.company?.name || "Företagsnamn saknas"}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-primary" />
                <div>
                  <span className="block text-xs text-muted-foreground">Organisationsnummer</span>
                  <span className="font-mono text-foreground">{declaration.company?.org_number || "-"}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Calendar className="h-5 w-5 text-primary" />
                <div>
                  <span className="block text-xs text-muted-foreground">Räkenskapsår</span>
                  <span className="text-foreground">
                    {declaration.fiscal_year?.start && declaration.fiscal_year?.end
                      ? `${formatDate(declaration.fiscal_year.start)} - ${formatDate(declaration.fiscal_year.end)}`
                      : "-"}
                  </span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/10 px-4 py-3 text-destructive">
          <AlertCircle className="h-5 w-5" />
          {error}
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 rounded-lg border border-green-500/20 bg-green-500/10 px-4 py-3 text-green-600">
          <CheckCircle2 className="h-5 w-5" />
          {success}
        </div>
      )}

      {declaration?.validation?.warnings && declaration.validation.warnings.length > 0 && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-4">
          <h4 className="mb-2 font-semibold text-amber-600">Varningar</h4>
          <ul className="space-y-1 text-sm text-amber-700">
            {declaration.validation.warnings.map((warning, idx) => (
              <li key={idx}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      {declaration && (
        <div className="border-b border-border">
          <nav className="flex space-x-1 overflow-x-auto" aria-label="Tabs">
            {declaration.tabs.map((tab) => {
              const Icon = TAB_ICONS[tab.id] || FileText;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
                    activeTab === tab.id
                      ? "border-primary bg-primary/5 text-primary"
                      : "border-transparent text-muted-foreground hover:border-border hover:text-foreground"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  <span>{tab.label}</span>
                  <span className="hidden text-xs text-muted-foreground sm:inline">({tab.description})</span>
                </button>
              );
            })}
          </nav>
        </div>
      )}

      {loading && (
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <div className="grid gap-4 md:grid-cols-2">
            <Skeleton className="h-96" />
            <Skeleton className="h-96" />
          </div>
        </div>
      )}

      {!loading && renderActiveTab()}
    </div>
  );
}
