"use client";

import { useParams } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { useState, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useVoucher, useAccounts, useVoucherSourceContext } from "@/hooks/useData";
import { api } from "@/lib/api";
import type { IntakeStatus, VoucherSourceContext } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import {
  ArrowLeft,
  FileText,
  Calendar,
  Hash,
  Brain,
  Pencil,
  History,
  CheckCircle2,
  AlertTriangle,
  X,
  Save,
  Paperclip,
  Upload,
  FileImage,
  File,
  Trash2,
  Download,
  ExternalLink,
  Landmark,
} from "lucide-react";

const intakeStatusLabels: Record<IntakeStatus, string> = {
  pending: "Väntar",
  processing: "Bearbetas",
  processed: "Klar",
  skipped: "Hoppad över",
  failed: "Misslyckad",
  needs_attention: "Behöver granskas",
  deleted: "Borttagen",
};

const sourceTypeLabels: Record<string, string> = {
  receipt: "Kvitto",
  supplier_invoice: "Leverantörsfaktura",
  customer_invoice: "Kundfaktura",
  reimbursement: "Utlägg/ersättning",
  other: "Annat",
};

export default function VoucherDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { data: voucher, isLoading } = useVoucher(id);
  const { data: accountsData } = useAccounts();
  const { data: sourceContext, isLoading: sourceContextLoading } =
    useVoucherSourceContext(id);
  const accounts = accountsData?.accounts || [];

  // Audit trail
  const { data: auditData } = useQuery({
    queryKey: ["voucher-audit", id],
    queryFn: () => api.getVoucherAudit(id),
    staleTime: 5 * 60 * 1000,
  });

  // Attachments
  const { data: attachmentsData, refetch: refetchAttachments } = useQuery({
    queryKey: ["voucher-attachments", id],
    queryFn: () => api.getVoucherAttachments(id),
    staleTime: 5 * 60 * 1000,
  });

  // Correction state
  const [isEditing, setIsEditing] = useState(false);
  const [editedRows, setEditedRows] = useState<any[]>([]);
  const [correctionReason, setCorrectionReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<{
    ok: boolean;
    msg: string;
  } | null>(null);

  // Upload state
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const handleFileUpload = useCallback(
    async (file: globalThis.File) => {
      setUploading(true);
      try {
        await api.uploadVoucherAttachment(id, file);
        refetchAttachments();
      } catch {
        console.error("Kunde inte ladda upp filen");
      } finally {
        setUploading(false);
      }
    },
    [id, refetchAttachments]
  );

  const openSourceFile = useCallback(
    async (source: VoucherSourceContext["source_material"][number]) => {
      const target = window.open("", "_blank", "noopener,noreferrer");
      const blob = await api.getIntakeFile(source.kind, source.id);
      const objectUrl = URL.createObjectURL(blob);
      if (target) {
        target.location.href = objectUrl;
      } else {
        window.open(objectUrl, "_blank", "noopener,noreferrer");
      }
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
    },
    []
  );

  const handleDeleteAttachment = async (attachmentId: string) => {
    if (!confirm("Ta bort denna bilaga?")) return;
    try {
      await api.deleteVoucherAttachment(id, attachmentId);
      refetchAttachments();
    } catch {
      console.error("Kunde inte ta bort bilagan");
    }
  };

  if (isLoading) {
    return (
      <div className="p-4 lg:p-8 space-y-6 max-w-[1000px] mx-auto">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!voucher) {
    return (
      <div className="p-4 lg:p-8 max-w-[1000px] mx-auto">
        <p className="text-muted-foreground">Verifikationen hittades inte.</p>
        <Link
          href="/vouchers"
          className="text-primary hover:underline mt-2 inline-block"
        >
          Tillbaka till verifikationer
        </Link>
      </div>
    );
  }

  const totalDebit = voucher.rows?.reduce(
    (s: number, r: any) => s + (r.debit || 0),
    0
  );
  const totalCredit = voucher.rows?.reduce(
    (s: number, r: any) => s + (r.credit || 0),
    0
  );
  const isBalanced = Math.abs((totalDebit || 0) - (totalCredit || 0)) < 0.01;
  const auditEntries = auditData?.entries || [];
  const attachmentsList = attachmentsData?.attachments || [];
  const sourceMaterials = sourceContext?.source_material || [];
  const processingNotes = sourceContext?.processing_notes || [];
  const correctionChain = sourceContext?.correction_chain || [];
  const showCorrectionChain = correctionChain.length > 0 || !!voucher.correction_of;

  const startEditing = () => {
    setEditedRows(
      voucher.rows.map((r: any) => ({
        account_code: r.account_code,
        debit: r.debit || 0,
        credit: r.credit || 0,
        description: r.description || "",
      }))
    );
    setIsEditing(true);
    setSaveResult(null);
  };

  const cancelEditing = () => {
    setIsEditing(false);
    setEditedRows([]);
    setCorrectionReason("");
    setSaveResult(null);
  };

  const updateRow = (index: number, field: string, value: any) => {
    setEditedRows((prev) =>
      prev.map((r, i) => (i === index ? { ...r, [field]: value } : r))
    );
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveResult(null);
    try {
      const rows = editedRows.map((r: any) => ({
          account: r.account_code || r.account,
          debit: r.debit || 0,
          credit: r.credit || 0,
          description: r.description || undefined,
        }));

      const saved =
        voucher.status === "posted"
          ? await api.correctVoucher(id, {
              corrected_rows: rows,
              reason: correctionReason || undefined,
            })
          : await api.updateVoucher(id, {
              rows,
              reason: correctionReason || undefined,
            });

      setSaveResult({
        ok: true,
        msg:
          voucher.status === "posted"
            ? `Korrigering bokförd som ${saved.series}${saved.number}.`
            : "Ändring sparad.",
      });
      queryClient.invalidateQueries({ queryKey: ["voucher", id] });
      queryClient.invalidateQueries({ queryKey: ["voucher-audit", id] });
      queryClient.invalidateQueries({ queryKey: ["voucher-source-context", id] });
      queryClient.invalidateQueries({ queryKey: ["vouchers"] });
      queryClient.invalidateQueries({ queryKey: ["accounting-corrections"] });
      setTimeout(() => setIsEditing(false), 2000);
    } catch (err: any) {
      setSaveResult({
        ok: false,
        msg: err?.message || "Kunde inte spara korrigeringen",
      });
    } finally {
      setSaving(false);
    }
  };

  const attachmentUrl = (attId: string) =>
    api.getAttachmentUrl(id, attId);

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1000px] mx-auto">
      {/* Back link */}
      <Link
        href="/vouchers"
        className="text-sm text-muted-foreground hover:text-foreground flex items-center gap-1 w-fit"
      >
        <ArrowLeft className="h-4 w-4" /> Tillbaka
      </Link>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">
              Verifikation {voucher.number}
            </h1>
            <Badge
              variant={
                voucher.status === "posted"
                  ? "success"
                  : voucher.status === "draft"
                  ? "warning"
                  : "secondary"
              }
            >
              {voucher.status === "draft"
                ? "Utkast"
                : voucher.status === "posted"
                ? "Bokförd"
                : voucher.status}
            </Badge>
          </div>
          <p className="text-muted-foreground mt-1">{voucher.description}</p>
        </div>
        <div className="flex items-center gap-2">
          {voucher.created_by === "ai" && (
            <Badge variant="secondary" className="gap-1">
              <Brain className="h-3 w-3" /> AI-genererad
            </Badge>
          )}
          {!isEditing && (
            <Button
              variant="outline"
              size="sm"
              onClick={startEditing}
              className="gap-2"
            >
              <Pencil className="h-4 w-4" />
              {voucher.status === "draft" ? "Redigera" : "Korrigera"}
            </Button>
          )}
        </div>
      </div>

      {/* Meta info */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <Calendar className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Datum</p>
              <p className="font-medium">{formatDate(voucher.date)}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <Hash className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Nummer</p>
              <p className="font-medium">
                {voucher.number}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <FileText className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Rader</p>
              <p className="font-medium">{voucher.rows?.length || 0}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div
              className={`h-2.5 w-2.5 rounded-full ${
                isBalanced ? "bg-emerald-500" : "bg-red-500"
              }`}
            />
            <div>
              <p className="text-xs text-muted-foreground">Balans</p>
              <p className="font-medium">
                {isBalanced ? "I balans" : "Obalanserad"}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Save result banner */}
      {saveResult && (
        <div
          className={`flex items-center gap-2 p-4 rounded-lg ${
            saveResult.ok
              ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400"
              : "bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-400"
          }`}
        >
          {saveResult.ok ? (
            <CheckCircle2 className="h-5 w-5 flex-shrink-0" />
          ) : (
            <AlertTriangle className="h-5 w-5 flex-shrink-0" />
          )}
          <span className="text-sm font-medium">{saveResult.msg}</span>
        </div>
      )}

      {/* Rows table — read-only or edit mode */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>
                {isEditing ? "Korrigera konteringsrader" : "Konteringsrader"}
              </CardTitle>
              <CardDescription>
                {isEditing
                  ? voucher.status === "posted"
                    ? "Skapar en postad B-serie-korrigering. Originalverifikationen ändras inte."
                    : "Ändra konto eller belopp och spara"
                  : "Debet och kredit per konto"}
              </CardDescription>
            </div>
            {isEditing && (
              <Button variant="ghost" size="sm" onClick={cancelEditing}>
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-left p-3 font-medium text-muted-foreground">
                    Konto
                  </th>
                  <th className="text-left p-3 font-medium text-muted-foreground">
                    Kontonamn
                  </th>
                  <th className="text-right p-3 font-medium text-muted-foreground">
                    Debet
                  </th>
                  <th className="text-right p-3 font-medium text-muted-foreground">
                    Kredit
                  </th>
                </tr>
              </thead>
              <tbody>
                {isEditing
                  ? editedRows.map((row, i) => (
                      <tr key={i} className="border-b last:border-0">
                        <td className="p-2" colSpan={2}>
                          <select
                            value={row.account_code}
                            onChange={(e) =>
                              updateRow(i, "account_code", e.target.value)
                            }
                            className="w-full rounded border bg-background px-2 py-1.5 text-sm font-mono"
                          >
                            {accounts.map((a: any) => (
                              <option key={a.code} value={a.code}>
                                {a.code} — {a.name}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="p-2">
                          <input
                            type="number"
                            value={row.debit || ""}
                            onChange={(e) =>
                              updateRow(
                                i,
                                "debit",
                                parseInt(e.target.value) || 0
                              )
                            }
                            className="w-full rounded border bg-background px-2 py-1.5 text-sm text-right font-mono"
                            placeholder="0"
                          />
                        </td>
                        <td className="p-2">
                          <input
                            type="number"
                            value={row.credit || ""}
                            onChange={(e) =>
                              updateRow(
                                i,
                                "credit",
                                parseInt(e.target.value) || 0
                              )
                            }
                            className="w-full rounded border bg-background px-2 py-1.5 text-sm text-right font-mono"
                            placeholder="0"
                          />
                        </td>
                      </tr>
                    ))
                  : voucher.rows?.map((row: any, i: number) => (
                      <tr
                        key={i}
                        className="border-b last:border-0 hover:bg-muted/30"
                      >
                        <td className="p-3 font-mono font-medium">
                          {row.account_code}
                        </td>
                        <td className="p-3 text-muted-foreground">
                          {row.account_name || "-"}
                        </td>
                        <td className="p-3 text-right font-mono">
                          {row.debit ? formatCurrency(row.debit) : "-"}
                        </td>
                        <td className="p-3 text-right font-mono">
                          {row.credit ? formatCurrency(row.credit) : "-"}
                        </td>
                      </tr>
                    ))}
              </tbody>
              {!isEditing && (
                <tfoot>
                  <tr className="border-t-2 font-bold">
                    <td className="p-3" colSpan={2}>
                      Summa
                    </td>
                    <td className="p-3 text-right font-mono">
                      {formatCurrency(totalDebit || 0)}
                    </td>
                    <td className="p-3 text-right font-mono">
                      {formatCurrency(totalCredit || 0)}
                    </td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>

          {/* Correction form */}
          {isEditing && (
            <div className="mt-6 space-y-4 border-t pt-6">
              <div>
                <label className="block text-sm font-medium mb-1">
                  Anledning till korrigering
                </label>
                <textarea
                  value={correctionReason}
                  onChange={(e) => setCorrectionReason(e.target.value)}
                  placeholder="Beskriv varför denna korrigering behövs..."
                  className="w-full rounded-lg border bg-background px-3 py-2 text-sm min-h-[80px] focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>

              {voucher.status === "posted" && (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Brain className="h-4 w-4 text-violet-500" />
                  Korrigeringen sparas som agentläsbar historik.
                </p>
              )}

              <div className="flex gap-3">
                <Button
                  onClick={handleSave}
                  disabled={saving}
                  className="gap-2"
                >
                  <Save className="h-4 w-4" />
                  {saving ? "Sparar..." : "Spara korrigering"}
                </Button>
                <Button variant="outline" onClick={cancelEditing}>
                  Avbryt
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <SourceMaterialSection
        isLoading={sourceContextLoading}
        sourceMaterials={sourceMaterials}
        onOpenSourceFile={openSourceFile}
      />

      <AgentProcessingSection
        isLoading={sourceContextLoading}
        processingNotes={processingNotes}
      />

      {showCorrectionChain && (
        <CorrectionChainSection
          currentVoucherId={voucher.id}
          correctionOf={voucher.correction_of}
          correctionChain={correctionChain}
        />
      )}

      {/* Attachments */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Paperclip className="h-5 w-5 text-primary" />
            Bilagor
            {attachmentsList.length > 0 && (
              <Badge variant="secondary" className="text-xs">
                {attachmentsList.length}
              </Badge>
            )}
          </CardTitle>
          <CardDescription>
            Underlag enligt BFL — kvitton, fakturor och andra dokument
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* Existing attachments */}
          {attachmentsList.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
              {attachmentsList.map((att: any) => {
                const isImage = att.mime_type?.startsWith("image/");
                const isPdf = att.mime_type === "application/pdf";
                const url = attachmentUrl(att.id);

                return (
                  <div
                    key={att.id}
                    className="border rounded-lg overflow-hidden group"
                  >
                    {isImage && (
                      <a href={url} target="_blank" rel="noopener noreferrer">
                        <Image
                          src={url}
                          alt={att.filename}
                          width={640}
                          height={360}
                          unoptimized
                          className="w-full h-48 object-contain bg-muted/30 hover:opacity-90 transition-opacity"
                        />
                      </a>
                    )}
                    {isPdf && (
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center justify-center h-48 bg-muted/30 hover:bg-muted/50 transition-colors"
                      >
                        <div className="text-center">
                          <File className="h-12 w-12 mx-auto text-red-500 mb-2" />
                          <span className="text-sm text-muted-foreground">Klicka för att öppna PDF</span>
                        </div>
                      </a>
                    )}
                    <div className="p-3 flex items-center justify-between">
                      <div className="flex items-center gap-2 min-w-0">
                        {isImage ? (
                          <FileImage className="h-4 w-4 text-blue-500 flex-shrink-0" />
                        ) : (
                          <File className="h-4 w-4 text-red-500 flex-shrink-0" />
                        )}
                        <span className="text-sm truncate">{att.filename}</span>
                        <span className="text-xs text-muted-foreground flex-shrink-0">
                          {(att.size_bytes / 1024).toFixed(0)} KB
                        </span>
                      </div>
                      {voucher.status === "draft" && (
                        <button
                          onClick={() => handleDeleteAttachment(att.id)}
                          className="text-muted-foreground hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100"
                          title="Ta bort"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Upload area */}
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
              if (file) handleFileUpload(file);
            }}
            className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
              dragOver
                ? "border-primary bg-primary/5"
                : "border-border hover:border-primary/50"
            }`}
          >
            {uploading ? (
              <div className="flex items-center justify-center gap-2">
                <div className="h-4 w-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                <span className="text-sm">Laddar upp...</span>
              </div>
            ) : (
              <>
                <Upload className="h-6 w-6 mx-auto mb-2 text-muted-foreground" />
                <p className="text-sm text-muted-foreground mb-2">
                  Dra och släpp en fil, eller
                </p>
                <label>
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/gif,image/webp,application/pdf"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleFileUpload(file);
                      e.target.value = "";
                    }}
                  />
                  <span className="inline-flex items-center justify-center rounded-lg font-medium text-sm h-8 px-3 border border-input bg-background hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer">
                    Välj fil
                  </span>
                </label>
                <p className="text-xs text-muted-foreground mt-2">
                  JPG, PNG, GIF, WebP eller PDF (max 10 MB)
                </p>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Audit trail / History */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <History className="h-5 w-5 text-primary" />
            Ändringshistorik
          </CardTitle>
          <CardDescription>
            Spårbarhet enligt BFL — alla händelser loggas
          </CardDescription>
        </CardHeader>
        <CardContent>
          {auditEntries.length > 0 ? (
            <div className="space-y-3">
              {auditEntries.map((entry: any, i: number) => (
                <div
                  key={entry.id || i}
                  className={`flex items-start gap-3 p-3 rounded-lg border-l-4 ${
                    entry.action === "created"
                      ? "border-l-emerald-500 bg-emerald-50/50 dark:bg-emerald-950/10"
                      : entry.action === "posted"
                      ? "border-l-blue-500 bg-blue-50/50 dark:bg-blue-950/10"
                      : entry.action === "corrected"
                      ? "border-l-amber-500 bg-amber-50/50 dark:bg-amber-950/10"
                      : "border-l-gray-400 bg-muted/30"
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge
                        variant={
                          entry.action === "created"
                            ? "success"
                            : entry.action === "posted"
                            ? "default"
                            : entry.action === "corrected"
                            ? "warning"
                            : "secondary"
                        }
                        className="text-xs"
                      >
                        {entry.action === "created"
                          ? "Skapad"
                          : entry.action === "posted"
                          ? "Bokförd"
                          : entry.action === "corrected"
                          ? "Korrigerad"
                          : entry.action === "updated"
                          ? "Uppdaterad"
                          : entry.action}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {entry.actor || "system"}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        •
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {formatDate(entry.timestamp)}
                      </span>
                    </div>
                    {entry.payload && (
                      <div className="mt-1 space-y-1">
                        <p className="text-xs text-muted-foreground">
                          {entry.payload.reason ||
                            (entry.payload.rows_count
                              ? `${entry.payload.rows_count} rader`
                              : "")}
                        </p>
                        {entry.payload.old_rows && entry.payload.new_rows && (
                          <details className="text-xs">
                            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                              Visa ändringar
                            </summary>
                            <div className="mt-1 grid grid-cols-2 gap-2">
                              <div>
                                <p className="font-medium text-muted-foreground mb-0.5">Före:</p>
                                {entry.payload.old_rows.map((r: any, j: number) => (
                                  <p key={j} className="font-mono text-red-600 dark:text-red-400">
                                    {r.account} D:{formatCurrency(r.debit)} K:{formatCurrency(r.credit)}
                                  </p>
                                ))}
                              </div>
                              <div>
                                <p className="font-medium text-muted-foreground mb-0.5">Efter:</p>
                                {entry.payload.new_rows.map((r: any, j: number) => (
                                  <p key={j} className="font-mono text-emerald-600 dark:text-emerald-400">
                                    {r.account} D:{formatCurrency(r.debit)} K:{formatCurrency(r.credit)}
                                  </p>
                                ))}
                              </div>
                            </div>
                          </details>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground text-center py-6 text-sm">
              Ingen historik tillgänglig
            </p>
          )}
        </CardContent>
      </Card>

      {/* Created info */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Skapad av: {voucher.created_by || "okänd"}</span>
        {voucher.created_at && <span>Skapad: {formatDate(voucher.created_at)}</span>}
      </div>
    </div>
  );
}

function SourceMaterialSection({
  isLoading,
  sourceMaterials,
  onOpenSourceFile,
}: {
  isLoading: boolean;
  sourceMaterials: VoucherSourceContext["source_material"];
  onOpenSourceFile: (
    source: VoucherSourceContext["source_material"][number]
  ) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-primary" />
          Källmaterial
          {sourceMaterials.length > 0 && (
            <Badge variant="secondary" className="text-xs">
              {sourceMaterials.length}
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          Intagsmaterial kopplat till verifikationen, separat från manuella bilagor.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : sourceMaterials.length > 0 ? (
          <div className="space-y-3">
            {sourceMaterials.map((source) => (
              <div
                key={`${source.kind}-${source.id}`}
                className="rounded-lg border p-4"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <SourceKindBadge kind={source.kind} />
                      <IntakeStatusBadge status={source.status} />
                    </div>
                    <p className="break-words text-sm font-medium">
                      {source.original_filename}
                    </p>
                    <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      <span>Uppladdad {formatDate(source.uploaded_at)}</span>
                      <span>Kopplad {formatDate(source.linked_at)}</span>
                      <span>Av {source.uploaded_by || source.linked_by || "okänd"}</span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {source.kind === "bank_input"
                        ? `${source.imported_count} importerade, ${source.skipped_count} hoppade över`
                        : source.source_type
                        ? sourceTypeLabels[source.source_type] || source.source_type
                        : "Verifikationsunderlag"}
                    </p>
                    {source.kind === "voucher_source" && source.explanation && (
                      <p className="whitespace-pre-wrap break-words text-sm">
                        {source.explanation}
                      </p>
                    )}
                    {source.link_reason && (
                      <p className="text-xs text-muted-foreground">
                        Länkorsak: {source.link_reason}
                      </p>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-2 sm:justify-end">
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-2"
                      onClick={() => onOpenSourceFile(source)}
                    >
                      <Download className="h-3.5 w-3.5" />
                      Öppna fil
                    </Button>
                    <Link href={`/vouchers/intake/${source.kind}/${source.id}`}>
                      <Button variant="ghost" size="sm" className="gap-2">
                        <ExternalLink className="h-3.5 w-3.5" />
                        Visa intag
                      </Button>
                    </Link>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Inget intagsmaterial är kopplat till verifikationen.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function AgentProcessingSection({
  isLoading,
  processingNotes,
}: {
  isLoading: boolean;
  processingNotes: VoucherSourceContext["processing_notes"];
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-5 w-5 text-primary" />
          Agentbearbetning
          {processingNotes.length > 0 && (
            <Badge variant="secondary" className="text-xs">
              {processingNotes.length}
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          Sammanfattningar, varningar och fel från agentens behandling av källmaterial.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : processingNotes.length > 0 ? (
          <div className="space-y-3">
            {processingNotes.map((note) => (
              <div key={`${note.kind}-${note.id}`} className="rounded-lg border p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <SourceKindBadge kind={note.kind} />
                  <IntakeStatusBadge status={note.status} />
                  <span className="text-xs text-muted-foreground">
                    {note.actor || "agent"}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {formatDate(note.created_at)}
                  </span>
                </div>

                {note.summary && (
                  <p className="mt-3 whitespace-pre-wrap break-words text-sm">
                    {note.summary}
                  </p>
                )}

                {note.kind === "bank_input" && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    {note.detected_format || "Okänt format"} ·{" "}
                    {note.imported_count ?? 0} importerade ·{" "}
                    {note.skipped_count ?? 0} hoppade över
                  </p>
                )}

                {note.warnings?.length > 0 && (
                  <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50/60 p-3 dark:border-amber-900/50 dark:bg-amber-950/20">
                    <div className="flex items-center gap-2 text-sm font-medium text-amber-800 dark:text-amber-300">
                      <AlertTriangle className="h-4 w-4" />
                      Varningar
                    </div>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                      {note.warnings.map((warning, index) => (
                        <li key={index} className="break-words">
                          {warning}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {note.error_detail && (
                  <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3">
                    <div className="flex items-center gap-2 text-sm font-medium text-destructive">
                      <AlertTriangle className="h-4 w-4" />
                      Fel
                    </div>
                    <p className="mt-2 whitespace-pre-wrap break-words text-sm">
                      {note.error_detail}
                    </p>
                  </div>
                )}

                <div className="mt-3 flex flex-wrap gap-2">
                  {note.kind === "voucher_source" && note.intake_source_id && (
                    <Link
                      href={`/vouchers/intake/voucher_source/${note.intake_source_id}`}
                      className="text-xs text-primary hover:underline"
                    >
                      Underlag {note.intake_source_id}
                    </Link>
                  )}
                  {note.kind === "bank_input" && (
                    <Link
                      href={`/vouchers/intake/bank_input/${note.id}`}
                      className="text-xs text-primary hover:underline"
                    >
                      Bankfil {note.id}
                    </Link>
                  )}
                  {note.voucher_id && (
                    <Link
                      href={`/vouchers/${note.voucher_id}`}
                      className="text-xs text-primary hover:underline"
                    >
                      Verifikation {note.voucher_id}
                    </Link>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Inga agentanteckningar är kopplade till verifikationen.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function CorrectionChainSection({
  currentVoucherId,
  correctionOf,
  correctionChain,
}: {
  currentVoucherId: string;
  correctionOf?: string | null;
  correctionChain: VoucherSourceContext["correction_chain"];
}) {
  const fallbackChain =
    correctionChain.length > 0
      ? correctionChain
      : [
          {
            id: `${correctionOf}-${currentVoucherId}`,
            original_voucher_id: correctionOf || "",
            correction_voucher_id: currentVoucherId,
            correction_reason: null,
            actor: null,
            timestamp: "",
            change_type: null,
          },
        ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <History className="h-5 w-5 text-primary" />
          Korrigeringskedja
        </CardTitle>
        <CardDescription>
          Read-only historik över ursprunglig verifikation och korrigeringar.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="rounded-lg border bg-muted/30 p-3 text-sm">
          Den här historiken kan användas av agenten vid framtida bokföring.
        </p>

        <div className="space-y-3">
          {fallbackChain.map((entry) => (
            <div key={entry.id} className="rounded-lg border p-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <CorrectionVoucherLink
                  label="Originalverifikation"
                  voucherId={entry.original_voucher_id || correctionOf}
                />
                <CorrectionVoucherLink
                  label="Korrigeringsverifikation"
                  voucherId={entry.correction_voucher_id || currentVoucherId}
                />
              </div>

              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                <ReadOnlyField
                  label="Anledning"
                  value={entry.correction_reason || "Ingen anledning angiven"}
                />
                <ReadOnlyField label="Aktör" value={entry.actor || "okänd"} />
                <ReadOnlyField
                  label="Tidpunkt"
                  value={entry.timestamp ? formatDate(entry.timestamp) : "-"}
                />
              </div>

              {entry.change_type && (
                <div className="mt-3">
                  <Badge variant="outline">{entry.change_type}</Badge>
                </div>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function CorrectionVoucherLink({
  label,
  voucherId,
}: {
  label: string;
  voucherId?: string | null;
}) {
  return (
    <div className="rounded-lg border bg-muted/20 p-3">
      <p className="text-xs font-semibold uppercase text-muted-foreground">
        {label}
      </p>
      {voucherId ? (
        <Link
          href={`/vouchers/${voucherId}`}
          className="mt-1 inline-flex items-center gap-1 break-all text-sm text-primary hover:underline"
        >
          <ExternalLink className="h-3.5 w-3.5 flex-shrink-0" />
          {voucherId}
        </Link>
      ) : (
        <p className="mt-1 text-sm text-muted-foreground">Saknas</p>
      )}
    </div>
  );
}

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-muted/20 p-3">
      <p className="text-xs font-semibold uppercase text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 break-words text-sm">{value}</p>
    </div>
  );
}

function SourceKindBadge({ kind }: { kind: "voucher_source" | "bank_input" }) {
  return (
    <Badge variant="outline" className="gap-1.5">
      {kind === "bank_input" ? (
        <Landmark className="h-3 w-3" />
      ) : (
        <FileText className="h-3 w-3" />
      )}
      {kind === "bank_input" ? "Bankfil" : "Underlag"}
    </Badge>
  );
}

function IntakeStatusBadge({ status }: { status: IntakeStatus }) {
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

  return <Badge variant={variant}>{intakeStatusLabels[status]}</Badge>;
}
