"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { useFiscalYears } from "@/hooks/useData";
import { Download, FileText, AlertCircle, CheckCircle2, Calendar, Building2 } from "lucide-react";


interface SRUField {
  field_number: string;
  description: string;
  value: number;
  source_accounts: string[];
}

interface SRUData {
  fiscal_year_id: string;
  org_number: string;
  company_name: string;
  start_date: string;
  end_date: string;
  fields: Record<string, SRUField>;
}

// Fält grupperingar baserat på Skatteverkets INK2
const FIELD_GROUPS = {
  "Tillgångar": ["7251", "7252", "7261", "7263", "7281", "7284", "7285", "7286"],
  "Eget kapital och skulder": ["7301", "7302", "7321", "7350", "7365", "7368", "7369", "7370"],
  "Resultaträkning": ["7410", "7413", "7416", "7417", "7420", "7450", "7511", "7513", "7514", "7515", "7520", "7522", "7528"],
  "Övrigt": ["7011", "7012", "7670", "7650", "7651", "7653", "7654"]
};

const FIELD_DESCRIPTIONS: Record<string, string> = {
  "7011": "Räkenskapsår start",
  "7012": "Räkenskapsår slut",
  "7251": "Immateriella anläggningstillgångar",
  "7261": "Byggnader och mark",
  "7263": "Maskiner och inventarier",
  "7281": "Kortfristiga fordringar",
  "7301": "Aktiekapital",
  "7302": "Balanserad vinst/förlust",
  "7368": "Rörelseresultat",
  "7369": "Kortfristiga skulder till kreditinstitut, kunder och leverantörer",
  "7410": "Nettoomsättning",
  "7416": "Övriga rörelseintäkter",
  "7417": "Rörelseintäkter",
  "7450": "Rörelseresultat före avskrivningar",
  "7513": "Skatt på årets resultat",
  "7514": "Årets resultat",
  "7522": "Övriga externa kostnader",
  "7528": "Finansiella intäkter",
  "7550": "Summa tillgångar",
  "7650": "Förlust som minskar aktiekapitalet",
  "7651": "Vinst som tillfaller aktieägarna",
  "7653": "Återbetalning från aktieägare",
  "7654": "Återbetalning till aktieägare",
  "7670": "Skillnad mellan tillgångar och skulder/EK"
};

export default function Ink2Page() {
  const [selectedYear, setSelectedYear] = useState<string>("");
  const [sruData, setSruData] = useState<SRUData | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const { data: fiscalYears } = useFiscalYears();

  // Auto-select first fiscal year on load
  useEffect(() => {
    if (fiscalYears?.length && !selectedYear) {
      setSelectedYear(fiscalYears[0].id);
    }
  }, [fiscalYears, selectedYear]);

  // Load SRU data when year changes
  useEffect(() => {
    if (!selectedYear) return;
    loadSruData(selectedYear);
  }, [selectedYear]);

  const loadSruData = async (fiscalYearId: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.previewSRU(fiscalYearId);
      setSruData(response);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Kunde inte ladda INK2-data");
    } finally {
      setLoading(false);
    }
  };

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
      const year = sruData?.start_date ? new Date(sruData.start_date).getFullYear() : "INK2";
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

  const getFieldValue = (fieldNumber: string): number => {
    return sruData?.fields?.[fieldNumber]?.value ?? 0;
  };

  const formatField = (value: number): string => {
    if (value === 0) return "-";
    return formatCurrency(value);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">INK2 - Inkomstdeklaration 2</h1>
          <p className="text-muted-foreground">
            Årsredovisning och inkomstdeklaration för aktiebolag
          </p>
        </div>
        <div className="flex items-center gap-2">
          {fiscalYears && (
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4 text-muted-foreground" />
              <select
                value={selectedYear}
                onChange={(e) => setSelectedYear(e.target.value)}
                className="h-10 w-[180px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              >
                {fiscalYears.map((fy: any) => (
                  <option key={fy.id} value={fy.id}>
                    {new Date(fy.start_date).getFullYear()}
                  </option>
                ))}
              </select>
            </div>
          )}
          <Button 
            onClick={handleExport} 
            disabled={!sruData || exporting}
            className="gap-2"
          >
            <Download className="h-4 w-4" />
            {exporting ? "Exporterar..." : "Ladda ner SRU"}
          </Button>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="bg-destructive/10 text-destructive px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      )}
      {success && (
        <div className="bg-green-500/10 text-green-600 px-4 py-3 rounded-lg flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4" />
          {success}
        </div>
      )}

      {/* Company Info */}
      {sruData && (
        <Card className="bg-muted/50">
          <CardContent className="p-4">
            <div className="flex flex-wrap items-center gap-6 text-sm">
              <div className="flex items-center gap-2">
                <Building2 className="h-4 w-4 text-muted-foreground" />
                <span className="font-medium">{sruData.company_name || "Företagsnamn saknas"}</span>
              </div>
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <span>Org.nr: {sruData.org_number || "-"}</span>
              </div>
              <div className="flex items-center gap-2">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <span>
                  {sruData.start_date && sruData.end_date 
                    ? `${sruData.start_date} – ${sruData.end_date}`
                    : "Räkenskapsår saknas"
                  }
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Loading State */}
      {loading && (
        <div className="space-y-4">
          <Skeleton className="h-8 w-48" />
          <div className="grid gap-4 md:grid-cols-2">
            <Skeleton className="h-64" />
            <Skeleton className="h-64" />
          </div>
        </div>
      )}

      {/* INK2 Blankett */}
      {!loading && sruData && (
        <div className="space-y-6">
          {/* Tillgångar */}
          <Card>
            <CardHeader className="bg-slate-50 dark:bg-slate-900">
              <CardTitle className="text-lg">Tillgångar</CardTitle>
              <CardDescription>Anläggningstillgångar och omsättningstillgångar</CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <table className="w-full">
                <tbody className="divide-y">
                  {FIELD_GROUPS["Tillgångar"].map((fieldNum) => {
                    const value = getFieldValue(fieldNum);
                    if (value === 0) return null;
                    return (
                      <tr key={fieldNum} className="hover:bg-muted/50">
                        <td className="px-4 py-3 w-20 font-mono text-sm">{fieldNum}</td>
                        <td className="px-4 py-3 text-sm">
                          {FIELD_DESCRIPTIONS[fieldNum] || sruData.fields?.[fieldNum]?.description || "-"}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-sm">
                          {formatField(value)}
                        </td>
                      </tr>
                    );
                  })}
                  <tr className="bg-muted/30 font-medium">
                    <td className="px-4 py-3 w-20 font-mono text-sm">7450</td>
                    <td className="px-4 py-3 text-sm">Summa tillgångar</td>
                    <td className="px-4 py-3 text-right font-mono text-sm">
                      {formatField(getFieldValue("7450"))}
                    </td>
                  </tr>
                </tbody>
              </table>
            </CardContent>
          </Card>

          {/* Eget kapital och skulder */}
          <Card>
            <CardHeader className="bg-slate-50 dark:bg-slate-900">
              <CardTitle className="text-lg">Eget kapital och skulder</CardTitle>
              <CardDescription>Eget kapital, avsättningar och skulder</CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <table className="w-full">
                <tbody className="divide-y">
                  {FIELD_GROUPS["Eget kapital och skulder"].map((fieldNum) => {
                    const value = getFieldValue(fieldNum);
                    if (value === 0 && fieldNum !== "7301") return null;
                    return (
                      <tr key={fieldNum} className="hover:bg-muted/50">
                        <td className="px-4 py-3 w-20 font-mono text-sm">{fieldNum}</td>
                        <td className="px-4 py-3 text-sm">
                          {FIELD_DESCRIPTIONS[fieldNum] || sruData.fields?.[fieldNum]?.description || "-"}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-sm">
                          {formatField(value)}
                        </td>
                      </tr>
                    );
                  })}
                  <tr className="bg-muted/30 font-medium">
                    <td className="px-4 py-3 w-20 font-mono text-sm">7550</td>
                    <td className="px-4 py-3 text-sm">Summa eget kapital och skulder</td>
                    <td className="px-4 py-3 text-right font-mono text-sm">
                      {formatField(getFieldValue("7550"))}
                    </td>
                  </tr>
                </tbody>
              </table>
            </CardContent>
          </Card>

          {/* Resultaträkning */}
          <Card>
            <CardHeader className="bg-slate-50 dark:bg-slate-900">
              <CardTitle className="text-lg">Resultaträkning</CardTitle>
              <CardDescription>Rörelseresultat, finansiella poster och årets resultat</CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <table className="w-full">
                <tbody className="divide-y">
                  {/* Intäkter */}
                  {getFieldValue("7410") !== 0 && (
                    <tr className="hover:bg-muted/50">
                      <td className="px-4 py-3 w-20 font-mono text-sm">7410</td>
                      <td className="px-4 py-3 text-sm">Nettoomsättning</td>
                      <td className="px-4 py-3 text-right font-mono text-sm">
                        {formatField(getFieldValue("7410"))}
                      </td>
                    </tr>
                  )}
                  {getFieldValue("7417") !== 0 && (
                    <tr className="hover:bg-muted/50">
                      <td className="px-4 py-3 w-20 font-mono text-sm">7417</td>
                      <td className="px-4 py-3 text-sm">Rörelseintäkter</td>
                      <td className="px-4 py-3 text-right font-mono text-sm">
                        {formatField(getFieldValue("7417"))}
                      </td>
                    </tr>
                  )}
                  {getFieldValue("7528") !== 0 && (
                    <tr className="hover:bg-muted/50">
                      <td className="px-4 py-3 w-20 font-mono text-sm">7528</td>
                      <td className="px-4 py-3 text-sm">Finansiella intäkter</td>
                      <td className="px-4 py-3 text-right font-mono text-sm">
                        {formatField(getFieldValue("7528"))}
                      </td>
                    </tr>
                  )}
                  {/* Kostnader */}
                  {getFieldValue("7522") !== 0 && (
                    <tr className="hover:bg-muted/50">
                      <td className="px-4 py-3 w-20 font-mono text-sm">7522</td>
                      <td className="px-4 py-3 text-sm">Övriga externa kostnader</td>
                      <td className="px-4 py-3 text-right font-mono text-sm">
                        {formatField(getFieldValue("7522"))}
                      </td>
                    </tr>
                  )}
                  {/* Resultat */}
                  {getFieldValue("7450") !== 0 && (
                    <tr className="bg-muted/20 font-medium">
                      <td className="px-4 py-3 w-20 font-mono text-sm">7450</td>
                      <td className="px-4 py-3 text-sm">Rörelseresultat</td>
                      <td className="px-4 py-3 text-right font-mono text-sm">
                        {formatField(getFieldValue("7450"))}
                      </td>
                    </tr>
                  )}
                  {getFieldValue("7513") !== 0 && (
                    <tr className="hover:bg-muted/50">
                      <td className="px-4 py-3 w-20 font-mono text-sm">7513</td>
                      <td className="px-4 py-3 text-sm">Skatt på årets resultat</td>
                      <td className="px-4 py-3 text-right font-mono text-sm text-red-600">
                        -{formatField(getFieldValue("7513"))}
                      </td>
                    </tr>
                  )}
                  {getFieldValue("7514") !== 0 && (
                    <tr className="bg-muted/30 font-bold">
                      <td className="px-4 py-3 w-20 font-mono text-sm">7514</td>
                      <td className="px-4 py-3 text-sm">Årets resultat</td>
                      <td className="px-4 py-3 text-right font-mono text-sm">
                        {formatField(getFieldValue("7514"))}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>

          {/* Balanskontroll */}
          {getFieldValue("7670") !== 0 && (
            <Card className="border-yellow-500/50">
              <CardHeader className="bg-yellow-50 dark:bg-yellow-900/20">
                <CardTitle className="text-lg text-yellow-700">⚠️ Balanskontroll</CardTitle>
              </CardHeader>
              <CardContent className="p-4">
                <p className="text-sm text-yellow-700">
                  Skillnad mellan tillgångar och skulder/EK: {formatField(getFieldValue("7670"))}
                </p>
                <p className="text-xs text-yellow-600 mt-1">
                  Denna skillnad bör vara 0. Kontrollera att alla verifikationer är bokförda korrekt.
                </p>
              </CardContent>
            </Card>
          )}

          {/* Alla fält (collapsible) */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm text-muted-foreground">Alla ifyllda fält</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                {Object.entries(sruData.fields)
                  .filter(([_, field]) => field.value !== 0)
                  .map(([key, field]) => (
                    <div key={key} className="flex justify-between px-2 py-1 bg-muted rounded">
                      <span className="font-mono">{field.field_number}</span>
                      <span>{formatCurrency(field.value)}</span>
                    </div>
                  ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
