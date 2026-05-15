"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Landmark,
  Upload,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useBankInputConnections } from "@/hooks/useData";
import { api } from "@/lib/api";

type UploadStatus = "idle" | "uploading" | "success" | "error";

const sourceTypeOptions = [
  { value: "receipt", label: "Kvitto" },
  { value: "supplier_invoice", label: "Leverantörsfaktura" },
  { value: "customer_invoice", label: "Kundfaktura" },
  { value: "reimbursement", label: "Utlägg/ersättning" },
  { value: "other", label: "Annat" },
];

const uploadErrorMessage =
  "Uppladdningen misslyckades. Kontrollera filtyp, bankkonto och att filen inte redan finns i intaget.";

export default function IntakePage() {
  const queryClient = useQueryClient();
  const { data: bankConnectionsData, isLoading: bankConnectionsLoading } =
    useBankInputConnections();
  const bankConnections = bankConnectionsData?.items || [];

  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [sourceFileInputKey, setSourceFileInputKey] = useState(0);
  const [sourceType, setSourceType] = useState("receipt");
  const [explanation, setExplanation] = useState("");
  const [sourceUploadStatus, setSourceUploadStatus] =
    useState<UploadStatus>("idle");
  const [sourceMessage, setSourceMessage] = useState("");

  const [bankFile, setBankFile] = useState<File | null>(null);
  const [bankFileInputKey, setBankFileInputKey] = useState(0);
  const [bankConnectionId, setBankConnectionId] = useState("");
  const [bankUploadStatus, setBankUploadStatus] =
    useState<UploadStatus>("idle");
  const [bankMessage, setBankMessage] = useState("");

  async function refreshWorkspace() {
    await queryClient.invalidateQueries({ queryKey: ["intake-workspace"] });
  }

  async function uploadSource() {
    if (!sourceFile) return;

    setSourceUploadStatus("uploading");
    setSourceMessage("");
    try {
      await api.uploadIntakeSource({
        file: sourceFile,
        source_type: sourceType,
        explanation: explanation.trim() || undefined,
      });
      await refreshWorkspace();
      setSourceUploadStatus("success");
      setSourceMessage("Underlaget har lagts till i intaget.");
      setSourceFile(null);
      setSourceFileInputKey((value) => value + 1);
      setSourceType("receipt");
      setExplanation("");
    } catch {
      setSourceUploadStatus("error");
      setSourceMessage(uploadErrorMessage);
    }
  }

  async function uploadBankInput() {
    if (!bankFile || !bankConnectionId) return;

    setBankUploadStatus("uploading");
    setBankMessage("");
    try {
      await api.uploadBankInput({
        file: bankFile,
        bank_connection_id: bankConnectionId,
      });
      await refreshWorkspace();
      setBankUploadStatus("success");
      setBankMessage("Bankfilen har lagts till i intaget.");
      setBankFile(null);
      setBankFileInputKey((value) => value + 1);
      setBankConnectionId("");
    } catch {
      setBankUploadStatus("error");
      setBankMessage(uploadErrorMessage);
    }
  }

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1400px] mx-auto">
      <div>
        <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">
          Intag
        </h1>
        <p className="text-muted-foreground mt-1">
          Ladda upp underlag och följ agentens bokföringsarbete.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              Verifikationsunderlag
            </CardTitle>
            <CardDescription>
              Kvitton, fakturor och annat material som agenten ska bokföra.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <label className="space-y-1.5 block" htmlFor="source-file">
              <span className="text-sm font-medium text-foreground">Fil</span>
              <input
                key={sourceFileInputKey}
                id="source-file"
                type="file"
                accept=".pdf,image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
                onChange={(event) =>
                  setSourceFile(event.target.files?.[0] || null)
                }
                className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground file:mr-3 file:rounded-md file:border-0 file:bg-secondary file:px-3 file:py-1.5 file:text-sm file:font-medium focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </label>

            <label className="space-y-1.5 block" htmlFor="source_type">
              <span className="text-sm font-medium text-foreground">Typ</span>
              <select
                id="source_type"
                value={sourceType}
                onChange={(event) => setSourceType(event.target.value)}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none transition-colors focus:ring-2 focus:ring-ring"
              >
                {sourceTypeOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="space-y-1.5 block" htmlFor="source-explanation">
              <span className="text-sm font-medium text-foreground">
                Kort förklaring
              </span>
              <textarea
                id="source-explanation"
                value={explanation}
                onChange={(event) => setExplanation(event.target.value)}
                rows={3}
                placeholder="Exempel: betald med företagskort eller privat utlägg"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:ring-2 focus:ring-ring"
              />
            </label>

            <div className="flex flex-wrap items-center gap-3">
              <Button
                onClick={uploadSource}
                disabled={!sourceFile || sourceUploadStatus === "uploading"}
                className="gap-2"
              >
                <Upload className="h-4 w-4" />
                {sourceUploadStatus === "uploading"
                  ? "Laddar upp..."
                  : "Ladda upp underlag"}
              </Button>
              <UploadMessage status={sourceUploadStatus} message={sourceMessage} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Landmark className="h-5 w-5 text-primary" />
              Bankfil
            </CardTitle>
            <CardDescription>
              CSV-filer från banken som agenten kan matcha mot bokföringen.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <label className="space-y-1.5 block" htmlFor="bank-file">
              <span className="text-sm font-medium text-foreground">CSV-fil</span>
              <input
                key={bankFileInputKey}
                id="bank-file"
                type="file"
                accept=".csv,text/csv"
                onChange={(event) =>
                  setBankFile(event.target.files?.[0] || null)
                }
                className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground file:mr-3 file:rounded-md file:border-0 file:bg-secondary file:px-3 file:py-1.5 file:text-sm file:font-medium focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </label>

            <label className="space-y-1.5 block" htmlFor="bank-connection">
              <span className="text-sm font-medium text-foreground">
                Bankkonto
              </span>
              <select
                id="bank-connection"
                value={bankConnectionId}
                onChange={(event) => setBankConnectionId(event.target.value)}
                disabled={bankConnectionsLoading}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none transition-colors focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
              >
                <option value="">
                  {bankConnectionsLoading ? "Läser bankkonton..." : "Välj bankkonto"}
                </option>
                {bankConnections.map((connection) => (
                  <option key={connection.id} value={connection.id}>
                    {connection.account_number || connection.iban || connection.id} -{" "}
                    {connection.bank_name}
                  </option>
                ))}
              </select>
            </label>

            <div className="flex flex-wrap items-center gap-3">
              <Button
                onClick={uploadBankInput}
                disabled={
                  !bankFile ||
                  !bankConnectionId ||
                  bankUploadStatus === "uploading"
                }
                className="gap-2"
              >
                <Upload className="h-4 w-4" />
                {bankUploadStatus === "uploading"
                  ? "Laddar upp..."
                  : "Ladda upp bankfil"}
              </Button>
              <UploadMessage status={bankUploadStatus} message={bankMessage} />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function UploadMessage({
  status,
  message,
}: {
  status: UploadStatus;
  message: string;
}) {
  if (status === "idle" || !message) return null;

  const isError = status === "error";

  return (
    <span
      className={`inline-flex items-center gap-2 text-sm ${
        isError ? "text-destructive" : "text-emerald-600"
      }`}
    >
      {isError ? (
        <AlertTriangle className="h-4 w-4" />
      ) : (
        <CheckCircle2 className="h-4 w-4" />
      )}
      {message}
    </span>
  );
}
