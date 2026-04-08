"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { 
  ArrowLeft, 
  Save, 
  FileText, 
  AlertTriangle,
  Download,
  Eye,
  Loader2
} from "lucide-react";
import Link from "next/link";

interface Account {
  id: string;
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

// Common SRU fields with descriptions
const SRU_FIELDS = [
  { code: "7251", description: "Varulager" },
  { code: "7261", description: "Kundfordringar" },
  { code: "7263", description: "Övriga fordringar" },
  { code: "7271", description: "Förutbetalda kostnader" },
  { code: "7281", description: "Likvida medel" },
  { code: "7301", description: "Eget kapital" },
  { code: "7302", description: "Resultat" },
  { code: "7321", description: "Obeskattade reserver" },
  { code: "7350", description: "Avsättningar" },
  { code: "7365", description: "Långfristiga skulder" },
  { code: "7368", description: "Leverantörsskulder" },
  { code: "7369", description: "Skatteskulder" },
  { code: "7370", description: "Övriga kortfristiga skulder" },
  { code: "7410", description: "Nettoomsättning" },
  { code: "7413", description: "Övriga rörelseintäkter" },
  { code: "7511", description: "Material och varor" },
  { code: "7513", description: "Övriga externa kostnader" },
  { code: "7514", description: "Personalkostnader" },
  { code: "7515", description: "Av- och nedskrivningar" },
  { code: "7416", description: "Immateriella anläggningstillgångar" },
  { code: "7417", description: "Materiella anläggningstillgångar" },
  { code: "7522", description: "Finansiella anläggningstillgångar" },
];

export default function SRUMappingsPage() {
  const [fiscalYears, setFiscalYears] = useState<FiscalYear[]>([]);
  const [selectedYear, setSelectedYear] = useState<string>("");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [mappings, setMappings] = useState<Record<string, string>>({});
  const [originalMappings, setOriginalMappings] = useState<Record<string, string>>({});
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
    } catch (err) {
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

      // Load existing SRU mappings
      try {
        const mappingsResponse = await api.getSRUMappings(fiscalYearId);
        const mappingsData: Record<string, string> = {};
        mappingsResponse.forEach((m: SRUMapping) => {
          mappingsData[m.account_id] = m.sru_field;
        });
        setMappings(mappingsData);
        setOriginalMappings(mappingsData);
      } catch (err) {
        // No mappings yet is OK
        setMappings({});
        setOriginalMappings({});
      }
      setHasChanges(false);
    } catch (err) {
      setError("Kunde inte ladda konton eller mappningar");
    } finally {
      setLoading(false);
    }
  };

  const handleMappingChange = (accountId: string, sruField: string) => {
    const newMappings = { ...mappings };
    if (sruField === "" || sruField === "__none__") {
      delete newMappings[accountId];
    } else {
      newMappings[accountId] = sruField;
    }
    setMappings(newMappings);
    setHasChanges(JSON.stringify(newMappings) !== JSON.stringify(originalMappings));
  };

  const saveMappings = async () => {
    if (!selectedYear) return;
    
    setSaving(true);
    setError(null);
    setSuccess(null);
    
    try {
      // Prepare bulk update data
      const mappingsList = Object.entries(mappings).map(([accountId, sruField]) => ({
        account_id: accountId,
        sru_field: sruField,
      }));

      await api.bulkUpdateSRUMappings(selectedYear, mappingsList);
      
      setOriginalMappings(mappings);
      setHasChanges(false);
      setSuccess("SRU-mappningarna har sparats");
      
      // Clear success message after 3 seconds
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
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
            {accounts.length} konton. Mappningar sparas från SIE4-import eller kan sättas manuellt.
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
                      <th className="px-4 py-3 text-left font-medium w-[200px]">SRU-fält</th>
                      <th className="px-4 py-3 text-left font-medium w-[300px]">Beskrivning</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {accounts.map((account) => {
                      const currentMapping = mappings[account.id];
                      const originalMapping = originalMappings[account.id];
                      const isChanged = currentMapping !== originalMapping;
                      
                      return (
                        <tr key={account.id} className={isChanged ? "bg-yellow-50/50" : ""}>
                          <td className="px-4 py-3 font-mono">{account.code}</td>
                          <td className="px-4 py-3">{account.name}</td>
                          <td className="px-4 py-3">
                            <select
                              value={currentMapping || ""}
                              onChange={(e) => handleMappingChange(account.id, e.target.value)}
                              className="w-full rounded border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                            >
                              <option value="">Ingen mappning</option>
                              {SRU_FIELDS.map((field) => (
                                <option key={field.code} value={field.code}>
                                  {field.code} - {field.description}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="px-4 py-3">
                            {currentMapping && (
                              <span className="text-muted-foreground">
                                {SRU_FIELDS.find(f => f.code === currentMapping)?.description || "Okänt fält"}
                              </span>
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
                SRU-mappningar kopplar dina bokföringskonton till de fält som används i 
                inkomstdeklarationen (INK2). Om du importerar en SIE4-fil med #SRU-taggar 
                fylls dessa i automatiskt. Du kan också sätta mappningarna manuellt här.
              </p>
              <p className="text-sm text-muted-foreground">
                När du exporterar SRU-filer beräknas summan per fält automatiskt baserat 
                på kontosaldon och dessa mappningar.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
