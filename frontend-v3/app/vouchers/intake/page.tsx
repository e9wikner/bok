"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Clock,
  ExternalLink,
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
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useBankInputConnections, useIntakeWorkspace } from "@/hooks/useData";
import { api } from "@/lib/api";
import type { IntakeKind, IntakeStatus, IntakeWorkspaceItem } from "@/lib/api";
import { formatDate } from "@/lib/utils";

type UploadStatus = "idle" | "uploading" | "success" | "error";
type StatusFilter = "all" | Exclude<IntakeStatus, "deleted">;
type KindFilter = "all" | IntakeKind;

const PAGE_SIZE = 15;

const sourceTypeOptions = [
  { value: "receipt", label: "Kvitto" },
  { value: "supplier_invoice", label: "Leverantörsfaktura" },
  { value: "customer_invoice", label: "Kundfaktura" },
  { value: "reimbursement", label: "Utlägg/ersättning" },
  { value: "other", label: "Annat" },
];

const uploadErrorMessage =
  "Uppladdningen misslyckades. Kontrollera filtyp, bankkonto och att filen inte redan finns i intaget.";

const statusFilters: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "Alla" },
  { value: "pending", label: "Väntar" },
  { value: "processing", label: "Bearbetas" },
  { value: "processed", label: "Klara" },
  { value: "skipped", label: "Hoppade över" },
  { value: "failed", label: "Misslyckade" },
  { value: "needs_attention", label: "Behöver granskas" },
];

const kindFilters: { value: KindFilter; label: string }[] = [
  { value: "all", label: "Alla typer" },
  { value: "voucher_source", label: "Underlag" },
  { value: "bank_input", label: "Bankfil" },
];

const statusLabels: Record<Exclude<IntakeStatus, "deleted">, string> = {
  pending: "Väntar",
  processing: "Bearbetas",
  processed: "Klar",
  skipped: "Hoppad över",
  failed: "Misslyckad",
  needs_attention: "Behöver granskas",
};

export default function IntakePage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  const [page, setPage] = useState(0);
  const { data: bankConnectionsData, isLoading: bankConnectionsLoading } =
    useBankInputConnections();
  const bankConnections = bankConnectionsData?.items || [];
  const { data: workspaceData, isLoading: workspaceLoading } =
    useIntakeWorkspace({
      status: statusFilter === "all" ? undefined : statusFilter,
      kind: kindFilter === "all" ? undefined : kindFilter,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    });
  const intakeItems = workspaceData?.items || [];
  const total = workspaceData?.total || 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const allStatusCount = Object.values(workspaceData?.status_counts || {}).reduce(
    (sum, count) => sum + count,
    0
  );

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

      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold uppercase text-muted-foreground">
              Status
            </span>
            {statusFilters.map((filter) => {
              const count =
                filter.value === "all"
                  ? allStatusCount || total
                  : workspaceData?.status_counts?.[filter.value] || 0;
              return (
                <Button
                  key={filter.value}
                  variant={statusFilter === filter.value ? "default" : "outline"}
                  size="sm"
                  onClick={() => {
                    setStatusFilter(filter.value);
                    setPage(0);
                  }}
                >
                  {filter.label}
                  <span className="ml-2 text-xs opacity-70">{count}</span>
                </Button>
              );
            })}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold uppercase text-muted-foreground">
              Typ
            </span>
            {kindFilters.map((filter) => (
              <Button
                key={filter.value}
                variant={kindFilter === filter.value ? "default" : "outline"}
                size="sm"
                onClick={() => {
                  setKindFilter(filter.value);
                  setPage(0);
                }}
              >
                {filter.label}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {workspaceLoading ? (
            <div className="p-6 space-y-3">
              {[...Array(8)].map((_, index) => (
                <Skeleton key={index} className="h-12 w-full" />
              ))}
            </div>
          ) : intakeItems.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px] table-fixed text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left p-4 font-medium text-muted-foreground">
                      Typ
                    </th>
                    <th className="text-left p-4 font-medium text-muted-foreground">
                      Uppladdad/fil
                    </th>
                    <th className="text-left p-4 font-medium text-muted-foreground">
                      Status
                    </th>
                    <th className="text-left p-4 font-medium text-muted-foreground">
                      Detalj
                    </th>
                    <th className="text-right p-4 font-medium text-muted-foreground">
                      Åtgärd
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {intakeItems.map((item) => (
                    <tr
                      key={`${item.kind}-${item.id}`}
                      className="border-b last:border-0 hover:bg-muted/30 transition-colors"
                    >
                      <td className="p-4">
                        <TypeBadge item={item} />
                      </td>
                      <td className="p-4">
                        <div className="space-y-1">
                          <p
                            className="max-w-[260px] truncate font-medium"
                            title={item.original_filename}
                          >
                            {item.original_filename}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {formatDate(item.uploaded_at)}
                          </p>
                        </div>
                      </td>
                      <td className="p-4">
                        <StatusBadge status={item.status} />
                      </td>
                      <td className="p-4">
                        <StatusDetail item={item} />
                      </td>
                      <td className="p-4 text-right">
                        <RowActions item={item} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-12 text-center text-muted-foreground">
              <FileText className="h-12 w-12 mx-auto mb-4 opacity-30" />
              <h2 className="text-lg font-semibold text-foreground">
                Inga underlag i intaget
              </h2>
              <p className="mt-2 text-sm">
                Ladda upp ett kvitto, en faktura eller en bankfil för att ge
                agenten nytt material att bokföra.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {total > 0 && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">
            Visar {page * PAGE_SIZE + 1}-
            {Math.min((page + 1) * PAGE_SIZE, total)} av {total}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((value) => Math.max(0, value - 1))}
              disabled={page === 0}
              aria-label="Föregående sida"
              title="Föregående sida"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="min-w-12 text-center text-sm">
              {page + 1} / {Math.max(totalPages, 1)}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                setPage((value) => Math.min(totalPages - 1, value + 1))
              }
              disabled={page >= totalPages - 1}
              aria-label="Nästa sida"
              title="Nästa sida"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
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

function TypeBadge({ item }: { item: IntakeWorkspaceItem }) {
  const isBankInput = item.kind === "bank_input";
  return (
    <Badge variant="outline" className="gap-1.5">
      {isBankInput ? (
        <Landmark className="h-3 w-3" />
      ) : (
        <FileText className="h-3 w-3" />
      )}
      {isBankInput ? "Bankfil" : "Underlag"}
    </Badge>
  );
}

function StatusBadge({ status }: { status: IntakeStatus }) {
  if (status === "deleted") {
    return <Badge variant="outline">Borttagen</Badge>;
  }

  const variant =
    status === "processed"
      ? "success"
      : status === "failed"
      ? "destructive"
      : status === "needs_attention"
      ? "warning"
      : status === "pending"
      ? "secondary"
      : "outline";

  return (
    <Badge variant={variant} className="gap-1.5">
      {status === "processing" && <Clock className="h-3 w-3" />}
      {statusLabels[status]}
    </Badge>
  );
}

function StatusDetail({ item }: { item: IntakeWorkspaceItem }) {
  const text = getStatusDetail(item);

  if (item.status === "processed" && item.linked_voucher_ids[0]) {
    return (
      <Link
        href={`/vouchers/${item.linked_voucher_ids[0]}`}
        className="text-primary hover:underline"
      >
        {text}
      </Link>
    );
  }

  return (
    <span
      className="block max-w-[360px] truncate text-muted-foreground"
      title={text}
    >
      {text}
    </span>
  );
}

function RowActions({ item }: { item: IntakeWorkspaceItem }) {
  const detailHref = `/vouchers/intake/${item.kind}/${item.id}`;
  const linkedVoucherId = item.linked_voucher_ids[0];

  if (item.status === "processed" && linkedVoucherId) {
    return (
      <div className="flex flex-wrap justify-end gap-2">
        <Link href={`/vouchers/${linkedVoucherId}`}>
          <Button size="sm" className="gap-1.5 whitespace-nowrap">
            <ExternalLink className="h-3.5 w-3.5" />
            Öppna verifikation
          </Button>
        </Link>
        <Link href={detailHref}>
          <Button
            variant="outline"
            size="sm"
            className="whitespace-nowrap"
          >
            Visa intagspost
          </Button>
        </Link>
      </div>
    );
  }

  if (item.status === "failed") {
    return (
      <Link href={detailHref}>
        <Button size="sm" className="gap-1.5 whitespace-nowrap">
          <AlertTriangle className="h-3.5 w-3.5" />
          Granska fel
        </Button>
      </Link>
    );
  }

  if (item.status === "needs_attention") {
    return (
      <Link href={detailHref}>
        <Button size="sm" className="gap-1.5 whitespace-nowrap">
          <AlertTriangle className="h-3.5 w-3.5" />
          Granska underlag
        </Button>
      </Link>
    );
  }

  return (
    <Link href={detailHref}>
      <Button variant="outline" size="sm" className="whitespace-nowrap">
        Visa intagspost
      </Button>
    </Link>
  );
}

function getStatusDetail(item: IntakeWorkspaceItem) {
  if (item.kind === "bank_input") {
    if (item.status === "processed") {
      return `${item.imported_count} importerade, ${item.skipped_count} hoppade över`;
    }
    if (item.status === "failed") {
      return item.parse_error || "Bankfilen kunde inte tolkas.";
    }
    if (item.status === "needs_attention") {
      return item.parse_error || "Bankfilen behöver granskas.";
    }
    if (item.status === "skipped") {
      return `${item.skipped_count} rader hoppades över`;
    }
  }

  if (item.kind === "voucher_source") {
    if (item.status === "processed") {
      return item.linked_voucher_ids[0]
        ? `Verifikation ${item.linked_voucher_ids[0]}`
        : item.latest_processing_summary || "Bearbetat utan länkad verifikation";
    }
    if (item.status === "failed") {
      return (
        item.latest_error_detail ||
        item.latest_processing_summary ||
        "Underlaget kunde inte bearbetas."
      );
    }
    if (item.status === "needs_attention") {
      return item.latest_error_detail || "Underlaget behöver granskas.";
    }
    if (item.status === "skipped") {
      return item.latest_processing_summary || "Underlaget hoppades över.";
    }
  }

  if (item.status === "processing") {
    return "Agenten arbetar med posten.";
  }
  if (item.status === "pending") {
    return "Väntar på agentens bearbetning.";
  }
  return "Ingen detalj tillgänglig.";
}
