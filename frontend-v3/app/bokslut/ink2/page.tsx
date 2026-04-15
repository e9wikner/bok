"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { useFiscalYears } from "@/hooks/useData";
import { Download, FileText, AlertCircle, CheckCircle2, Calendar, Building2, FileSpreadsheet, Calculator, Map } from "lucide-react";

interface SRUField {
  field_number: string;
  description: string;
  value: number;
  source_accounts: string[];
}

interface SRUData {
  fiscal_year_id: string;
  company: {
    name: string;
    org_number: string;
  };
  fiscal_year: {
    start: string;
    end: string;
  };
  fields: SRUField[];
  validation?: {
    errors: string[];
    warnings: string[];
    is_valid: boolean;
  };
}

type TabType = "ink2" | "ink2r" | "ink2s" | "mappings";

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
  { id: "mappings" as TabType, label: "Mappningar", icon: Map, description: "Konto-mappningar" },
];

export default function Ink2Page() {
  const [activeTab, setActiveTab] = useState<TabType>("ink2");
  const [selectedYear, setSelectedYear] = useState<string>("");
  const [sruData, setSruData] = useState<SRUData | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [mappings, setMappings] = useState<Record<string, string>>({});
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
      const [sruResponse, mappingsResponse] = await Promise.all([
        api.previewSRU(fiscalYearId),
        api.getSRUMappings(fiscalYearId),
      ]);
      setSruData(sruResponse);
      // Convert array of mappings to Record<account_code, sru_field>
      const mappingsRecord: Record<string, string> = {};
      if (Array.isArray(mappingsResponse)) {
        mappingsResponse.forEach((m: any) => {
          mappingsRecord[m.account_code] = m.sru_field;
        });
      }
      setMappings(mappingsRecord);
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
      const year = sruData?.fiscal_year?.start ? sruData.fiscal_year.start.substring(0, 4) : "INK2";
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

  // Convert array to map for easy lookup
  const getFieldValue = (fieldNumber: string): number => {
    const field = sruData?.fields?.find(f => f.field_number === fieldNumber);
    return field?.value ?? 0;
  };

  const formatField = (value: number): string => {
    if (value === 0) return "";
    return formatCurrency(value);
  };

  const renderFieldRow = (fieldNum: string, isBold = false) => {
    const value = getFieldValue(fieldNum);
    const hasValue = value !== 0;
    return (
      <tr key={fieldNum} className={`${hasValue ? "bg-background" : "bg-muted/30"} ${isBold ? "font-semibold border-t-2 border-border" : "border-b border-border/50"} hover:bg-accent/50`}>
        <td className="px-4 py-2 w-24 font-mono text-sm text-muted-foreground">{fieldNum}</td>
        <td className="px-4 py-2 text-sm text-foreground">
          {FIELD_DESCRIPTIONS[fieldNum] || sruData?.fields?.find(f => f.field_number === fieldNum)?.description || "-"}
        </td>
        <td className="px-4 py-2 w-40 text-right">
          <span className={`font-mono text-sm ${isBold ? "font-bold" : ""} ${value < 0 ? "text-red-500" : "text-foreground"}`}>
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
        <h3 className="text-sm font-bold text-foreground uppercase tracking-wide mb-3 px-2 py-1 bg-muted rounded">
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

  // Format date from YYYYMMDD to YYYY-MM-DD
  const formatDate = (dateStr: string): string => {
    if (!dateStr || dateStr.length !== 8) return dateStr;
    return `${dateStr.substring(0, 4)}-${dateStr.substring(4, 6)}-${dateStr.substring(6, 8)}`;
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
            <div className="flex items-center gap-2 bg-background border rounded-lg px-3 py-2 shadow-sm">
              <Calendar className="h-4 w-4 text-muted-foreground" />
              <select
                value={selectedYear}
                onChange={(e) => setSelectedYear(e.target.value)}
                className="bg-transparent text-sm font-medium focus:outline-none text-foreground"
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
            <div className="text-sm text-muted-foreground">Laddar räkenskapsår...</div>
          )}
          {fiscalYears.length === 0 && fiscalYearsData && (
            <div className="text-sm text-amber-500">Inga räkenskapsår hittades</div>
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
        <Card className="bg-gradient-to-r from-primary/10 to-primary/5 border-primary/20">
          <CardContent className="p-4">
            <div className="flex flex-wrap items-center gap-6 text-sm">
              <div className="flex items-center gap-2">
                <Building2 className="h-5 w-5 text-primary" />
                <div>
                  <span className="text-muted-foreground text-xs block">Företag</span>
                  <span className="font-semibold text-foreground">{sruData.company?.name || "Företagsnamn saknas"}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-primary" />
                <div>
                  <span className="text-muted-foreground text-xs block">Organisationsnummer</span>
                  <span className="font-mono text-foreground">{sruData.company?.org_number || "-"}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Calendar className="h-5 w-5 text-primary" />
                <div>
                  <span className="text-muted-foreground text-xs block">Räkenskapsår</span>
                  <span className="text-foreground">
                    {sruData.fiscal_year?.start && sruData.fiscal_year?.end 
                      ? `${formatDate(sruData.fiscal_year.start)} – ${formatDate(sruData.fiscal_year.end)}`
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
        <div className="bg-destructive/10 border border-destructive/20 text-destructive px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertCircle className="h-5 w-5" />
          {error}
        </div>
      )}
      {success && (
        <div className="bg-green-500/10 border border-green-500/20 text-green-600 px-4 py-3 rounded-lg flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5" />
          {success}
        </div>
      )}

      {/* Validation Warnings */}
      {sruData?.validation?.warnings && sruData.validation.warnings.length > 0 && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-4">
          <h4 className="font-semibold text-amber-600 mb-2">⚠️ Varningar</h4>
          <ul className="text-sm text-amber-700 space-y-1">
            {sruData.validation.warnings.map((warning, idx) => (
              <li key={idx}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="border-b border-border">
        <nav className="flex space-x-1" aria-label="Tabs">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? "border-primary text-primary bg-primary/5"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>{tab.label}</span>
                <span className="hidden sm:inline text-xs text-muted-foreground">({tab.description})</span>
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
          <Card className="border-2 border-border shadow-lg">
            <CardHeader className="bg-muted border-b border-border">
              <CardTitle className="text-lg font-bold text-foreground">INK2 – Huvudblankett</CardTitle>
              <CardDescription>Obligatoriska uppgifter för inkomstdeklaration</CardDescription>
            </CardHeader>
            <CardContent className="p-6">
              {/* Räkenskapsår */}
              <div className="mb-6">
                <h3 className="text-sm font-bold text-foreground uppercase tracking-wide mb-3 px-2 py-1 bg-muted rounded">
                  Räkenskapsår
                </h3>
                <table className="w-full">
                  <tbody>
                    <tr className="border-b border-border/50">
                      <td className="px-4 py-3 w-24 font-mono text-sm text-muted-foreground">7011</td>
                      <td className="px-4 py-3 text-sm text-foreground">Räkenskapsår – första dag</td>
                      <td className="px-4 py-3 w-40 text-right font-mono text-sm text-foreground">
                        {formatDate(sruData.fiscal_year?.start) || "-"}
                      </td>
                    </tr>
                    <tr className="border-b border-border/50">
                      <td className="px-4 py-3 w-24 font-mono text-sm text-muted-foreground">7012</td>
                      <td className="px-4 py-3 text-sm text-foreground">Räkenskapsår – sista dag</td>
                      <td className="px-4 py-3 w-40 text-right font-mono text-sm text-foreground">
                        {formatDate(sruData.fiscal_year?.end) || "-"}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Resultat */}
              <div className="mb-6">
                <h3 className="text-sm font-bold text-foreground uppercase tracking-wide mb-3 px-2 py-1 bg-muted rounded">
                  Resultat
                </h3>
                <table className="w-full">
                  <tbody>
                    {getFieldValue("7410") !== 0 && renderFieldRow("7410")}
                    {renderFieldRow("7450", true)}
                    {getFieldValue("7513") !== 0 && (
                      <tr className="border-b border-border/50">
                        <td className="px-4 py-2 w-24 font-mono text-sm text-muted-foreground">7513</td>
                        <td className="px-4 py-2 text-sm text-foreground">Skatt på årets resultat</td>
                        <td className="px-4 py-2 w-40 text-right font-mono text-sm text-red-500">
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
                <div className="mt-6 p-4 bg-amber-500/10 border border-amber-500/30 rounded-lg">
                  <div className="flex items-start gap-3">
                    <AlertCircle className="h-5 w-5 text-amber-500 mt-0.5" />
                    <div>
                      <h4 className="font-semibold text-amber-600">⚠️ Balanskontroll</h4>
                      <p className="text-sm text-amber-700 mt-1">
                        Skillnad mellan tillgångar och skulder/EK: {formatField(getFieldValue("7670"))}
                      </p>
                      <p className="text-xs text-amber-600 mt-1">
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
          <Card className="border-2 border-border shadow-lg">
            <CardHeader className="bg-muted border-b border-border">
              <CardTitle className="text-lg font-bold text-foreground">INK2R – Räkenskapsschema</CardTitle>
              <CardDescription>Balansräkning och resultaträkning</CardDescription>
            </CardHeader>
            <CardContent className="p-6">
              <div className="grid md:grid-cols-2 gap-8">
                {/* Vänster kolumn - Tillgångar */}
                <div>
                  {renderFieldGroup("Tillgångar", INK2R_FIELDS["Tillgångar"])}
                  <div className="mt-6 p-3 bg-primary/10 rounded-lg">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-foreground">Summa tillgångar</span>
                      <span className="font-mono font-bold text-lg text-foreground">{formatField(getFieldValue("7450"))}</span>
                    </div>
                  </div>
                </div>
                
                {/* Höger kolumn - EK och Skulder */}
                <div>
                  {renderFieldGroup("Eget kapital", INK2R_FIELDS["Eget kapital"])}
                  {renderFieldGroup("Skulder", INK2R_FIELDS["Skulder"])}
                  <div className="mt-6 p-3 bg-primary/10 rounded-lg">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-foreground">Summa EK och skulder</span>
                      <span className="font-mono font-bold text-lg text-foreground">{formatField(getFieldValue("7550"))}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Resultaträkning */}
              <div className="mt-8 pt-8 border-t-2 border-border">
                <h3 className="text-sm font-bold text-foreground uppercase tracking-wide mb-4 px-2 py-1 bg-muted rounded">
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
          <Card className="border-2 border-border shadow-lg">
            <CardHeader className="bg-muted border-b border-border">
              <CardTitle className="text-lg font-bold text-foreground">INK2S – Skattemässiga justeringar</CardTitle>
              <CardDescription>Justeringar mellan bokfört och skattemässigt resultat</CardDescription>
            </CardHeader>
            <CardContent className="p-6">
              <div className="text-center py-12 text-muted-foreground">
                <Calculator className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
                <p className="text-lg font-medium">Skattemässiga justeringar</p>
                <p className="text-sm mt-2 max-w-md mx-auto">
                  Denna del av blanketten visas här när skattemässiga justeringar är implementerade.
                  Till exempel avskrivningsdifferenser, ej avdragsgilla kostnader, m.m.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Mappings Tab - Konto-mappningar */}
      {!loading && activeTab === "mappings" && sruData && (
        <div className="space-y-6">
          <Card className="border-2 border-border shadow-lg">
            <CardHeader className="bg-muted border-b border-border">
              <CardTitle className="text-lg font-bold text-foreground">SRU-mappningar</CardTitle>
              <CardDescription>Konton mappade till INK2-fält</CardDescription>
            </CardHeader>
            <CardContent className="p-6">
              <div className="grid md:grid-cols-2 gap-6">
                {/* Balansräkning - Tillgångar */}
                <div>
                  <h3 className="text-sm font-bold text-foreground uppercase tracking-wide mb-3 px-2 py-1 bg-muted rounded">
                    Tillgångar (1xxx)
                  </h3>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {Object.entries(mappings)
                      .filter(([account]) => account >= '1000' && account < '2000')
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([account, field]) => (
                        <div key={account} className="flex justify-between items-center px-3 py-2 bg-background rounded border border-border/50">
                          <div className="flex items-center gap-3">
                            <span className="font-mono text-sm text-muted-foreground">{account}</span>
                            <span className="text-sm text-foreground">
                              {sruData.fields.find(f => f.source_accounts?.includes(account))?.source_accounts?.includes(account) 
                                ? sruData.fields.find(f => f.source_accounts?.includes(account))?.field_number 
                                : ''}
                            </span>
                          </div>
                          <span className="font-mono text-sm font-medium text-primary">{field}</span>
                        </div>
                      ))}
                  </div>
                </div>

                {/* Balansräkning - EK och Skulder */}
                <div>
                  <h3 className="text-sm font-bold text-foreground uppercase tracking-wide mb-3 px-2 py-1 bg-muted rounded">
                    Eget kapital och skulder (2xxx)
                  </h3>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {Object.entries(mappings)
                      .filter(([account]) => account >= '2000' && account < '3000')
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([account, field]) => (
                        <div key={account} className="flex justify-between items-center px-3 py-2 bg-background rounded border border-border/50">
                          <div className="flex items-center gap-3">
                            <span className="font-mono text-sm text-muted-foreground">{account}</span>
                          </div>
                          <span className="font-mono text-sm font-medium text-primary">{field}</span>
                        </div>
                      ))}
                  </div>
                </div>

                {/* Resultaträkning - Intäkter */}
                <div>
                  <h3 className="text-sm font-bold text-foreground uppercase tracking-wide mb-3 px-2 py-1 bg-muted rounded">
                    Intäkter (3xxx)
                  </h3>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {Object.entries(mappings)
                      .filter(([account]) => account >= '3000' && account < '4000')
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([account, field]) => (
                        <div key={account} className="flex justify-between items-center px-3 py-2 bg-background rounded border border-border/50">
                          <div className="flex items-center gap-3">
                            <span className="font-mono text-sm text-muted-foreground">{account}</span>
                          </div>
                          <span className="font-mono text-sm font-medium text-primary">{field}</span>
                        </div>
                      ))}
                  </div>
                </div>

                {/* Resultaträkning - Kostnader */}
                <div>
                  <h3 className="text-sm font-bold text-foreground uppercase tracking-wide mb-3 px-2 py-1 bg-muted rounded">
                    Kostnader (4xxx-8xxx)
                  </h3>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {Object.entries(mappings)
                      .filter(([account]) => (account >= '4000' && account < '9000'))
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([account, field]) => (
                        <div key={account} className="flex justify-between items-center px-3 py-2 bg-background rounded border border-border/50">
                          <div className="flex items-center gap-3">
                            <span className="font-mono text-sm text-muted-foreground">{account}</span>
                          </div>
                          <span className="font-mono text-sm font-medium text-primary">{field}</span>
                        </div>
                      ))}
                  </div>
                </div>
              </div>

              {/* Summary stats */}
              <div className="mt-6 pt-6 border-t border-border">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                  <div className="p-3 bg-muted rounded-lg">
                    <div className="text-2xl font-bold text-foreground">
                      {Object.keys(mappings).filter(a => a >= '1000' && a < '2000').length}
                    </div>
                    <div className="text-xs text-muted-foreground">Tillgångskonton</div>
                  </div>
                  <div className="p-3 bg-muted rounded-lg">
                    <div className="text-2xl font-bold text-foreground">
                      {Object.keys(mappings).filter(a => a >= '2000' && a < '3000').length}
                    </div>
                    <div className="text-xs text-muted-foreground">Skuldkonton</div>
                  </div>
                  <div className="p-3 bg-muted rounded-lg">
                    <div className="text-2xl font-bold text-foreground">
                      {Object.keys(mappings).filter(a => a >= '3000' && a < '9000').length}
                    </div>
                    <div className="text-xs text-muted-foreground">Resultatkonton</div>
                  </div>
                  <div className="p-3 bg-muted rounded-lg">
                    <div className="text-2xl font-bold text-primary">
                      {Object.keys(mappings).length}
                    </div>
                    <div className="text-xs text-muted-foreground">Totalt mappade</div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
