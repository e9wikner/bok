"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { 
  ArrowLeft, 
  Save, 
  FileText, 
  AlertTriangle,
  Download,
  Eye,
  Loader2,
  Info,
  ExternalLink,
  Copy,
  RotateCcw
} from "lucide-react";
import Link from "next/link";

interface Account {
  code: string;
  name: string;
  account_type: string;
}

interface FiscalYear {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
}

interface SRUMapping {
  id: string;
  fiscal_year_id: string;
  account_id: string;
  account_code: string;
  account_name: string;
  sru_field: string;
  created_at: string;
  updated_at: string;
}

// Common SRU fields with descriptions used by the app's INK2 export.
const SRU_FIELDS = [
  { code: "7201", description: "Koncessioner, patent, licenser, varumärken, hyresrätter, goodwill och liknande rättigheter", bas: "1000-1099" },
  { code: "7214", description: "Byggnader och mark", bas: "1100-1199" },
  { code: "7215", description: "Maskiner, inventarier och övriga materiella anläggningstillgångar", bas: "1200-1299" },
  { code: "7233", description: "Ägarintresse i övriga företag och andra långfristiga värdepappersinnehav", bas: "1300-1399" },
  { code: "7241", description: "Råvaror och förnödenheter", bas: "1400-1499" },
  { code: "7251", description: "Kundfordringar", bas: "1500-1599" },
  { code: "7261", description: "Övriga fordringar", bas: "1600-1699" },
  { code: "7263", description: "Förutbetalda kostnader och upplupna intäkter", bas: "1700-1799" },
  { code: "7271", description: "Övriga kortfristiga placeringar", bas: "1800-1899" },
  { code: "7281", description: "Likvida medel", bas: "1900-1999" },
  { code: "7301", description: "Eget kapital", bas: "2000-2089" },
  { code: "7302", description: "Balanserat resultat/Årets resultat", bas: "2091, 2099" },
  { code: "7321", description: "Obeskattade reserver", bas: "2100-2199" },
  { code: "7350", description: "Avsättningar", bas: "2200-2299" },
  { code: "7365", description: "Långfristiga skulder", bas: "2300-2399" },
  { code: "7368", description: "Leverantörsskulder", bas: "2400-2499" },
  { code: "7369", description: "Skatteskulder", bas: "2500-2599" },
  { code: "7370", description: "Övriga kortfristiga skulder", bas: "2600-2999" },
  { code: "7410", description: "Nettoomsättning", bas: "3000-3799" },
  { code: "7413", description: "Övriga rörelseintäkter", bas: "3900-3999" },
  { code: "7511", description: "Material och varor", bas: "4000-4999" },
  { code: "7513", description: "Övriga externa kostnader", bas: "5000-6999" },
  { code: "7514", description: "Personalkostnader", bas: "7000-7699" },
  { code: "7515", description: "Av- och nedskrivningar", bas: "7800-7999" },
  { code: "7517", description: "Övriga rörelsekostnader", bas: "8000-8199" },
  { code: "7416/7520", description: "Resultat från övriga finansiella anläggningstillgångar", bas: "8200-8299" },
  { code: "7416", description: "Resultat från övriga finansiella anläggningstillgångar", bas: "8200-8299" },
  { code: "7520", description: "Resultat från övriga finansiella anläggningstillgångar", bas: "8200-8299" },
  { code: "7417", description: "Övriga ränteintäkter och liknande resultatposter", bas: "8300-8399" },
  { code: "7522", description: "Räntekostnader och liknande resultatposter", bas: "8400-8499" },
  { code: "7528", description: "Skatt på årets resultat", bas: "8910-8919" },
];

const getFieldDescription = (fieldCode?: string | null) =>
  SRU_FIELDS.find((field) => field.code === fieldCode)?.description;

export default function SRUMappingsPage() {
  const [fiscalYears, setFiscalYears] = useState<FiscalYear[]>([]);
  const [selectedYear, setSelectedYear] = useState<string>("");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [mappings, setMappings] = useState<Record<string, string>>({});
  const [originalMappings, setOriginalMappings] = useState<Record<string, string>>({});
  const [defaultMappings, setDefaultMappings] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Load fiscal years on mount
  useEffect(() => {
    loadFiscalYears();
  }, []);

  // Load accounts and mappings when fiscal year changes
  useEffect(() => {
    if (selectedYear) {
      loadAccountsAndMappings(selectedYear);
    }
  }, [selectedYear]);

  const loadFiscalYears = async () => {
    try {
      const response = await api.getFiscalYears();
      setFiscalYears(response.fiscal_years || []);
      if (response.fiscal_years?.length > 0) {
        setSelectedYear(response.fiscal_years[0].id);
      }
    } catch {
      setError("Kunde inte ladda räkenskapsår");
    }
  };

  const loadAccountsAndMappings = async (fiscalYearId: string) => {
    setLoading(true);
    setError(null);
    try {
      // Load accounts
      const accountsResponse = await api.getAccounts();
      setAccounts(accountsResponse.accounts || []);

      const defaultMappingsResponse = await api.getDefaultSRUMappings(fiscalYearId);
      const defaultMappingsData: Record<string, string> = {};
      defaultMappingsResponse.forEach((m: SRUMapping) => {
        defaultMappingsData[m.account_code] = m.sru_field;
      });
      setDefaultMappings(defaultMappingsData);

      // Load existing SRU mappings
      try {
        const mappingsResponse = await api.getSRUMappings(fiscalYearId);
        const mappingsData: Record<string, string> = {};
        mappingsResponse.forEach((m: SRUMapping) => {
          mappingsData[m.account_code] = m.sru_field;
        });
        setMappings(mappingsData);
        setOriginalMappings(mappingsData);
      } catch {
        // No mappings yet is OK
        setMappings({});
        setOriginalMappings({});
      }
      setHasChanges(false);
    } catch {
      setError("Kunde inte ladda konton eller mappningar");
    } finally {
      setLoading(false);
    }
  };

  const handleMappingChange = (accountCode: string, sruField: string) => {
    const newMappings = { ...mappings };
    if (sruField === "" || sruField === "__none__" || sruField === "__standard__") {
      delete newMappings[accountCode];
    } else {
      newMappings[accountCode] = sruField;
    }
    setMappings(newMappings);
    setHasChanges(JSON.stringify(newMappings) !== JSON.stringify(originalMappings));
  };

  const replaceMappings = (nextMappings: Record<string, string>) => {
    setMappings(nextMappings);
    setHasChanges(JSON.stringify(nextMappings) !== JSON.stringify(originalMappings));
  };

  const inheritPreviousYear = async () => {
    if (!selectedYear) return;

    const currentYear = fiscalYears.find((year) => year.id === selectedYear);
    if (!currentYear) return;

    const previousYear = fiscalYears
      .filter((year) => new Date(year.end_date) < new Date(currentYear.start_date))
      .sort((a, b) => new Date(b.end_date).getTime() - new Date(a.end_date).getTime())[0];

    if (!previousYear) {
      setError("Det finns inget tidigare räkenskapsår att ärva mappning från");
      return;
    }

    setError(null);
    setSuccess(null);
    try {
      const mappingsResponse = await api.getSRUMappings(previousYear.id);
      const inheritedMappings: Record<string, string> = {};
      mappingsResponse.forEach((m: SRUMapping) => {
        inheritedMappings[m.account_code] = m.sru_field;
      });
      replaceMappings(inheritedMappings);
      setSuccess(`Mappningar från ${previousYear.name} har lästs in. Klicka på Spara ändringar för att använda dem.`);
    } catch {
      setError("Kunde inte hämta mappningar från föregående år");
    }
  };

  const resetToDefault = () => {
    replaceMappings({});
    setSuccess("Standardmappningen är vald. Klicka på Spara ändringar för att ta bort årets manuella mappningar.");
  };

  const saveMappings = async () => {
    if (!selectedYear) return;
    
    setSaving(true);
    setError(null);
    setSuccess(null);
    
    try {
      // Prepare bulk update data
      const mappingsList = Object.entries(mappings).map(([accountCode, sruField]) => ({
        account_id: accountCode,
        sru_field: sruField,
      }));

      await api.bulkUpdateSRUMappings(selectedYear, mappingsList);
      
      setOriginalMappings(mappings);
      setHasChanges(false);
      setSuccess("SRU-mappningarna har sparats");
      
      // Clear success message after 3 seconds
      setTimeout(() => setSuccess(null), 3000);
    } catch {
      setError("Kunde inte spara mappningarna");
    } finally {
      setSaving(false);
    }
  };

  const exportSRU = async () => {
    if (!selectedYear) return;
    
    setError(null);
    try {
      const response = await api.exportSRU(selectedYear);
      
      // Download ZIP file
      const blob = new Blob([response.data], { type: "application/zip" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const contentDisposition = response.headers["content-disposition"];
      const filename = contentDisposition?.split("filename=")[1]?.replace(/"/g, "") || "INK2_SRU.zip";
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      
      setSuccess("SRU-filer har laddats ner");
      setTimeout(() => setSuccess(null), 3000);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Export misslyckades");
    }
  };

  const previewSRU = async () => {
    if (!selectedYear) return;
    
    // Open preview in new window/tab
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "";
    window.open(`${apiUrl}/api/v1/export/sru/${selectedYear}/preview`, "_blank");
  };

  if (loading && !fiscalYears.length) {
    return (
      <div className="p-4 lg:p-8 flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="p-4 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-4">
          <Link href="/settings">
            <Button variant="outline" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">
              SRU-mappningar
            </h1>
            <p className="text-muted-foreground mt-1">
              Koppla konton till INK2-deklarationsfält
            </p>
          </div>
        </div>
        
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={inheritPreviousYear}
            disabled={!selectedYear || saving}
            className="gap-2"
          >
            <Copy className="h-4 w-4" />
            Ärv föregående år
          </Button>
          <Button
            variant="outline"
            onClick={resetToDefault}
            disabled={!selectedYear || saving}
            className="gap-2"
          >
            <RotateCcw className="h-4 w-4" />
            Återställ standard
          </Button>
          <Button
            variant="outline"
            onClick={previewSRU}
            disabled={!selectedYear}
            className="gap-2"
          >
            <Eye className="h-4 w-4" />
            Förhandsgranska
          </Button>
          <Button
            variant="outline"
            onClick={exportSRU}
            disabled={!selectedYear}
            className="gap-2"
          >
            <Download className="h-4 w-4" />
            Exportera SRU
          </Button>
          <Button
            onClick={saveMappings}
            disabled={!hasChanges || saving}
            className="gap-2"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {saving ? "Sparar..." : "Spara ändringar"}
          </Button>
        </div>
      </div>

      {/* Error/Success Messages */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertTriangle className="h-5 w-5" />
          {error}
        </div>
      )}
      {success && (
        <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg flex items-center gap-2">
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          {success}
        </div>
      )}

      <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-4 text-blue-950">
        <div className="flex items-start gap-3">
          <Info className="h-5 w-5 mt-0.5 shrink-0" />
          <div className="space-y-2">
            <p className="text-sm font-medium">SRU = Skatteverkets Rapporterings-Utbyte</p>
            <p className="text-sm text-blue-900">
              Systemet använder standardmappningen automatiskt vid export när ingen årsspecifik
              mappning finns. Årets mappning sparas bara när ett konto ska avvika, till exempel
              efter en SIE4-import med #SRU-koder.
            </p>
            <a
              href="https://edeklarera.se/sru-filer/sru-koder"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-sm font-medium underline underline-offset-4"
            >
              SRU-koder och fältbeskrivningar
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
      </div>

      {/* Fiscal Year Selector */}
      <Card>
        <CardHeader>
          <CardTitle>Räkenskapsår</CardTitle>
          <CardDescription>
            Välj vilket räkenskapsår du vill hantera mappningar för
          </CardDescription>
        </CardHeader>
        <CardContent>
          <select
            value={selectedYear}
            onChange={(e) => setSelectedYear(e.target.value)}
            className="w-full sm:w-[300px] rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">Välj räkenskapsår</option>
            {fiscalYears.map((year) => (
              <option key={year.id} value={year.id}>
                {year.name} ({year.start_date} - {year.end_date})
              </option>
            ))}
          </select>
        </CardContent>
      </Card>

      {/* Mappings Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Konton och SRU-fält
          </CardTitle>
          <CardDescription>
            {accounts.length} konton. En tom årsmappning betyder att standardmappningen används.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="border rounded-lg overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium w-[100px]">Konto</th>
                      <th className="px-4 py-3 text-left font-medium">Namn</th>
                      <th className="px-4 py-3 text-left font-medium w-[260px]">Årsmappning</th>
                      <th className="px-4 py-3 text-left font-medium w-[260px]">Standardmappning</th>
                      <th className="px-4 py-3 text-left font-medium w-[280px]">Aktiv mappning</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {accounts.map((account) => {
                      const savedMapping = mappings[account.code];
                      const originalMapping = originalMappings[account.code];
                      const standardMapping = defaultMappings[account.code];
                      const activeMapping = savedMapping || standardMapping;
                      const standardDescription = getFieldDescription(standardMapping);
                      const activeDescription = getFieldDescription(activeMapping);
                      const isChanged = savedMapping !== originalMapping;
                      const isCustom = Boolean(savedMapping && savedMapping !== standardMapping);
                      const usesStandard = !savedMapping && Boolean(standardMapping);
                      
                      return (
                        <tr key={account.code} className={isChanged ? "bg-yellow-50/50" : ""}>
                          <td className="px-4 py-3 font-mono">{account.code}</td>
                          <td className="px-4 py-3">{account.name}</td>
                          <td className="px-4 py-3">
                            <select
                              value={savedMapping || (standardMapping ? "__standard__" : "__none__")}
                              onChange={(e) => handleMappingChange(account.code, e.target.value)}
                              className="w-full rounded border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                            >
                              {standardMapping ? (
                                <option value="__standard__">
                                  Använd standard: {standardMapping} - {standardDescription || "Okänt fält"}
                                </option>
                              ) : (
                                <option value="__none__">Ingen mappning</option>
                              )}
                              {SRU_FIELDS.map((field) => (
                                <option key={field.code} value={field.code}>
                                  {field.code} - {field.description} ({field.bas})
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="px-4 py-3 text-muted-foreground">
                            {standardMapping && standardDescription ? (
                              <span title={`BAS ${SRU_FIELDS.find(f => f.code === standardMapping)?.bas || ""}`}>
                                {standardMapping} - {standardDescription}
                              </span>
                            ) : (
                              <span>Ingen standardmappning</span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {activeMapping ? (
                              <span className="text-muted-foreground">
                                {activeMapping} - {activeDescription || "Okänt fält"}
                              </span>
                            ) : (
                              <span className="text-muted-foreground">Ingen mappning</span>
                            )}
                            {usesStandard && (
                              <Badge variant="outline" className="ml-2 text-green-700 border-green-700">
                                Standard
                              </Badge>
                            )}
                            {isCustom && (
                              <Badge variant="outline" className="ml-2 text-amber-700 border-amber-700">
                                Anpassad
                              </Badge>
                            )}
                            {isChanged && (
                              <Badge variant="outline" className="ml-2 text-yellow-600 border-yellow-600">
                                Ändrad
                              </Badge>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Info Card */}
      <Card className="bg-muted/50">
        <CardContent className="pt-6">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5" />
            <div className="space-y-2">
              <p className="text-sm font-medium">Om SRU-mappningar</p>
              <p className="text-sm text-muted-foreground">
                SRU-mappningar kopplar dina bokföringskonton till fälten i inkomstdeklarationen
                (INK2). Standardmappningen visas separat så att du kan se vad systemet hade valt
                utan årsspecifika ändringar.
              </p>
              <p className="text-sm text-muted-foreground">
                Knappen Ärv föregående år kopierar sparade årsmappningar från närmast tidigare
                räkenskapsår. Återställ standard tar bort årets sparade mappningar vid nästa sparning.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
