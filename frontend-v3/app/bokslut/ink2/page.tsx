"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Building2, Calculator, Calendar, CheckCircle2, Download, FileSpreadsheet, FileText, Map } from "lucide-react";
import { api } from "@/lib/api";
import { useFiscalYears } from "@/hooks/useData";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface SourceAccountValue {
  account: string;
  name?: string;
  value: number;
}

interface SRUField {
  field_number: string;
  description: string;
  value: number;
  source_accounts: string[];
  source_account_values?: SourceAccountValue[];
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

interface DeclarationRow {
  code: string;
  label: string;
  sru?: string;
  value?: (ctx: ReportContext) => number;
  sign?: "+" | "-" | "(+) =" | "(-) =";
  note?: string;
}

interface DeclarationSection {
  title: string;
  rows: DeclarationRow[];
}

interface ReportContext {
  getFieldValue: (fieldNumber: string) => number;
  accountingResult: number;
  taxableResult: number;
}

const TABS = [
  { id: "ink2" as TabType, label: "INK2", icon: FileText, description: "Huvudblankett" },
  { id: "ink2r" as TabType, label: "INK2R", icon: FileSpreadsheet, description: "Räkenskapsschema" },
  { id: "ink2s" as TabType, label: "INK2S", icon: Calculator, description: "Skattemässiga justeringar" },
  { id: "mappings" as TabType, label: "Mappningar", icon: Map, description: "Konto-mappningar" },
];

const INK2_SECTIONS: DeclarationSection[] = [
  {
    title: "Underlag för inkomstskatt",
    rows: [
      { code: "1.1", label: "Överskott av näringsverksamhet", value: ({ taxableResult }) => Math.max(taxableResult, 0) },
      { code: "1.2", label: "Underskott av näringsverksamhet", value: ({ taxableResult }) => Math.min(taxableResult, 0) },
      { code: "1.3", label: "Underskott som inte redovisas i p. 1.2, koncernbidrags- och fusionsspärrat underskott" },
    ],
  },
  {
    title: "Underlag för särskild löneskatt",
    rows: [
      { code: "1.4", label: "Underlag för särskild löneskatt på pensionskostnader" },
      { code: "1.5", label: "Negativt underlag för särskild löneskatt på pensionskostnader" },
    ],
  },
  {
    title: "Underlag för avkastningsskatt",
    rows: [
      { code: "1.6", label: "Underlag för avkastningsskatt 15 %. Försäkringsföretag m.fl. Avsatt till pensioner" },
      { code: "1.7", label: "Underlag för avkastningsskatt 30 %. Försäkringsföretag m.fl. Utländska kapitalförsäkringar" },
    ],
  },
  {
    title: "Underlag för fastighetsavgift",
    rows: [
      { code: "1.8", label: "Småhus, hel avgift" },
      { code: "1.8", label: "Småhus, halv avgift" },
      { code: "1.9", label: "Hyreshus, bostäder, hel avgift" },
      { code: "1.9", label: "Hyreshus, bostäder, halv avgift" },
    ],
  },
  {
    title: "Underlag för fastighetsskatt",
    rows: [
      { code: "1.10", label: "Småhus/ägarlägenhet: tomtmark, byggnad under uppförande" },
      { code: "1.11", label: "Hyreshus: tomtmark, bostäder under uppförande" },
      { code: "1.12", label: "Hyreshus: lokaler" },
      { code: "1.13", label: "Industri/elproduktionsenhet, värmekraftverk (utom vindkraftverk)" },
      { code: "1.14", label: "Elproduktionsenhet, vattenkraftverk" },
      { code: "1.15", label: "Elproduktionsenhet, vindkraftverk" },
    ],
  },
];

const INK2R_SECTIONS: DeclarationSection[] = [
  {
    title: "Tillgångar / Anläggningstillgångar",
    rows: [
      { code: "2.1", label: "Koncessioner, patent, licenser, varumärken, hyresrätter, goodwill och liknande rättigheter", sru: "7416" },
      { code: "2.2", label: "Förskott avseende immateriella anläggningstillgångar" },
      { code: "2.3", label: "Byggnader och mark", sru: "7417" },
      { code: "2.4", label: "Maskiner, inventarier och övriga materiella anläggningstillgångar" },
      { code: "2.5", label: "Förbättringsutgifter på annans fastighet" },
      { code: "2.6", label: "Pågående nyanläggningar och förskott avseende materiella anläggningstillgångar" },
      { code: "2.7", label: "Andelar i koncernföretag", sru: "7522" },
      { code: "2.8", label: "Andelar i intresseföretag" },
      { code: "2.9", label: "Fordringar hos koncern- och intresseföretag" },
      { code: "2.10", label: "Andra långfristiga värdepappersinnehav" },
      { code: "2.11", label: "Lån till delägare eller närstående" },
      { code: "2.12", label: "Andra långfristiga fordringar" },
    ],
  },
  {
    title: "Omsättningstillgångar",
    rows: [
      { code: "2.13", label: "Råvaror och förnödenheter", sru: "7251" },
      { code: "2.14", label: "Varor under tillverkning" },
      { code: "2.15", label: "Färdiga varor och handelsvaror" },
      { code: "2.16", label: "Övriga lagertillgångar" },
      { code: "2.17", label: "Pågående arbeten för annans räkning" },
      { code: "2.18", label: "Förskott till leverantörer" },
      { code: "2.19", label: "Kundfordringar", sru: "7261" },
      { code: "2.20", label: "Fordringar hos koncern- och intresseföretag" },
      { code: "2.21", label: "Övriga fordringar", sru: "7263" },
      { code: "2.22", label: "Upparbetad men ej fakturerad intäkt" },
      { code: "2.23", label: "Förutbetalda kostnader och upplupna intäkter", sru: "7271" },
      { code: "2.24", label: "Andelar i koncernföretag" },
      { code: "2.25", label: "Övriga kortfristiga placeringar" },
      { code: "2.26", label: "Kassa, bank och redovisningsmedel", sru: "7281" },
    ],
  },
  {
    title: "Eget kapital",
    rows: [
      { code: "2.27", label: "Bundet eget kapital", sru: "7301" },
      { code: "2.28", label: "Fritt eget kapital", sru: "7302" },
    ],
  },
  {
    title: "Obeskattade reserver och avsättningar",
    rows: [
      { code: "2.29", label: "Periodiseringsfonder", sru: "7321" },
      { code: "2.30", label: "Ackumulerade överavskrivningar" },
      { code: "2.31", label: "Övriga obeskattade reserver" },
      { code: "2.32", label: "Avsättning för pensioner och liknande förpliktelser enligt lag (1967:531) om tryggande av pensionsutfästelse m.m.", sru: "7350" },
      { code: "2.33", label: "Övriga avsättningar för pensioner och liknande förpliktelser" },
      { code: "2.34", label: "Övriga avsättningar" },
    ],
  },
  {
    title: "Skulder",
    rows: [
      { code: "2.35", label: "Obligationslån", sru: "7365" },
      { code: "2.36", label: "Checkräkningskredit" },
      { code: "2.37", label: "Övriga skulder till kreditinstitut" },
      { code: "2.38", label: "Skulder till koncern- och intresseföretag" },
      { code: "2.39", label: "Övriga skulder" },
      { code: "2.40", label: "Checkräkningskredit" },
      { code: "2.41", label: "Övriga skulder till kreditinstitut" },
      { code: "2.42", label: "Förskott från kunder" },
      { code: "2.43", label: "Pågående arbeten för annans räkning" },
      { code: "2.44", label: "Fakturerad men ej upparbetad intäkt" },
      { code: "2.45", label: "Leverantörsskulder", sru: "7368" },
      { code: "2.46", label: "Växelskulder" },
      { code: "2.47", label: "Skulder till koncern- och intresseföretag" },
      { code: "2.48", label: "Skatteskulder", sru: "7369" },
      { code: "2.49", label: "Övriga skulder", sru: "7370" },
      { code: "2.50", label: "Upplupna kostnader och förutbetalda intäkter" },
    ],
  },
  {
    title: "Resultaträkning",
    rows: [
      { code: "3.1", label: "Nettoomsättning", sru: "7410", sign: "+" },
      { code: "3.2", label: "Förändring av lager av produkter i arbete, färdiga varor och pågående arbete för annans räkning", sru: "7413", sign: "+" },
      { code: "3.3", label: "Aktiverat arbete för egen räkning", sign: "+" },
      { code: "3.4", label: "Övriga rörelseintäkter", sign: "+" },
      { code: "3.5", label: "Råvaror och förnödenheter", sru: "7511", sign: "-" },
      { code: "3.6", label: "Handelsvaror", sign: "-" },
      { code: "3.7", label: "Övriga externa kostnader", sru: "7513", sign: "-" },
      { code: "3.8", label: "Personalkostnader", sru: "7514", sign: "-" },
      { code: "3.9", label: "Av- och nedskrivningar av materiella och immateriella anläggningstillgångar", sru: "7515", sign: "-" },
      { code: "3.10", label: "Nedskrivningar av omsättningstillgångar utöver normala nedskrivningar", sign: "-" },
      { code: "3.11", label: "Övriga rörelsekostnader", sru: "7520", sign: "-" },
      { code: "3.12", label: "Resultat från andelar i koncernföretag", sign: "+" },
      { code: "3.13", label: "Resultat från andelar i intresseföretag", sign: "+" },
      { code: "3.14", label: "Resultat från övriga finansiella anläggningstillgångar", sru: "7525", sign: "+" },
      { code: "3.15", label: "Övriga ränteintäkter och liknande resultatposter", sru: "7528", sign: "+" },
      { code: "3.16", label: "Nedskrivningar av finansiella anläggningstillgångar och kortfristiga placeringar", sign: "-" },
      { code: "3.17", label: "Räntekostnader och liknande resultatposter", sign: "-" },
      { code: "3.18", label: "Extraordinära intäkter", sign: "+" },
      { code: "3.19", label: "Extraordinära kostnader", sign: "-" },
      { code: "3.20", label: "Lämnade koncernbidrag", sign: "-" },
      { code: "3.21", label: "Mottagna koncernbidrag", sign: "+" },
      { code: "3.22", label: "Återföring av periodiseringsfond", sign: "+" },
      { code: "3.23", label: "Avsättning till periodiseringsfond", sign: "-" },
      { code: "3.24", label: "Förändring av överavskrivningar", sign: "+" },
      { code: "3.25", label: "Övriga bokslutsdispositioner", sign: "+" },
      { code: "3.26", label: "Skatt på årets resultat", sign: "-" },
      { code: "3.27", label: "Årets resultat, vinst (flyttas till p. 4.1)", value: ({ accountingResult }) => Math.max(accountingResult, 0), sign: "(+) =" },
      { code: "3.28", label: "Årets resultat, förlust (flyttas till p. 4.2)", value: ({ accountingResult }) => Math.min(accountingResult, 0), sign: "(-) =" },
    ],
  },
];

const INK2S_SECTIONS: DeclarationSection[] = [
  {
    title: "Årets resultat",
    rows: [
      { code: "4.1", label: "Årets resultat, vinst", sru: "7650", sign: "+" },
      { code: "4.2", label: "Årets resultat, förlust", value: ({ accountingResult }) => Math.min(accountingResult, 0), sign: "-" },
    ],
  },
  {
    title: "Bokförda kostnader och intäkter",
    rows: [
      { code: "4.3a", label: "Bokförda kostnader som inte ska dras av: skatt på årets resultat", sru: "7651", sign: "+" },
      { code: "4.3b", label: "Bokförda kostnader som inte ska dras av: nedskrivning av finansiella tillgångar", sign: "+" },
      { code: "4.3c", label: "Bokförda kostnader som inte ska dras av: andra bokförda kostnader", sru: "7653", sign: "+" },
      { code: "4.4a", label: "Kostnader som ska dras av men som inte ingår i det redovisade resultatet: lämnade koncernbidrag", sign: "-" },
      { code: "4.4b", label: "Kostnader som ska dras av men som inte ingår i det redovisade resultatet: andra ej bokförda kostnader", sign: "-" },
      { code: "4.5a", label: "Bokförda intäkter som inte ska tas upp: ackordsvinster", sign: "-" },
      { code: "4.5b", label: "Bokförda intäkter som inte ska tas upp: utdelning", sign: "-" },
      { code: "4.5c", label: "Bokförda intäkter som inte ska tas upp: andra bokförda intäkter", sru: "7754", sign: "-" },
      { code: "4.6a", label: "Intäkter som ska tas upp men som inte ingår i det redovisade resultatet: schablonintäkt på kvarvarande periodiseringsfonder", sru: "7654", sign: "+" },
      { code: "4.6b", label: "Intäkter som ska tas upp men som inte ingår i det redovisade resultatet: schablonintäkt på investeringsfonder", sign: "+" },
      { code: "4.6c", label: "Intäkter som ska tas upp men som inte ingår i det redovisade resultatet: mottagna koncernbidrag", sign: "+" },
      { code: "4.6d", label: "Intäkter som ska tas upp men som inte ingår i det redovisade resultatet: intäkt negativ justerad anskaffningsutgift", sign: "+" },
      { code: "4.6e", label: "Intäkter som ska tas upp men som inte ingår i det redovisade resultatet: andra ej bokförda intäkter", sign: "+" },
    ],
  },
  {
    title: "Övriga skattemässiga justeringar",
    rows: [
      { code: "4.7a", label: "Avyttring av delägarrätter: bokförd vinst", sign: "-" },
      { code: "4.7b", label: "Avyttring av delägarrätter: bokförd förlust", sign: "+" },
      { code: "4.7c", label: "Avyttring av delägarrätter: uppskov med kapitalvinst enligt blankett N4", sign: "-" },
      { code: "4.7d", label: "Avyttring av delägarrätter: återfört uppskov av kapitalvinst enligt blankett N4", sign: "+" },
      { code: "4.7e", label: "Avyttring av delägarrätter: kapitalvinst för beskattningsåret", sign: "+" },
      { code: "4.7f", label: "Avyttring av delägarrätter: kapitalförlust som ska dras av", sign: "-" },
      { code: "4.8a", label: "Andel i handelsbolag: bokförd intäkt/vinst", sign: "-" },
      { code: "4.8b", label: "Andel i handelsbolag: skattemässigt överskott enligt N3B", sign: "+" },
      { code: "4.8c", label: "Andel i handelsbolag: bokförd kostnad/förlust", sign: "+" },
      { code: "4.8d", label: "Andel i handelsbolag: skattemässigt underskott enligt N3B", sign: "-" },
      { code: "4.9", label: "Skattemässig justering av bokfört resultat för avskrivning på byggnader och annan fast egendom samt vid restvärdesavskrivning", sign: "+" },
      { code: "4.10", label: "Skattemässig korrigering av bokfört resultat vid avyttring av näringsfastighet och näringsbostadsrätt", sign: "+" },
      { code: "4.11", label: "Skogs-/substansminskningsavdrag", sign: "-" },
      { code: "4.12", label: "Återföringar vid avyttring av fastighet", sign: "+" },
      { code: "4.13", label: "Andra skattemässiga justeringar av resultatet", sign: "+" },
      { code: "4.14a", label: "Underskott: outnyttjat underskott från föregående år", sign: "-" },
      { code: "4.14b", label: "Underskott: reduktion av underskott med hänsyn till exempelvis ägarförändring eller ackord", sign: "+" },
      { code: "4.15", label: "Överskott (flyttas till p. 1.1)", sru: "7670", sign: "(+) =" },
      { code: "4.16", label: "Underskott (flyttas till p. 1.2)", value: ({ taxableResult }) => Math.min(taxableResult, 0), sign: "(-) =" },
    ],
  },
  {
    title: "Övriga uppgifter",
    rows: [
      { code: "4.17", label: "Årets begärda och tidigare års medgivna värdeminskningsavdrag på byggnader som finns kvar vid beskattningsårets utgång" },
      { code: "4.18", label: "Årets begärda och tidigare års medgivna värdeminskningsavdrag på markanläggningar som finns kvar vid beskattningsårets utgång" },
      { code: "4.19", label: "Vid restvärdesavskrivning: återförda belopp för av- och nedskrivning, försäljning, utrangering" },
      { code: "4.20", label: "Lån från aktieägare (fysisk person) vid beskattningsårets utgång" },
      { code: "4.21", label: "Pensionskostnader (som ingår i p. 3.8)" },
    ],
  },
  {
    title: "Upplysningar om årsredovisningen",
    rows: [
      { code: "JA/NEJ", label: "Uppdragstagare, t.ex. redovisningskonsult, har biträtt vid upprättandet av årsredovisningen" },
      { code: "JA/NEJ", label: "Årsredovisningen har varit föremål för revision" },
    ],
  },
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
  
  const fiscalYears = Array.isArray(fiscalYearsData) ? fiscalYearsData : fiscalYearsData?.fiscal_years || [];

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

  const getFieldValue = (fieldNumber: string): number => {
    const field = sruData?.fields?.find(f => f.field_number === fieldNumber);
    return field?.value ?? 0;
  };

  const getField = (fieldNumber?: string): SRUField | undefined => {
    if (!fieldNumber) return undefined;
    return sruData?.fields?.find(f => f.field_number === fieldNumber);
  };

  const sumFields = (fields: string[]): number => fields.reduce((sum, field) => sum + getFieldValue(field), 0);
  const computedAccountingResult = sumFields(["7410", "7413", "7528"]) - sumFields(["7511", "7513", "7514", "7515", "7520"]);
  const accountingResult = getFieldValue("7650") || computedAccountingResult;
  const taxableResult = getFieldValue("7670") || accountingResult;
  const reportContext: ReportContext = { getFieldValue, accountingResult, taxableResult };

  const formatAmount = (value?: number, options?: { showSign?: boolean }): string => {
    if (!value) return "";
    const sign = options?.showSign ? (value < 0 ? "-" : "+") : "";
    return sign + new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(Math.abs(Math.round(value))) + " kr";
  };

  const rowValue = (row: DeclarationRow): number | undefined => {
    if (row.value) return row.value(reportContext);
    if (row.sru) return getFieldValue(row.sru);
    return undefined;
  };

  const rowSourceAccounts = (row: DeclarationRow): SourceAccountValue[] => {
    const field = getField(row.sru);
    if (field?.source_account_values?.length) {
      return field.source_account_values.filter((account) => account.value !== 0);
    }
    return [];
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
          const value = rowValue(row);
          const hasValue = !!value;
          const accounts = rowSourceAccounts(row);
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
                        {account.value !== 0 && (
                          <span className={account.value < 0 ? "text-destructive" : "text-emerald-600"}>
                            {formatAmount(account.value, { showSign: true })}
                          </span>
                        )}
                      </span>
                    ))}
                  </div>
                )}
                {row.note && <div className="mt-1 text-xs text-muted-foreground">{row.note}</div>}
              </div>
              <div className="col-span-2 flex items-center justify-between gap-2 sm:col-span-1 sm:block sm:text-right">
                {row.sign && <span className="font-mono text-xs text-muted-foreground sm:block">{row.sign}</span>}
                <span className={`font-mono text-sm tabular-nums ${hasValue ? "font-semibold text-foreground" : "text-muted-foreground"}`}>
                  {formatAmount(value)}
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
          <div className="font-mono text-lg font-semibold">{formatAmount(accountingResult)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Skattemässigt resultat</div>
          <div className="font-mono text-lg font-semibold">{formatAmount(taxableResult)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Blankettstruktur</div>
          <div className="text-sm font-medium">SKV 2002, INK2/INK2R/INK2S</div>
        </div>
      </CardContent>
    </Card>
  );

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
                onChange={(e) => setSelectedYear(e.target.value)}
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
          <Button onClick={handleExport} disabled={!sruData || exporting} className="gap-2">
            <Download className="h-4 w-4" />
            {exporting ? "Exporterar..." : "Ladda ner SRU"}
          </Button>
        </div>
      </div>

      {sruData && (
        <Card className="border-primary/20 bg-gradient-to-r from-primary/10 to-primary/5">
          <CardContent className="p-4">
            <div className="flex flex-wrap items-center gap-6 text-sm">
              <div className="flex items-center gap-2">
                <Building2 className="h-5 w-5 text-primary" />
                <div>
                  <span className="block text-xs text-muted-foreground">Företag</span>
                  <span className="font-semibold text-foreground">{sruData.company?.name || "Företagsnamn saknas"}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-primary" />
                <div>
                  <span className="block text-xs text-muted-foreground">Organisationsnummer</span>
                  <span className="font-mono text-foreground">{sruData.company?.org_number || "-"}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Calendar className="h-5 w-5 text-primary" />
                <div>
                  <span className="block text-xs text-muted-foreground">Räkenskapsår</span>
                  <span className="text-foreground">
                    {sruData.fiscal_year?.start && sruData.fiscal_year?.end
                      ? `${formatDate(sruData.fiscal_year.start)} - ${formatDate(sruData.fiscal_year.end)}`
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

      {sruData?.validation?.warnings && sruData.validation.warnings.length > 0 && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-4">
          <h4 className="mb-2 font-semibold text-amber-600">Varningar</h4>
          <ul className="space-y-1 text-sm text-amber-700">
            {sruData.validation.warnings.map((warning, idx) => (
              <li key={idx}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="border-b border-border">
        <nav className="flex space-x-1 overflow-x-auto" aria-label="Tabs">
          {TABS.map((tab) => {
            const Icon = tab.icon;
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

      {loading && (
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <div className="grid gap-4 md:grid-cols-2">
            <Skeleton className="h-96" />
            <Skeleton className="h-96" />
          </div>
        </div>
      )}

      {!loading && sruData && activeTab === "ink2" && (
        <div className="space-y-4">
          {renderSummaryCard()}
          {renderDeclarationSections(INK2_SECTIONS)}
        </div>
      )}

      {!loading && sruData && activeTab === "ink2r" && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>INK2R - Räkenskapsschema</CardTitle>
              <CardDescription>Balansräkning och resultaträkning med Skatteverkets fältnummer 2.1-3.28.</CardDescription>
            </CardHeader>
          </Card>
          {renderDeclarationSections(INK2R_SECTIONS)}
        </div>
      )}

      {!loading && sruData && activeTab === "ink2s" && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>INK2S - Skattemässiga justeringar</CardTitle>
              <CardDescription>
                Fält 4.1-4.21 enligt blanketten. Tomma justeringsfält visas för att rapporten ska följa blankettens struktur.
              </CardDescription>
            </CardHeader>
          </Card>
          {renderDeclarationSections(INK2S_SECTIONS)}
        </div>
      )}

      {!loading && activeTab === "mappings" && sruData && (
        <div className="space-y-6">
          <Card className="border-2 border-border shadow-lg">
            <CardHeader className="border-b border-border bg-muted">
              <CardTitle className="text-lg font-bold text-foreground">SRU-mappningar</CardTitle>
              <CardDescription>Konton mappade till INK2-fält</CardDescription>
            </CardHeader>
            <CardContent className="p-6">
              <div className="grid gap-6 md:grid-cols-2">
                {[
                  { title: "Tillgångar (1xxx)", filter: ([account]: [string, string]) => account >= "1000" && account < "2000" },
                  { title: "Eget kapital och skulder (2xxx)", filter: ([account]: [string, string]) => account >= "2000" && account < "3000" },
                  { title: "Intäkter (3xxx)", filter: ([account]: [string, string]) => account >= "3000" && account < "4000" },
                  { title: "Kostnader (4xxx-8xxx)", filter: ([account]: [string, string]) => account >= "4000" && account < "9000" },
                ].map(section => (
                  <div key={section.title}>
                    <h3 className="mb-3 rounded bg-muted px-2 py-1 text-sm font-bold uppercase tracking-wide text-foreground">
                      {section.title}
                    </h3>
                    <div className="max-h-96 space-y-2 overflow-y-auto">
                      {Object.entries(mappings)
                        .filter(section.filter)
                        .sort(([a], [b]) => a.localeCompare(b))
                        .map(([account, field]) => (
                          <div key={account} className="flex items-center justify-between rounded border border-border/50 bg-background px-3 py-2">
                            <span className="font-mono text-sm text-muted-foreground">{account}</span>
                            <span className="font-mono text-sm font-medium text-primary">{field}</span>
                          </div>
                        ))}
                    </div>
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
