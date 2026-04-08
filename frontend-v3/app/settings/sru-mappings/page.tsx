"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/useToast";
import { api } from "@/lib/api";
import { 
  ArrowLeft, 
  Save, 
  FileText, 
  AlertTriangle,
  CheckCircle2,
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
  const { toast } = useToast();
  const [fiscalYears, setFiscalYears] = useState<FiscalYear[]>([]);
  const [selectedYear, setSelectedYear] = useState<string>("");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [mappings, setMappings] = useState<Record<string, string>>({});
  const [originalMappings, setOriginalMappings] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

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
      setFiscalYears(response.data || []);
      if (response.data?.length > 0) {
        setSelectedYear(response.data[0].id);
      }
    } catch (error) {
      toast({
        title: "Fel",
        description: "Kunde inte ladda räkenskapsår",
        variant: "destructive",
      });
    }
  };

  const loadAccountsAndMappings = async (fiscalYearId: string) => {
    setLoading(true);
    try {
      // Load accounts
      const accountsResponse = await api.getAccounts();
      setAccounts(accountsResponse.data || []);

      // Load existing SRU mappings
      const mappingsResponse = await api.getSRUMappings(fiscalYearId);
      const mappingsData: Record<string, string> = {};
      mappingsResponse.data?.forEach((m: SRUMapping) => {
        mappingsData[m.account_id] = m.sru_field;
      });
      setMappings(mappingsData);
      setOriginalMappings(mappingsData);
      setHasChanges(false);
    } catch (error) {
      toast({
        title: "Fel",
        description: "Kunde inte ladda konton eller mappningar",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleMappingChange = (accountId: string, sruField: string) => {
    const newMappings = { ...mappings };
    if (sruField === "__none__") {
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
    try {
      // Prepare bulk update data
      const mappingsList = Object.entries(mappings).map(([accountId, sruField]) => ({
        account_id: accountId,
        sru_field: sruField,
      }));

      await api.bulkUpdateSRUMappings(selectedYear, mappingsList);
      
      setOriginalMappings(mappings);
      setHasChanges(false);
      
      toast({
        title: "Sparat",
        description: "SRU-mappningarna har sparats",
      });
    } catch (error) {
      toast({
        title: "Fel",
        description: "Kunde inte spara mappningarna",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  const exportSRU = async () => {
    if (!selectedYear) return;
    
    try {
      const response = await api.exportSRU(selectedYear);
      
      // Download ZIP file
      const blob = new Blob([response.data], { type: "application/zip" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = response.headers["content-disposition"]?.split("filename=")[1]?.replace(/"/g, "") || "INK2_SRU.zip";
      a.click();
      URL.revokeObjectURL(url);
      
      toast({
        title: "Exporterat",
        description: "SRU-filer har laddats ner",
      });
    } catch (error: any) {
      toast({
        title: "Fel",
        description: error.response?.data?.detail || "Export misslyckades",
        variant: "destructive",
      });
    }
  };

  const previewSRU = async () => {
    if (!selectedYear) return;
    
    // Open preview in new window/tab
    window.open(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/export/sru/${selectedYear}/preview`, "_blank");
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

      {/* Fiscal Year Selector */}
      <Card>
        <CardHeader>
          <CardTitle>Räkenskapsår</CardTitle>
          <CardDescription>
            Välj vilket räkenskapsår du vill hantera mappningar för
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Select value={selectedYear} onValueChange={setSelectedYear}>
            <SelectTrigger className="w-full sm:w-[300px]">
              <SelectValue placeholder="Välj räkenskapsår" />
            </SelectTrigger>
            <SelectContent>
              {fiscalYears.map((year) => (
                <SelectItem key={year.id} value={year.id}>
                  {year.name} ({year.start_date} - {year.end_date})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
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
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[100px]">Konto</TableHead>
                    <TableHead>Namn</TableHead>
                    <TableHead className="w-[200px]">SRU-fält</TableHead>
                    <TableHead className="w-[300px]">Beskrivning</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {accounts.map((account) => {
                    const currentMapping = mappings[account.id];
                    const originalMapping = originalMappings[account.id];
                    const isChanged = currentMapping !== originalMapping;
                    
                    return (
                      <TableRow key={account.id} className={isChanged ? "bg-yellow-50/50" : ""}>
                        <TableCell className="font-mono">{account.code}</TableCell>
                        <TableCell>{account.name}</TableCell>
                        <TableCell>
                          <Select
                            value={currentMapping || "__none__"}
                            onValueChange={(value) => handleMappingChange(account.id, value)}
                          >
                            <SelectTrigger className="w-full">
                              <SelectValue placeholder="Välj SRU-fält" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="__none__">Ingen mappning</SelectItem>
                              {SRU_FIELDS.map((field) => (
                                <SelectItem key={field.code} value={field.code}>
                                  {field.code} - {field.description}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </TableCell>
                        <TableCell>
                          {currentMapping && (
                            <span className="text-sm text-muted-foreground">
                              {SRU_FIELDS.find(f => f.code === currentMapping)?.description || "Okänt fält"}
                            </span>
                          )}
                          {isChanged && (
                            <Badge variant="outline" className="ml-2 text-yellow-600 border-yellow-600">
                              Ändrad
                            </Badge>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
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
