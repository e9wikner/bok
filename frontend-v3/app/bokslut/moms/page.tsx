"use client";

import { useState } from "react";
import { Calendar, Download, FileText } from "lucide-react";
import { api } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { useReportOptions, useYearlyVatDeclaration } from "@/hooks/useData";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function VatDeclarationPage() {
  const { data: reportOptions } = useReportOptions();
  const availableYears: number[] = reportOptions?.years || [new Date().getFullYear()];
  const [year, setYear] = useState<number>(availableYears[0] || new Date().getFullYear());
  const [exporting, setExporting] = useState<"pdf" | "eskd" | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const { data, isLoading } = useYearlyVatDeclaration(year);

  const downloadResponseBlob = (response: any, fallbackFilename: string) => {
    const blob = new Blob([response.data], { type: response.headers["content-type"] || "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = response.headers["content-disposition"]?.split("filename=")[1]?.replace(/"/g, "") || fallbackFilename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExport = async (format: "pdf" | "eskd") => {
    setExporting(format);
    setErrorMessage(null);
    try {
      if (format === "eskd") {
        const response = await api.exportVatEskd(year);
        downloadResponseBlob(response, `Moms-${year}12.eskd`);
      } else {
        const blob = await api.exportVatPdf(year);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `momsdeklaration-${year}12.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      }
      setSuccessMessage(format === "eskd" ? "ESKD-fil har laddats ner" : "Momsdeklaration PDF har laddats ner");
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      setErrorMessage(err?.response?.data?.detail || "Kunde inte exportera momsdeklaration.");
    } finally {
      setExporting(null);
    }
  };

  const boxes = data?.boxes || [];
  const summary = data?.summary || {};
  const company = data?.company || {};

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 lg:p-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight lg:text-3xl">Momsdeklaration</h1>
        <p className="mt-1 text-muted-foreground">Bokslutsunderlag och export till Skatteverkets ESKD-format.</p>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col flex-wrap items-start gap-4 sm:flex-row sm:items-center">
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Räkenskapsår:</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {availableYears.map((availableYear) => (
                <Button
                  key={availableYear}
                  variant={year === availableYear ? "default" : "outline"}
                  size="sm"
                  onClick={() => setYear(availableYear)}
                >
                  {availableYear}
                </Button>
              ))}
            </div>
            <div className="ml-auto flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleExport("pdf")}
                disabled={!!exporting}
                className="gap-2"
              >
                <Download className="h-4 w-4" />
                {exporting === "pdf" ? "Exporterar..." : "Exportera PDF"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleExport("eskd")}
                disabled={!!exporting}
                className="gap-2"
              >
                <FileText className="h-4 w-4" />
                {exporting === "eskd" ? "Exporterar..." : "Exportera ESKD"}
              </Button>
            </div>
          </div>
          {errorMessage && <p className="mt-2 px-1 text-sm text-red-600 dark:text-red-400">{errorMessage}</p>}
          {successMessage && <p className="mt-2 px-1 text-sm text-green-600 dark:text-green-400">{successMessage}</p>}
        </CardContent>
      </Card>

      {isLoading ? (
        <ReportSkeleton />
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Card>
              <CardContent className="p-4">
                <p className="text-sm text-muted-foreground">Moms att betala</p>
                <p className="font-mono text-2xl font-bold">{formatCurrency((summary.net_vat_sek || 0) * 100)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <p className="text-sm text-muted-foreground">Utgående moms</p>
                <p className="font-mono text-2xl font-bold">{formatCurrency((summary.total_output_vat_sek || 0) * 100)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <p className="text-sm text-muted-foreground">Ingående moms</p>
                <p className="font-mono text-2xl font-bold">{formatCurrency((summary.total_input_vat_sek || 0) * 100)}</p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-primary" />
                Momsdeklaration {data?.period || year}
              </CardTitle>
              <CardDescription>
                {company.name} {company.org_number ? `· ${company.org_number}` : ""}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="w-20 p-3 text-left font-medium text-muted-foreground">Ruta</th>
                      <th className="p-3 text-left font-medium text-muted-foreground">Benämning</th>
                      <th className="p-3 text-left font-medium text-muted-foreground">Underlag</th>
                      <th className="w-40 p-3 text-right font-medium text-muted-foreground">Belopp</th>
                    </tr>
                  </thead>
                  <tbody>
                    {boxes.map((box: any) => (
                      <tr key={box.box} className="border-b align-top last:border-0">
                        <td className="p-3 font-mono text-muted-foreground">{box.box}</td>
                        <td className="p-3">{box.label}</td>
                        <td className="p-3 text-muted-foreground">
                          {box.sources?.length ? (
                            <div className="space-y-1">
                              {box.sources.map((source: any) => (
                                <div key={`${box.box}-${source.account_code}`} className="flex gap-3">
                                  <span className="font-mono">{source.account_code}</span>
                                  <span>{source.account_name}</span>
                                  <span className="ml-auto font-mono">{formatCurrency((source.amount_sek || 0) * 100)}</span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <span>Inget saldo</span>
                          )}
                        </td>
                        <td className="p-3 text-right font-mono font-medium">{formatCurrency((box.amount_sek || 0) * 100)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

function ReportSkeleton() {
  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-full" />
      </CardContent>
    </Card>
  );
}
