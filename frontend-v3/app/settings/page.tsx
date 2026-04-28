"use client";

import { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useHealth } from "@/hooks/useData";
import { api, CompanyInfo } from "@/lib/api";
import { useDarkMode } from "@/hooks/useDarkMode";
import {
  Upload,
  FileUp,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Download,
  Server,
  Sun,
  Moon,
  Monitor,
  FileText,
  Settings2,
  Building2,
} from "lucide-react";
import Link from "next/link";

export default function SettingsPage() {
  const { data: health } = useHealth();
  const { isDark, toggle } = useDarkMode();
  const [companyInfo, setCompanyInfo] = useState<CompanyInfo>({
    name: "",
    org_number: "",
    contact_name: "",
    address: "",
    postnr: "",
    postort: "",
    email: "",
    phone: "",
  });
  const [companyStatus, setCompanyStatus] = useState<"idle" | "loading" | "saving" | "success" | "error">("loading");
  const [companyMessage, setCompanyMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    const loadCompanyInfo = async () => {
      setCompanyStatus("loading");
      try {
        const data = await api.getCompanyInfo();
        if (!cancelled) {
          setCompanyInfo({
            name: data.name || "",
            org_number: data.org_number || "",
            contact_name: data.contact_name || "",
            address: data.address || "",
            postnr: data.postnr || "",
            postort: data.postort || "",
            email: data.email || "",
            phone: data.phone || "",
          });
          setCompanyStatus("idle");
        }
      } catch (err: any) {
        if (!cancelled) {
          setCompanyStatus("error");
          setCompanyMessage(err?.response?.data?.detail || "Kunde inte läsa företagsuppgifter");
        }
      }
    };

    loadCompanyInfo();
    return () => {
      cancelled = true;
    };
  }, []);

  const updateCompanyField = (key: keyof CompanyInfo, value: string) => {
    setCompanyInfo((current) => ({ ...current, [key]: value }));
  };

  const saveCompanyInfo = async () => {
    setCompanyStatus("saving");
    setCompanyMessage("");
    try {
      const saved = await api.updateCompanyInfo(companyInfo);
      setCompanyInfo({
        name: saved.name || "",
        org_number: saved.org_number || "",
        contact_name: saved.contact_name || "",
        address: saved.address || "",
        postnr: saved.postnr || "",
        postort: saved.postort || "",
        email: saved.email || "",
        phone: saved.phone || "",
      });
      setCompanyStatus("success");
      setCompanyMessage("Företagsuppgifter sparade");
      setTimeout(() => {
        setCompanyStatus("idle");
        setCompanyMessage("");
      }, 2500);
    } catch (err: any) {
      setCompanyStatus("error");
      setCompanyMessage(err?.response?.data?.detail || "Kunde inte spara företagsuppgifter");
    }
  };

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1000px] mx-auto">
      <div>
        <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">
          Inställningar
        </h1>
        <p className="text-muted-foreground mt-1">
          Systemkonfiguration och dataimport
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-primary" />
            Företagsuppgifter
          </CardTitle>
          <CardDescription>
            Används i rapporter, SIE-export och SRU-filer
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Field
              label="Företagsnamn"
              value={companyInfo.name}
              onChange={(value) => updateCompanyField("name", value)}
              disabled={companyStatus === "loading" || companyStatus === "saving"}
            />
            <Field
              label="Organisationsnummer"
              value={companyInfo.org_number}
              onChange={(value) => updateCompanyField("org_number", value)}
              disabled={companyStatus === "loading" || companyStatus === "saving"}
            />
            <Field
              label="Kontaktperson"
              value={companyInfo.contact_name || ""}
              onChange={(value) => updateCompanyField("contact_name", value)}
              disabled={companyStatus === "loading" || companyStatus === "saving"}
            />
            <Field
              label="E-post"
              value={companyInfo.email || ""}
              onChange={(value) => updateCompanyField("email", value)}
              disabled={companyStatus === "loading" || companyStatus === "saving"}
            />
            <Field
              label="Adress"
              value={companyInfo.address || ""}
              onChange={(value) => updateCompanyField("address", value)}
              disabled={companyStatus === "loading" || companyStatus === "saving"}
            />
            <Field
              label="Telefon"
              value={companyInfo.phone || ""}
              onChange={(value) => updateCompanyField("phone", value)}
              disabled={companyStatus === "loading" || companyStatus === "saving"}
            />
            <Field
              label="Postnummer"
              value={companyInfo.postnr || ""}
              onChange={(value) => updateCompanyField("postnr", value)}
              disabled={companyStatus === "loading" || companyStatus === "saving"}
            />
            <Field
              label="Postort"
              value={companyInfo.postort || ""}
              onChange={(value) => updateCompanyField("postort", value)}
              disabled={companyStatus === "loading" || companyStatus === "saving"}
            />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={saveCompanyInfo} disabled={companyStatus === "loading" || companyStatus === "saving"}>
              {companyStatus === "saving" ? "Sparar..." : "Spara företagsuppgifter"}
            </Button>
            {companyMessage && (
              <span className={`text-sm ${companyStatus === "error" ? "text-destructive" : "text-emerald-600"}`}>
                {companyMessage}
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Appearance / Dark mode */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Monitor className="h-5 w-5 text-primary" />
            Utseende
          </CardTitle>
          <CardDescription>
            Välj mellan ljust och mörkt läge
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <button
              onClick={() => { if (isDark) toggle(); }}
              className={`flex items-center gap-2 px-4 py-3 rounded-lg border-2 transition-colors ${
                !isDark
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-primary/50"
              }`}
            >
              <Sun className="h-5 w-5 text-amber-500" />
              <div className="text-left">
                <p className="text-sm font-medium">Ljust</p>
              </div>
            </button>
            <button
              onClick={() => { if (!isDark) toggle(); }}
              className={`flex items-center gap-2 px-4 py-3 rounded-lg border-2 transition-colors ${
                isDark
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-primary/50"
              }`}
            >
              <Moon className="h-5 w-5 text-blue-500" />
              <div className="text-left">
                <p className="text-sm font-medium">Mörkt</p>
              </div>
            </button>
          </div>
        </CardContent>
      </Card>

      {/* API Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Server className="h-5 w-5 text-primary" />
            Systemstatus
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              {health ? (
                <>
                  <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                  <div>
                    <p className="font-medium">API-server online</p>
                    <p className="text-sm text-muted-foreground">
                      {process.env.NEXT_PUBLIC_API_URL || (typeof window !== "undefined" ? window.location.origin : "")}
                    </p>
                  </div>
                </>
              ) : (
                <>
                  <XCircle className="h-5 w-5 text-red-500" />
                  <div>
                    <p className="font-medium">Ingen anslutning</p>
                    <p className="text-sm text-muted-foreground">
                      Kontrollera att API-servern är igång
                    </p>
                  </div>
                </>
              )}
            </div>
            {health && (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-2 border-t">
                <div>
                  <p className="text-xs text-muted-foreground">Version</p>
                  <p className="text-sm font-mono">{health.version || "-"}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Commit</p>
                  <p className="text-sm font-mono">{health.commit || "-"}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Service</p>
                  <p className="text-sm font-mono">{health.service || "-"}</p>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Tax Declaration (SRU) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-primary" />
            Deklaration (SRU)
          </CardTitle>
          <CardDescription>
            Hantera SRU-mappningar för inkomstdeklaration
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3">
            <Link href="/settings/sru-mappings">
              <Button variant="outline" className="gap-2">
                <Settings2 className="h-4 w-4" />
                SRU-mappningar
              </Button>
            </Link>
          </div>
        </CardContent>
      </Card>

      {/* File Import */}
      <FileImportCard
        title="Importera SIE4"
        description="Importera bokföringsdata i SIE4-format"
        accept=".se,.si,.sie"
        onUpload={api.importSie4}
      />
      <FileImportCard
        title="Importera CSV"
        description="Importera banktransaktioner från CSV-fil"
        accept=".csv"
        onUpload={api.importCsv}
      />

      {/* Export */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Download className="h-5 w-5 text-primary" />
            Exportera data
          </CardTitle>
          <CardDescription>
            Exportera bokföringsdata i SIE4-format
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant="outline"
            onClick={async () => {
              try {
                const data = await api.exportSie4();
                const blob = new Blob([data], { type: "text/plain" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "export.se";
                a.click();
                URL.revokeObjectURL(url);
              } catch {
                console.error("Kunde inte exportera data");
              }
            }}
            className="gap-2"
          >
            <Download className="h-4 w-4" />
            Ladda ner SIE4
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const id = label.toLowerCase().replace(/\s+/g, "-");
  return (
    <label htmlFor={id} className="space-y-1.5">
      <span className="text-sm font-medium text-foreground">{label}</span>
      <input
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-primary disabled:cursor-not-allowed disabled:opacity-60"
      />
    </label>
  );
}

function FileImportCard({
  title,
  description,
  accept,
  onUpload,
}: {
  title: string;
  description: string;
  accept: string;
  onUpload: (file: File) => Promise<any>;
}) {
  const [status, setStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");
  const [dragOver, setDragOver] = useState(false);

  const handleFile = useCallback(
    async (file: File) => {
      setStatus("uploading");
      setMessage("");
      try {
        const result = await onUpload(file);
        setStatus("success");
        setMessage(
          result?.message ||
            `Importerade ${result?.imported_count || ""} poster`
        );
      } catch (err: any) {
        setStatus("error");
        setMessage(err?.response?.data?.detail || "Import misslyckades");
      }
    },
    [onUpload]
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileUp className="h-5 w-5 text-primary" />
          {title}
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const file = e.dataTransfer.files[0];
            if (file) handleFile(file);
          }}
          className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
            dragOver
              ? "border-primary bg-primary/5"
              : "border-border hover:border-primary/50"
          }`}
        >
          <Upload className="h-8 w-8 mx-auto mb-3 text-muted-foreground" />
          <p className="text-sm text-muted-foreground mb-3">
            Dra och släpp en fil här, eller
          </p>
          <label>
            <input
              type="file"
              accept={accept}
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFile(file);
              }}
            />
            <span className="inline-flex items-center justify-center rounded-lg font-medium text-sm h-8 px-3 border border-input bg-background hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer">
              Välj fil
            </span>
          </label>
        </div>

        {status !== "idle" && (
          <div className="mt-4 flex items-center gap-2">
            {status === "uploading" && (
              <>
                <div className="h-4 w-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                <span className="text-sm">Importerar...</span>
              </>
            )}
            {status === "success" && (
              <>
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span className="text-sm text-emerald-600">{message}</span>
              </>
            )}
            {status === "error" && (
              <>
                <AlertTriangle className="h-4 w-4 text-red-500" />
                <span className="text-sm text-red-600">{message}</span>
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
