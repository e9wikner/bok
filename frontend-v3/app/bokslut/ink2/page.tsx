"use client";

import { useState, useEffect } from "react";
import type { ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
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

type FormRow = {
  code: string;
  label: string;
  field?: string;
  value?: number;
  sign?: "+" | "-" | "(+) =" | "(-) =";
  heading?: string;
  tall?: boolean;
  indent?: boolean;
};

const TABS = [
  { id: "ink2" as TabType, label: "INK2", icon: FileText, description: "Huvudblankett" },
  { id: "ink2r" as TabType, label: "INK2R", icon: FileSpreadsheet, description: "Räkenskapsschema" },
  { id: "ink2s" as TabType, label: "INK2S", icon: Calculator, description: "Skattemässiga justeringar" },
  { id: "mappings" as TabType, label: "Mappningar", icon: Map, description: "Konto-mappningar" },
];

const INK2_MAIN_ROWS: FormRow[] = [
  { code: "1.1", label: "Överskott av näringsverksamhet" },
  { code: "1.2", label: "Underskott av näringsverksamhet" },
  { code: "1.3", label: "Underskott som inte redovisas i p. 1.2, koncernbidrags- och fusionsspärrat underskott" },
];

const PAYROLL_TAX_ROWS: FormRow[] = [
  { code: "1.4", label: "Underlag för särskild löneskatt på pensionskostnader" },
  { code: "1.5", label: "Negativt underlag för särskild löneskatt på pensionskostnader" },
];

const YIELD_TAX_ROWS: FormRow[] = [
  { code: "1.6", label: "Underlag för avkastningsskatt 15 %. Försäkringsföretag m.fl. Avsatt till pensioner", tall: true },
  { code: "1.7", label: "Underlag för avkastningsskatt 30 %. Försäkringsföretag m.fl. Utländska kapitalförsäkringar", tall: true },
];

const PROPERTY_FEE_ROWS: FormRow[] = [
  { code: "1.8", label: "Småhus hel avgift" },
  { code: "1.8", label: "Småhus halv avgift" },
  { code: "1.9", label: "Hyreshus, bostäder hel avgift" },
  { code: "1.9", label: "Hyreshus, bostäder halv avgift" },
];

const PROPERTY_TAX_ROWS: FormRow[] = [
  { code: "1.10", label: "Småhus/ägarlägenhet: tomtmark, byggnad under uppförande", tall: true },
  { code: "1.11", label: "Hyreshus: tomtmark, bostäder under uppförande", tall: true },
  { code: "1.12", label: "Hyreshus: lokaler" },
  { code: "1.13", label: "Industri/elproduktionsenhet, värmekraftverk (utom vindkraftverk)", tall: true },
  { code: "1.14", label: "Elproduktionsenhet, vattenkraftverk" },
  { code: "1.15", label: "Elproduktionsenhet, vindkraftverk" },
];

const INK2R_ASSET_ROWS: FormRow[] = [
  { code: "", label: "Immateriella anläggningstillgångar", heading: "Tillgångar/Anläggningstillgångar" },
  { code: "2.1", label: "Koncessioner, patent, licenser, varumärken, hyresrätter, goodwill och liknande rättigheter", field: "7416", tall: true },
  { code: "2.2", label: "Förskott avseende immateriella anläggningstillgångar" },
  { code: "", label: "Materiella anläggningstillgångar" },
  { code: "2.3", label: "Byggnader och mark", field: "7417" },
  { code: "2.4", label: "Maskiner, inventarier och övriga materiella anläggningstillgångar" },
  { code: "2.5", label: "Förbättringsutgifter på annans fastighet" },
  { code: "2.6", label: "Pågående nyanläggningar och förskott avseende materiella anläggningstillgångar", tall: true },
  { code: "", label: "Finansiella anläggningstillgångar" },
  { code: "2.7", label: "Andelar i koncernföretag", field: "7522" },
  { code: "2.8", label: "Andelar i intresseföretag" },
  { code: "2.9", label: "Fordringar hos koncern- och intresseföretag", tall: true },
  { code: "2.10", label: "Andra långfristiga värdepappersinnehav" },
  { code: "2.11", label: "Lån till delägare eller närstående" },
  { code: "2.12", label: "Andra långfristiga fordringar" },
  { code: "", label: "Varulager", heading: "Omsättningstillgångar" },
  { code: "2.13", label: "Råvaror och förnödenheter", field: "7251" },
  { code: "2.14", label: "Varor under tillverkning" },
  { code: "2.15", label: "Färdiga varor och handelsvaror" },
  { code: "2.16", label: "Övriga lagertillgångar" },
  { code: "2.17", label: "Pågående arbeten för annans räkning" },
  { code: "2.18", label: "Förskott till leverantörer" },
  { code: "", label: "Kortfristiga fordringar" },
  { code: "2.19", label: "Kundfordringar", field: "7261" },
  { code: "2.20", label: "Fordringar hos koncern- och intresseföretag", tall: true },
  { code: "2.21", label: "Övriga fordringar", field: "7263" },
  { code: "2.22", label: "Upparbetad men ej fakturerad intäkt" },
  { code: "2.23", label: "Förutbetalda kostnader och upplupna intäkter", field: "7271", tall: true },
  { code: "", label: "Kortfristiga placeringar" },
  { code: "2.24", label: "Andelar i koncernföretag" },
  { code: "2.25", label: "Övriga kortfristiga placeringar" },
  { code: "", label: "Kassa och bank" },
  { code: "2.26", label: "Kassa, bank och redovisningsmedel", field: "7281" },
];

const INK2R_EQUITY_ROWS: FormRow[] = [
  { code: "2.27", label: "Bundet eget kapital", field: "7301" },
  { code: "2.28", label: "Fritt eget kapital", field: "7302" },
];

const INK2R_RESERVE_ROWS: FormRow[] = [
  { code: "", label: "Obeskattade reserver" },
  { code: "2.29", label: "Periodiseringsfonder", field: "7321" },
  { code: "2.30", label: "Ackumulerade överavskrivningar" },
  { code: "2.31", label: "Övriga obeskattade reserver" },
  { code: "", label: "Avsättningar" },
  { code: "2.32", label: "Avsättning för pensioner och liknande förpliktelser enligt lag (1967:531) om tryggande av pensionsutfästelse m.m.", field: "7350", tall: true },
  { code: "2.33", label: "Övriga avsättningar för pensioner och liknande förpliktelser", tall: true },
  { code: "2.34", label: "Övriga avsättningar" },
];

const INK2R_DEBT_ROWS: FormRow[] = [
  { code: "", label: "Långfristiga skulder" },
  { code: "2.35", label: "Obligationslån", field: "7365" },
  { code: "2.36", label: "Checkräkningskredit" },
  { code: "2.37", label: "Övriga skulder till kreditinstitut" },
  { code: "2.38", label: "Skulder till koncern- och intresseföretag" },
  { code: "2.39", label: "Övriga skulder" },
  { code: "", label: "Kortfristiga skulder" },
  { code: "2.40", label: "Checkräkningskredit" },
  { code: "2.41", label: "Övriga skulder till kreditinstitut" },
  { code: "2.42", label: "Förskott från kunder" },
  { code: "2.43", label: "Pågående arbeten för annans räkning" },
  { code: "2.44", label: "Fakturerad men ej upparbetad intäkt" },
  { code: "2.45", label: "Leverantörsskulder", field: "7368" },
  { code: "2.46", label: "Växelskulder" },
  { code: "2.47", label: "Skulder till koncern- och intresseföretag" },
  { code: "2.48", label: "Skatteskulder", field: "7369" },
  { code: "2.49", label: "Övriga skulder", field: "7370" },
  { code: "2.50", label: "Upplupna kostnader och förutbetalda intäkter", tall: true },
];

const INK2R_RESULT_LEFT_ROWS: FormRow[] = [
  { code: "3.1", label: "Nettoomsättning", field: "7410", sign: "+" },
  { code: "3.2", label: "Förändring av lager av produkter i arbete, färdiga varor och pågående arbete för annans räkning", field: "7413", sign: "+", tall: true },
  { code: "3.3", label: "Aktiverat arbete för egen räkning", sign: "+" },
  { code: "3.4", label: "Övriga rörelseintäkter", sign: "+" },
  { code: "3.5", label: "Råvaror och förnödenheter", field: "7511", sign: "-" },
  { code: "3.6", label: "Handelsvaror", sign: "-" },
  { code: "3.7", label: "Övriga externa kostnader", field: "7513", sign: "-" },
  { code: "3.8", label: "Personalkostnader", field: "7514", sign: "-" },
  { code: "3.9", label: "Av- och nedskrivningar av materiella och immateriella anläggningstillgångar", field: "7515", sign: "-", tall: true },
  { code: "3.10", label: "Nedskrivningar av omsättningstillgångar utöver normala nedskrivningar", sign: "-", tall: true },
  { code: "3.11", label: "Övriga rörelsekostnader", field: "7520", sign: "-" },
  { code: "3.12", label: "Resultat från andelar i koncernföretag", sign: "+", tall: true },
  { code: "3.13", label: "Resultat från andelar i intresseföretag", sign: "+", tall: true },
  { code: "3.14", label: "Resultat från övriga finansiella anläggningstillgångar", field: "7525", sign: "+", tall: true },
];

const INK2R_RESULT_RIGHT_ROWS: FormRow[] = [
  { code: "3.15", label: "Övriga ränteintäkter och liknande resultatposter", field: "7528", sign: "+" },
  { code: "3.16", label: "Nedskrivningar av finansiella anläggningstillgångar och kortfristiga placeringar", sign: "-", tall: true },
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
];

const INK2S_LEFT_ROWS: FormRow[] = [
  { code: "4.1", label: "Årets resultat, vinst", sign: "+", value: 0 },
  { code: "4.2", label: "Årets resultat, förlust", sign: "-", value: 0 },
  { code: "4.3", label: "Bokförda kostnader som inte ska dras av" },
  { code: "a.", label: "Skatt på årets resultat", sign: "+", indent: true },
  { code: "b.", label: "Nedskrivning av finansiella tillgångar", sign: "+", indent: true },
  { code: "c.", label: "Andra bokförda kostnader", sign: "+", indent: true },
  { code: "4.4", label: "Kostnader som ska dras av men som inte ingår i det redovisade resultatet" },
  { code: "a.", label: "Lämnade koncernbidrag", sign: "-", indent: true },
  { code: "b.", label: "Andra ej bokförda kostnader", sign: "-", indent: true },
  { code: "4.5", label: "Bokförda intäkter som inte ska tas upp" },
  { code: "a.", label: "Ackordsvinster", sign: "-", indent: true },
  { code: "b.", label: "Utdelning", sign: "-", indent: true },
  { code: "c.", label: "Andra bokförda intäkter", sign: "-", indent: true },
  { code: "4.6", label: "Intäkter som ska tas upp men som inte ingår i det redovisade resultatet" },
  { code: "a.", label: "Beräknad schablonintäkt på kvarvarande periodiseringsfonder vid beskattningsårets ingång", sign: "+", indent: true, tall: true },
  { code: "b.", label: "Beräknad schablonintäkt på investeringsfonder ägda vid ingången av kalenderåret", sign: "+", indent: true, tall: true },
  { code: "c.", label: "Mottagna koncernbidrag", sign: "+", indent: true },
  { code: "d.", label: "Intäkt negativ justerad anskaffningsutgift", sign: "+", indent: true },
  { code: "e.", label: "Andra ej bokförda intäkter", sign: "+", indent: true },
  { code: "4.7", label: "Avyttring av delägarrätter" },
  { code: "a.", label: "Bokförd vinst", sign: "-", indent: true },
  { code: "b.", label: "Bokförd förlust", sign: "+", indent: true },
  { code: "c.", label: "Uppskov med kapitalvinst enligt blankett N4", sign: "-", indent: true },
  { code: "d.", label: "Återfört uppskov av kapitalvinst enligt blankett N4", sign: "+", indent: true },
  { code: "e.", label: "Kapitalvinst för beskattningsåret", sign: "+", indent: true },
  { code: "f.", label: "Kapitalförlust som ska dras av", sign: "-", indent: true },
  { code: "4.8", label: "Andel i handelsbolag (inkl. avyttring)" },
  { code: "a.", label: "Bokförd intäkt/vinst", sign: "-", indent: true },
  { code: "b.", label: "Skattemässigt överskott enligt N3B", sign: "+", indent: true },
  { code: "c.", label: "Bokförd kostnad/förlust", sign: "+", indent: true },
  { code: "d.", label: "Skattemässigt underskott enligt N3B", sign: "-", indent: true },
  { code: "4.9", label: "Skattemässig justering av bokfört resultat för avskrivning på byggnader och annan fast egendom samt vid restvärdesavskrivning på maskiner och inventarier", sign: "+", tall: true },
];

const INK2S_RIGHT_ROWS: FormRow[] = [
  { code: "4.10", label: "Skattemässig korrigering av bokfört resultat vid avyttring av näringsfastighet och näringsbostadsrätt", sign: "+", tall: true },
  { code: "4.11", label: "Skogs-/substansminskningsavdrag (specificeras på blankett N8)", sign: "-" },
  { code: "4.12", label: "Återföringar vid avyttring av fastighet, t.ex. värdeminskningsavdrag, skogsavdrag och substansminskningsavdrag", sign: "+", tall: true },
  { code: "4.13", label: "Andra skattemässiga justeringar av resultatet", sign: "+" },
  { code: "4.14", label: "Underskott" },
  { code: "a.", label: "Outnyttjat underskott från föregående år", sign: "-", indent: true },
  { code: "b.", label: "Reduktion av underskott med hänsyn till exempelvis ägarförändring eller ackord", sign: "+", indent: true, tall: true },
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

  const sumFields = (fields: string[]): number => {
    return fields.reduce((sum, field) => sum + getFieldValue(field), 0);
  };

  const revenueFields = ["7410", "7413", "7528"];
  const expenseFields = ["7511", "7513", "7514", "7515", "7520"];
  const accountingResult = sumFields(revenueFields) - sumFields(expenseFields);
  const taxableResult = accountingResult;

  const formatFormValue = (value?: number): string => {
    if (!value) return "";
    return new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(Math.abs(Math.round(value)));
  };

  const rowValue = (row: FormRow): number | undefined => {
    if (row.value !== undefined) return row.value;
    if (!row.field) return undefined;
    return getFieldValue(row.field);
  };

  const formatDate = (dateStr: string): string => {
    if (!dateStr || dateStr.length !== 8) return dateStr;
    return `${dateStr.substring(0, 4)}-${dateStr.substring(4, 6)}-${dateStr.substring(6, 8)}`;
  };

  const formDates = {
    start: formatDate(sruData?.fiscal_year?.start || ""),
    end: formatDate(sruData?.fiscal_year?.end || ""),
  };

  const renderFormRow = (row: FormRow, key: string) => {
    if (!row.code && !row.field && !row.sign && !row.value) {
      return (
        <tr key={key} className="border-x border-black">
          <td colSpan={3} className="px-1 pt-1 text-[13px] font-bold leading-tight">{row.label}</td>
        </tr>
      );
    }
    return (
      <tr key={key} className={`border-x border-b border-black ${row.tall ? "h-[44px]" : "h-[32px]"}`}>
        <td className={`px-1 align-middle text-[12px] leading-[1.05] ${row.indent ? "pl-7" : ""}`}>
          <span className="font-bold">{row.code}</span>{row.code ? " " : ""}{row.label}
        </td>
        <td className="w-7 border-l border-black text-center text-[13px] align-middle">{row.sign || ""}</td>
        <td className="w-[128px] border-l border-black px-2 text-right align-middle font-mono text-[13px]">
          {formatFormValue(rowValue(row))}
        </td>
      </tr>
    );
  };

  const renderFormTable = (rows: FormRow[]) => (
    <table className="w-full table-fixed border-t border-black">
      <tbody>{rows.map((row, index) => renderFormRow(row, `${row.code}-${row.label}-${index}`))}</tbody>
    </table>
  );

  const renderTwoFieldHeader = () => (
    <div className="grid grid-cols-[160px_1fr_1fr] border border-black text-[12px]">
      <div className="flex items-end px-1 pb-1 text-[18px]">Räkenskapsår</div>
      <div className="border-l border-black">
        <div className="-mt-5 h-5 text-[12px]">Fr.o.m.</div>
        <div className="px-2 pt-5 font-mono text-[13px]">{formDates.start}</div>
      </div>
      <div className="border-l border-black">
        <div className="-mt-5 h-5 text-[12px]">T.o.m.</div>
        <div className="px-2 pt-5 font-mono text-[13px]">{formDates.end}</div>
      </div>
    </div>
  );

  const SkatteverketBrand = () => (
    <div className="flex items-center gap-3">
      <div className="relative h-9 w-11">
        <div className="absolute left-1 top-4 h-5 w-8 rotate-[-28deg] rounded-t-full border-[5px] border-b-0 border-black" />
        <div className="absolute left-2 top-2 h-5 w-8 rotate-[28deg] rounded-t-full border-[5px] border-b-0 border-black" />
        <div className="absolute left-4 top-1 h-7 w-5 rounded-t-full border-[5px] border-b-0 border-black" />
      </div>
      <div className="text-[28px] font-bold tracking-tight">Skatteverket</div>
    </div>
  );

  const Barcode = ({ label }: { label: string }) => (
    <div className="text-center">
      <div className="mx-auto flex h-12 w-72 items-end gap-[2px]">
        {Array.from({ length: 54 }).map((_, index) => (
          <span
            key={index}
            className="block bg-black"
            style={{
              width: index % 5 === 0 ? 3 : index % 3 === 0 ? 2 : 1,
              height: index % 7 === 0 ? 48 : index % 4 === 0 ? 42 : 36,
            }}
          />
        ))}
      </div>
      <div className="font-mono text-[14px] tracking-[0.18em]">{label}</div>
    </div>
  );

  const PageFrame = ({ children, sideCode, barcode }: { children: ReactNode; sideCode: string; barcode: string }) => (
    <div className="relative mx-auto min-h-[1123px] w-[794px] bg-white px-[58px] py-[42px] text-black shadow-xl ring-1 ring-black/10 print:shadow-none">
      <div className="absolute bottom-24 left-8 flex origin-bottom-left -rotate-90 items-center gap-8 text-[14px]">
        <span>SKV</span><span>2002</span><span>23</span><span>{sideCode}</span><span>W 12-12</span>
      </div>
      {children}
      <div className="absolute bottom-10 right-12">
        <Barcode label={barcode} />
      </div>
    </div>
  );

  const renderInk2Page = () => (
    <PageFrame sideCode="01" barcode="INK2M-1-23-2013P3">
      <div className="grid grid-cols-[1fr_1.02fr] gap-10">
        <div><SkatteverketBrand /></div>
        <div>
          <div className="text-[29px] font-bold leading-[0.9]">Inkomstdeklaration 2</div>
          <div className="flex items-start justify-between">
            <div className="text-[20px] font-bold leading-tight">Aktiebolag, ekonomisk förening m.fl.</div>
            <div className="text-[20px] font-bold">Utg 23</div>
          </div>
          <div className="grid grid-cols-[1fr_44px] border border-black text-[12px]">
            <div className="h-12 px-1">Organisationsnummer<div className="font-mono text-[13px]">{sruData?.company?.org_number}</div></div>
            <div className="row-span-2 flex items-center justify-center border-l border-black text-2xl font-bold">M</div>
            <div className="grid grid-cols-[1fr_1fr_1fr] border-t border-black">
              <div className="flex items-end px-1 pb-1 text-[18px]">Räkenskapsår</div>
              <div className="border-l border-black px-1">Fr.o.m.<div className="font-mono text-[13px]">{formDates.start}</div></div>
              <div className="border-l border-black px-1">T.o.m.<div className="font-mono text-[13px]">{formDates.end}</div></div>
            </div>
          </div>
          <div className="text-[12px]">Namn (firma) adress</div>
          <div className="font-mono text-[13px]">{sruData?.company?.name}</div>
        </div>
      </div>

      <div className="mt-14 grid grid-cols-[1fr_1.03fr] gap-3">
        <div>
          <div className="mb-24 text-[15px] leading-tight">
            <div>Skatteverket</div>
            <div className="mt-2 text-[18px]">0771-567 567</div>
            <p className="mt-7">Information om hur man fyller i blanketten finns i broschyren Skatteregler för aktie- och handelsbolag, SKV 294.</p>
            <p className="mt-1">Ange belopp i hela krontal.</p>
            <div className="mt-7 h-16 rounded-[2px] border border-black px-1 text-[12px]">Datum då blanketten fylls i</div>
          </div>
          <h2 className="mb-1 text-[21px] font-bold">Underlag för inkomstskatt</h2>
          {renderFormTable(INK2_MAIN_ROWS.map(row => {
            if (row.code === "1.1") return { ...row, value: taxableResult > 0 ? taxableResult : 0 };
            if (row.code === "1.2") return { ...row, value: taxableResult < 0 ? taxableResult : 0 };
            return row;
          }))}
          <h2 className="mb-1 mt-6 text-[21px] font-bold">Underlag för fastighetsavgift</h2>
          {renderFormTable(PROPERTY_FEE_ROWS)}
        </div>
        <div className="pt-[278px]">
          <h2 className="mb-1 text-[21px] font-bold">Underlag för särskild löneskatt</h2>
          {renderFormTable(PAYROLL_TAX_ROWS)}
          <h2 className="mb-1 mt-4 text-[21px] font-bold">Underlag för avkastningsskatt</h2>
          {renderFormTable(YIELD_TAX_ROWS)}
          <h2 className="mb-1 mt-4 text-[21px] font-bold">Underlag för fastighetsskatt</h2>
          {renderFormTable(PROPERTY_TAX_ROWS)}
        </div>
      </div>

      <div className="absolute bottom-28 left-[58px] right-[312px]">
        <h2 className="mb-1 text-[21px] font-bold">Underskrift</h2>
        <div className="h-24 border border-black text-[12px]">
          <div className="h-12 px-1">Behörig firmatecknares namnteckning</div>
          <div className="grid h-12 grid-cols-2 border-t border-black">
            <div className="px-1">Namnförtydligande</div>
            <div className="border-l border-black px-1">Telefonnummer</div>
          </div>
        </div>
      </div>
      <div className="absolute bottom-28 right-[58px] w-[240px]">
        <h2 className="mb-1 text-[21px] font-bold">Övriga upplysningar</h2>
        <div className="flex h-16 border border-black text-[12px] leading-tight">
          <div className="mt-auto h-5 w-6 border-r border-t border-black" />
          <div className="p-2">Upplysningar kan bara lämnas i särskild skrivelse. Kryssa här om övrig upplysning lämnats.</div>
        </div>
      </div>
      <div className="absolute bottom-9 left-[58px] text-[14px] font-bold">www.skatteverket.se</div>
    </PageFrame>
  );

  const renderInk2rPages = () => (
    <div className="space-y-8">
      <PageFrame sideCode="02" barcode="INK2RM-1-23-2013P3">
        <div className="grid grid-cols-[1fr_1.03fr] gap-3">
          <div><SkatteverketBrand /></div>
          <div className="text-right">
            <div className="text-[28px] font-bold leading-[0.9]">Räkenskapsschema</div>
            <div className="flex items-start justify-between">
              <div className="text-left text-[22px] font-bold leading-tight">Inkomstdeklaration 2</div>
              <div>
                <div className="text-[30px] font-bold">INK2R</div>
                <div className="text-[22px] font-bold">Utg 23</div>
              </div>
            </div>
          </div>
        </div>
        <div className="mt-8 grid grid-cols-[1fr_1.03fr] gap-3">
          <div>{renderTwoFieldHeader()}</div>
          <div className="grid grid-cols-2 border border-black text-[12px]">
            <div className="h-12 px-1">Organisationsnummer<div className="font-mono text-[13px]">{sruData?.company?.org_number}</div></div>
            <div className="border-l border-black px-1">Datum då blanketten fylls i</div>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-[1fr_1.03fr] gap-3">
          <div>{renderFormTable(INK2R_ASSET_ROWS)}</div>
          <div>
            <h2 className="mb-1 text-[21px] font-bold">Eget kapital</h2>
            {renderFormTable(INK2R_EQUITY_ROWS)}
            <h2 className="mb-1 mt-4 text-[21px] font-bold">Obeskattade reserver och avsättningar</h2>
            {renderFormTable(INK2R_RESERVE_ROWS)}
            <h2 className="mb-1 mt-4 text-[21px] font-bold">Skulder</h2>
            {renderFormTable(INK2R_DEBT_ROWS)}
          </div>
        </div>
      </PageFrame>
      <PageFrame sideCode="03" barcode="INK2RM-2-23-2013P3">
        <div className="grid grid-cols-[1fr_1.03fr] gap-3">
          <div>{renderTwoFieldHeader()}</div>
          <div className="grid grid-cols-2 border border-black text-[12px]">
            <div className="h-12 px-1">Organisationsnummer<div className="font-mono text-[13px]">{sruData?.company?.org_number}</div></div>
            <div className="border-l border-black px-1">Datum då blanketten fylls i</div>
          </div>
        </div>
        <div className="mt-16 grid grid-cols-[1fr_1.03fr] gap-3">
          <div>
            <h2 className="mb-1 text-[21px] font-bold">Resultaträkning</h2>
            {renderFormTable(INK2R_RESULT_LEFT_ROWS)}
          </div>
          <div>
            <h2 className="mb-1 text-[21px] font-bold">Resultaträkning (forts.)</h2>
            {renderFormTable([
              ...INK2R_RESULT_RIGHT_ROWS,
              { code: "3.27", label: "Årets resultat, vinst (flyttas till p. 4.1)", value: accountingResult > 0 ? accountingResult : 0, sign: "(+) =" },
              { code: "3.28", label: "Årets resultat, förlust (flyttas till p. 4.2)", value: accountingResult < 0 ? accountingResult : 0, sign: "(-) =" },
            ])}
          </div>
        </div>
      </PageFrame>
    </div>
  );

  const renderInk2sPage = () => (
    <PageFrame sideCode="04" barcode="INK2SM-1-23-2013P3">
      <div className="grid grid-cols-[1fr_1.03fr] gap-3">
        <div><SkatteverketBrand /></div>
        <div className="text-right">
          <div className="text-[28px] font-bold leading-[0.95]">Skattemässiga justeringar</div>
          <div className="flex items-start justify-between">
            <div className="text-left text-[22px] font-bold leading-tight">Inkomstdeklaration 2</div>
            <div>
              <div className="text-[30px] font-bold">INK2S</div>
              <div className="text-[22px] font-bold">Utg 23</div>
            </div>
          </div>
        </div>
      </div>
      <div className="mt-8 grid grid-cols-[1fr_1.03fr] gap-3">
        <div>{renderTwoFieldHeader()}</div>
        <div className="grid grid-cols-2 border border-black text-[12px]">
          <div className="h-12 px-1">Organisationsnummer<div className="font-mono text-[13px]">{sruData?.company?.org_number}</div></div>
          <div className="border-l border-black px-1">Datum då blanketten fylls i</div>
        </div>
      </div>
      <div className="mt-10 grid grid-cols-[1fr_1.03fr] gap-3">
        <div>{renderFormTable(INK2S_LEFT_ROWS.map(row => {
          if (row.code === "4.1") return { ...row, value: accountingResult > 0 ? accountingResult : 0 };
          if (row.code === "4.2") return { ...row, value: accountingResult < 0 ? accountingResult : 0 };
          return row;
        }))}</div>
        <div>
          {renderFormTable([
            ...INK2S_RIGHT_ROWS,
            { code: "4.15", label: "Överskott (flyttas till p. 1.1 på sid. 1)", value: taxableResult > 0 ? taxableResult : 0, sign: "(+) =" },
            { code: "4.16", label: "Underskott (flyttas till p. 1.2 på sid. 1)", value: taxableResult < 0 ? taxableResult : 0, sign: "(-) =" },
          ])}
          <h2 className="mb-1 mt-8 text-[21px] font-bold">Övriga uppgifter</h2>
          {renderFormTable([
            { code: "4.17", label: "Årets begärda och tidigare års medgivna värdeminskningsavdrag på byggnader som finns kvar vid beskattningsårets utgång", tall: true },
            { code: "4.18", label: "Årets begärda och tidigare års medgivna värdeminskningsavdrag på markanläggningar som finns kvar vid beskattningsårets utgång", tall: true },
            { code: "4.19", label: "Vid restvärdesavskrivning: återförda belopp för av- och nedskrivning, försäljning, utrangering", tall: true },
            { code: "4.20", label: "Lån från aktieägare (fysisk person) vid beskattningsårets utgång" },
            { code: "4.21", label: "Pensionskostnader (som ingår i p. 3.8)" },
          ])}
          <h2 className="mb-1 mt-14 text-[21px] font-bold">Upplysningar om årsredovisningen</h2>
          <div className="border border-black text-[12px]">
            <div className="px-1">Uppdragstagare (t.ex. redovisningskonsult) har biträtt vid upprättandet av årsredovisningen</div>
            <div className="grid grid-cols-4 border-t border-black">
              <div className="h-7 border-r border-black px-1"><span className="inline-block h-5 w-5 border border-black align-middle" /> Ja</div>
              <div className="h-7 px-1"><span className="inline-block h-5 w-5 border border-black align-middle" /> Nej</div>
            </div>
            <div className="border-t border-black px-1">Årsredovisningen har varit föremål för revision</div>
            <div className="grid grid-cols-4 border-t border-black">
              <div className="h-7 border-r border-black px-1"><span className="inline-block h-5 w-5 border border-black align-middle" /> Ja</div>
              <div className="h-7 px-1"><span className="inline-block h-5 w-5 border border-black align-middle" /> Nej</div>
            </div>
          </div>
        </div>
      </div>
    </PageFrame>
  );

  return (
    <div className="space-y-6">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Inkomstdeklaration 2</h1>
          <p className="text-sm text-muted-foreground">Blankettförhandsvisning enligt Skatteverkets SKV 2002-layout.</p>
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
                  <option key={fy.id} value={fy.id}>Räkenskapsår {new Date(fy.start_date).getFullYear()}</option>
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
        <div className="mx-auto max-w-6xl rounded-lg border border-primary/20 bg-primary/10 p-4">
          <div className="flex flex-wrap items-center gap-6 text-sm">
            <div className="flex items-center gap-2">
              <Building2 className="h-5 w-5 text-primary" />
              <div><span className="block text-xs text-muted-foreground">Företag</span><span className="font-semibold">{sruData.company?.name || "Företagsnamn saknas"}</span></div>
            </div>
            <div className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              <div><span className="block text-xs text-muted-foreground">Organisationsnummer</span><span className="font-mono">{sruData.company?.org_number || "-"}</span></div>
            </div>
            <div className="flex items-center gap-2">
              <Calendar className="h-5 w-5 text-primary" />
              <div><span className="block text-xs text-muted-foreground">Räkenskapsår</span><span>{formDates.start && formDates.end ? `${formDates.start} - ${formDates.end}` : "-"}</span></div>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="mx-auto flex max-w-6xl items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/10 px-4 py-3 text-destructive">
          <AlertCircle className="h-5 w-5" />{error}
        </div>
      )}
      {success && (
        <div className="mx-auto flex max-w-6xl items-center gap-2 rounded-lg border border-green-500/20 bg-green-500/10 px-4 py-3 text-green-600">
          <CheckCircle2 className="h-5 w-5" />{success}
        </div>
      )}

      <div className="mx-auto max-w-6xl border-b border-border">
        <nav className="flex space-x-1 overflow-x-auto" aria-label="Tabs">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
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
        <div className="mx-auto max-w-6xl space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-[720px] w-full" />
        </div>
      )}

      {!loading && activeTab !== "mappings" && sruData && (
        <div className="overflow-x-auto bg-neutral-200 py-8">
          {activeTab === "ink2" && renderInk2Page()}
          {activeTab === "ink2r" && renderInk2rPages()}
          {activeTab === "ink2s" && renderInk2sPage()}
        </div>
      )}

      {!loading && activeTab === "mappings" && sruData && (
        <div className="mx-auto max-w-6xl space-y-6">
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
                    <h3 className="mb-3 rounded bg-muted px-2 py-1 text-sm font-bold uppercase tracking-wide text-foreground">{section.title}</h3>
                    <div className="max-h-96 space-y-2 overflow-y-auto">
                      {Object.entries(mappings).filter(section.filter).sort(([a], [b]) => a.localeCompare(b)).map(([account, field]) => (
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
