"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { useFiscalYears } from "@/hooks/useData";
import { Download, FileText, AlertCircle, CheckCircle2, Calendar, Building2, FileSpreadsheet, Calculator } from "lucide-react";

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

type TabType = "ink2" | "ink2r" | "ink2s";

// Fält grupperingar per blankett
const INK2_FIELDS = {
  "Räkenskapsår": ["7011", "7012"],
  "Resultat": ["7410", "7450", "7513", "7514"],
  "Övrigt": ["7670"]
};

const INK2R_FIELDS = {
  "Tillgångar": ["7251", "7252", "7261", "7263", "7281", "7284", "7285", "7286"],
  "Eget kapital": ["7301", "7302"],
  "Skulder": ["7321", "7350", "7365", "7368", "7369", "7370"],
  "Intäkter": ["7410", "7413", "7416", "7417", "7420", "7528"],
  "Kostnader": ["7511", "7513", "7514", "7515", "7520", "7522"]
};

const FIELD_DESCRIPTIONS: Record<string, string> = {
  "7011": "Räkenskapsår – första dag",
  "7012": "Räkenskapsår – sista dag",
  "7251": "Koncessioner, patent, licenser, varumärken m.m.",
  "7252": "Hyresrätter och liknande rättigheter",
  "7261": "Byggnader och mark",
  "7263": "Maskiner och inventarier",
  "7281": "Kortfristiga fordringar",
  "7284": "Kassa och bank",
  "7285": "Aktier och andelar",
  "7286": "Övriga tillgångar",
  "7301": "Aktiekapital",
  "7302": "Balanserad vinst eller förlust",
  "7321": "Reservfond",
  "7350": "Avsättningar",
  "7365": "Långfristiga skulder till kreditinstitut",
  "7368": "Rörelseresultat",
  "7369": "Kortfristiga skulder",
  "7370": "Skulder till närstående personer",
  "7410": "Nettoomsättning",
  "7413": "Förändring av lager av produkter i arbete",
  "7416": "Aktiverat arbete för egen räkning",
  "7417": "Övriga rörelseintäkter",
  "7420": "Rörelseintäkter",
  "7450": "Rörelseresultat",
  "7511": "Råvaror och förnödenheter",
  "7513": "Skatt på årets resultat",
  "7514": "Årets resultat",
  "7515": "Avskrivningar",
  "7520": "Övriga rörelsekostnader",
  "7522": "Övriga externa kostnader",
  "7528": "Finansiella intäkter",
  "7670": "Skillnad mellan tillgångar och skulder/EK"
};

const TABS = [
  { id: "ink2" as TabType, label: "INK2", icon: FileText, description: "Huvudblankett" },
  { id: "ink2r" as TabType, label: "INK2R", icon: FileSpreadsheet, description: "Räkenskapsschema" },
  { id: "ink2s" as TabType, label: "INK2S", icon: Calculator, description: "Skattemässiga justeringar" },
];

export default function Ink2Page() {
  const [activeTab, setActiveTab] = useState<TabType>("ink2");
  const [selectedYear, setSelectedYear] = useState<string>("");
  const [sruData, setSruData] = useState<SRUData | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const { data: fiscalYearsData } = useFiscalYears();
  
  // Handle both { fiscal_years: [...] } and [...] response formats
  const fiscalYears = Array.isArray(fiscalYearsData) 
    ? fiscalYearsData 
    : fiscalYearsData?.fiscal_years || [];

  useEffect(() => {
    if (fiscalYears.length > 0 && !selectedYear) {
      setSelectedYear(fiscalYears[0].id);
    }
  }, [fiscalYears, selectedYear]);

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
    if (value === 0) return "";
    return formatCurrency(value);
  };

  const renderFieldRow = (fieldNum: string, isBold = false) => {
    const value = getFieldValue(fieldNum);
    const hasValue = value !== 0;
    return (
      <tr key={fieldNum} className={`${hasValue ? "bg-white" : "bg-muted/30"} ${isBold ? "font-semibold border-t-2 border-gray-300" : "border-b border-gray-100"} hover:bg-blue-50/50`}>
        <td className="px-4 py-2 w-24 font-mono text-sm text-gray-600">{fieldNum}</td>
        <td className="px-4 py-2 text-sm text-gray-800">
          {FIELD_DESCRIPTIONS[fieldNum] || sruData?.fields?.[fieldNum]?.description || "-"}
        </td>
        <td className="px-4 py-2 w-40 text-right">
          <span className={`font-mono text-sm ${isBold ? "font-bold" : ""} ${value < 0 ? "text-red-600" : "text-gray-900"}`}>
            {formatField(value)}
          </span>
        </td>
      </tr>
    );
  };

  const renderFieldGroup = (title: string, fields: string[]) => {
    const hasAnyValue = fields.some(f => getFieldValue(f) !== 0);
    if (!hasAnyValue && activeTab !== "ink2r") return null;
    
    return (
      <div className="mb-6">
        <h3 className="text-sm font-bold text-gray-700 uppercase tracking-wide mb-3 px-2 py-1 bg-gray-100 rounded">
          {title}
        </h3>
        <table className="w-full">
          <tbody>
            {fields.map(fieldNum => renderFieldRow(fieldNum))}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Inkomstdeklaration 2</h1>
          <p className="text-muted-foreground text-sm">
            Aktiebolag, ekonomiska föreningar, bostadsrättsföreningar m.fl.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {fiscalYears.length > 0 && (
            <div className="flex items-center gap-2 bg-white border rounded-lg px-3 py-2 shadow-sm">
              <Calendar className="h-4 w-4 text-gray-400" />
              <select
                value={selectedYear}
                onChange={(e) => setSelectedYear(e.target.value)}
                className="bg-transparent text-sm font-medium focus:outline-none"
              >
                {fiscalYears.map((fy: any) => (
                  <option key={fy.id} value={fy.id}>
                    Räkenskapsår {new Date(fy.start_date).getFullYear()}
                  </option>
                ))}
              </select>
            </div>
          )}
          {fiscalYears.length === 0 && !fiscalYearsData && (
            <div className="text-sm text-gray-500">Laddar räkenskapsår...</div>
          )}
          {fiscalYears.length === 0 && fiscalYearsData && (
            <div className="text-sm text-amber-600">Inga räkenskapsår hittades</div>
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

      {/* Company Info Card */}
      {sruData && (
        <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
          <CardContent className="p-4">
            <div className="flex flex-wrap items-center gap-6 text-sm">
              <div className="flex items-center gap-2">
                <Building2 className="h-5 w-5 text-blue-600" />
                <div>
                  <span className="text-gray-500 text-xs block">Företag</span>
                  <span className="font-semibold text-gray-900">{sruData.company_name || "Företagsnamn saknas"}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-blue-600" />
                <div>
                  <span className="text-gray-500 text-xs block">Organisationsnummer</span>
                  <span className="font-mono text-gray-900">{sruData.org_number || "-"}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Calendar className="h-5 w-5 text-blue-600" />
                <div>
                  <span className="text-gray-500 text-xs block">Räkenskapsår</span>
                  <span className="text-gray-900">
                    {sruData.start_date && sruData.end_date 
                      ? `${sruData.start_date} – ${sruData.end_date}`
                      : "-"
                    }
                  </span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Alerts */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertCircle className="h-5 w-5" />
          {error}
        </div>
      )}
      {success && (
        <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5" />
          {success}
        </div>
      )}

      {/* Tab Navigation */}
      <div className="border-b border-gray-200">
        <nav className="flex space-x-1" aria-label="Tabs">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? "border-blue-600 text-blue-600 bg-blue-50/50"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>{tab.label}</span>
                <span className="hidden sm:inline text-xs text-gray-400">({tab.description})</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <div className="grid gap-4 md:grid-cols-2">
            <Skeleton className="h-96" />
            <Skeleton className="h-96" />
          </div>
        </div>
      )}

      {/* INK2 Tab - Huvudblankett */}
      {!loading && activeTab === "ink2" && sruData && (
        <div className="space-y-6">
          <Card className="border-2 border-gray-300 shadow-lg">
            <CardHeader className="bg-gray-100 border-b border-gray-300">
              <CardTitle className="text-lg font-bold text-gray-800">INK2 – Huvudblankett</CardTitle>
              <CardDescription>Obligatoriska uppgifter för inkomstdeklaration</CardDescription>
            </CardHeader>
            <CardContent className="p-6">
              {/* Räkenskapsår */}
              <div className="mb-6">
                <h3 className="text-sm font-bold text-gray-700 uppercase tracking-wide mb-3 px-2 py-1 bg-gray-100 rounded">
                  Räkenskapsår
                </h3>
                <table className="w-full">
                  <tbody>
                    <tr className="border-b border-gray-100">
                      <td className="px-4 py-3 w-24 font-mono text-sm text-gray-600">7011</td>
                      <td className="px-4 py-3 text-sm text-gray-800">Räkenskapsår – första dag</td>
                      <td className="px-4 py-3 w-40 text-right font-mono text-sm">
                        {sruData.start_date || "-"}
                      </td>
                    </tr>
                    <tr className="border-b border-gray-100">
                      <td className="px-4 py-3 w-24 font-mono text-sm text-gray-600">7012</td>
                      <td className="px-4 py-3 text-sm text-gray-800">Räkenskapsår – sista dag</td>
                      <td className="px-4 py-3 w-40 text-right font-mono text-sm">
                        {sruData.end_date || "-"}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Resultat */}
              <div className="mb-6">
                <h3 className="text-sm font-bold text-gray-700 uppercase tracking-wide mb-3 px-2 py-1 bg-gray-100 rounded">
                  Resultat
                </h3>
                <table className="w-full">
                  <tbody>
                    {getFieldValue("7410") !== 0 && renderFieldRow("7410")}
                    {renderFieldRow("7450", true)}
                    {getFieldValue("7513") !== 0 && (
                      <tr className="border-b border-gray-100">
                        <td className="px-4 py-2 w-24 font-mono text-sm text-gray-600">7513</td>
                        <td className="px-4 py-2 text-sm text-gray-800">Skatt på årets resultat</td>
                        <td className="px-4 py-2 w-40 text-right font-mono text-sm text-red-600">
                          -{formatField(getFieldValue("7513"))}
                        </td>
                      </tr>
                    )}
                    {renderFieldRow("7514", true)}
                  </tbody>
                </table>
              </div>

              {/* Balanskontroll */}
              {getFieldValue("7670") !== 0 && (
                <div className="mt-6 p-4 bg-yellow-50 border border-yellow-300 rounded-lg">
                  <div className="flex items-start gap-3">
                    <AlertCircle className="h-5 w-5 text-yellow-600 mt-0.5" />
                    <div>
                      <h4 className="font-semibold text-yellow-800">⚠️ Balanskontroll</h4>
                      <p className="text-sm text-yellow-700 mt-1">
                        Skillnad mellan tillgångar och skulder/EK: {formatField(getFieldValue("7670"))}
                      </p>
                      <p className="text-xs text-yellow-600 mt-1">
                        Denna skillnad bör vara 0. Kontrollera att alla verifikationer är korrekt bokförda.
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* INK2R Tab - Räkenskapsschema */}
      {!loading && activeTab === "ink2r" && sruData && (
        <div className="space-y-6">
          <Card className="border-2 border-gray-300 shadow-lg">
            <CardHeader className="bg-gray-100 border-b border-gray-300">
              <CardTitle className="text-lg font-bold text-gray-800">INK2R – Räkenskapsschema</CardTitle>
              <CardDescription>Balansräkning och resultaträkning</CardDescription>
            </CardHeader>
            <CardContent className="p-6">
              <div className="grid md:grid-cols-2 gap-8">
                {/* Vänster kolumn - Tillgångar */}
                <div>
                  {renderFieldGroup("Tillgångar", INK2R_FIELDS["Tillgångar"])}
                  <div className="mt-6 p-3 bg-blue-50 rounded-lg">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-gray-800">Summa tillgångar</span>
                      <span className="font-mono font-bold text-lg">{formatField(getFieldValue("7450"))}</span>
                    </div>
                  </div>
                </div>
                
                {/* Höger kolumn - EK och Skulder */}
                <div>
                  {renderFieldGroup("Eget kapital", INK2R_FIELDS["Eget kapital"])}
                  {renderFieldGroup("Skulder", INK2R_FIELDS["Skulder"])}
                  <div className="mt-6 p-3 bg-green-50 rounded-lg">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-gray-800">Summa EK och skulder</span>
                      <span className="font-mono font-bold text-lg">{formatField(getFieldValue("7550"))}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Resultaträkning */}
              <div className="mt-8 pt-8 border-t-2 border-gray-200">
                <h3 className="text-sm font-bold text-gray-700 uppercase tracking-wide mb-4 px-2 py-1 bg-gray-100 rounded">
                  Resultaträkning
                </h3>
                <div className="grid md:grid-cols-2 gap-8">
                  <div>
                    {renderFieldGroup("Intäkter", INK2R_FIELDS["Intäkter"])}
                  </div>
                  <div>
                    {renderFieldGroup("Kostnader", INK2R_FIELDS["Kostnader"])}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* INK2S Tab - Skattemässiga justeringar */}
      {!loading && activeTab === "ink2s" && (
        <div className="space-y-6">
          <Card className="border-2 border-gray-300 shadow-lg">
            <CardHeader className="bg-gray-100 border-b border-gray-300">
              <CardTitle className="text-lg font-bold text-gray-800">INK2S – Skattemässiga justeringar</CardTitle>
              <CardDescription>Justeringar mellan bokfört och skattemässigt resultat</CardDescription>
            </CardHeader>
            <CardContent className="p-6">
              <div className="text-center py-12 text-gray-500">
                <Calculator className="h-12 w-12 mx-auto mb-4 text-gray-300" />
                <p className="text-lg font-medium">Skattemässiga justeringar</p>
                <p className="text-sm mt-2 max-w-md mx-auto">
                  Denna del av blankettens visas här när skattemässiga justeringar är implementerade.
                  Till exempel avskrivningsdifferenser, ej avdragsgilla kostnader, m.m.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
