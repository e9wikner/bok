"use client";

import { useParams } from "next/navigation";
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
import { useVoucher, useAccounts } from "@/hooks/useData";
import { api } from "@/lib/api";
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
} from "lucide-react";
export default function VoucherDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { data: voucher, isLoading } = useVoucher(id);
  const { data: accountsData } = useAccounts();
  const accounts = accountsData?.accounts || [];

  // Audit trail
  const { data: auditData } = useQuery({
    queryKey: ["voucher-audit", id],
    queryFn: async () => {
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1/vouchers/${id}/audit`,
        {
          headers: {
            Authorization: `Bearer ${process.env.NEXT_PUBLIC_API_KEY || "dev-key-change-in-production"}`,
          },
        }
      );
      return resp.json();
    },
    staleTime: 5 * 60 * 1000,
  });

  // Attachments
  const { data: attachmentsData, refetch: refetchAttachments } = useQuery({
    queryKey: ["voucher-attachments", id],
    queryFn: async () => {
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1/vouchers/${id}/attachments`,
        {
          headers: {
            Authorization: `Bearer ${process.env.NEXT_PUBLIC_API_KEY || "dev-key-change-in-production"}`,
          },
        }
      );
      return resp.json();
    },
    staleTime: 5 * 60 * 1000,
  });

  // Correction state
  const [isEditing, setIsEditing] = useState(false);
  const [editedRows, setEditedRows] = useState<any[]>([]);
  const [correctionReason, setCorrectionReason] = useState("");
  const [teachAI, setTeachAI] = useState(true);
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
        const formData = new FormData();
        formData.append("file", file);
        await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1/vouchers/${id}/attachments`,
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${process.env.NEXT_PUBLIC_API_KEY || "dev-key-change-in-production"}`,
            },
            body: formData,
          }
        );
        refetchAttachments();
      } catch {
        alert("Kunde inte ladda upp filen");
      } finally {
        setUploading(false);
      }
    },
    [id, refetchAttachments]
  );

  const handleDeleteAttachment = async (attachmentId: string) => {
    if (!confirm("Ta bort denna bilaga?")) return;
    try {
      await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1/vouchers/${id}/attachments/${attachmentId}`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${process.env.NEXT_PUBLIC_API_KEY || "dev-key-change-in-production"}`,
          },
        }
      );
      refetchAttachments();
    } catch {
      alert("Kunde inte ta bort bilagan");
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

  const startEditing = () => {
    setEditedRows(
      voucher.rows.map((r: any) => ({
        account_code: r.account_code,
        debit: r.debit || 0,
        credit: r.credit || 0,
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
      await api.recordCorrection(id, editedRows, correctionReason);
      setSaveResult({
        ok: true,
        msg: teachAI
          ? "Korrigering sparad! AI:n har lärt sig av ändringen."
          : "Korrigering sparad.",
      });
      queryClient.invalidateQueries({ queryKey: ["voucher", id] });
      queryClient.invalidateQueries({ queryKey: ["voucher-audit", id] });
      queryClient.invalidateQueries({ queryKey: ["vouchers"] });
      setTimeout(() => setIsEditing(false), 2000);
    } catch (err: any) {
      setSaveResult({
        ok: false,
        msg: err?.response?.data?.detail || "Kunde inte spara korrigeringen",
      });
    } finally {
      setSaving(false);
    }
  };

  const attachmentUrl = (attId: string) =>
    `${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1/vouchers/${id}/attachments/${attId}`;

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
              Verifikation {voucher.series || "A"}
              {voucher.number}
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
          {!isEditing && voucher.status === "posted" && (
            <Button
              variant="outline"
              size="sm"
              onClick={startEditing}
              className="gap-2"
            >
              <Pencil className="h-4 w-4" />
              Korrigera
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
                {voucher.series || "A"}
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
                  ? "Ändra konto eller belopp och spara"
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

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={teachAI}
                  onChange={(e) => setTeachAI(e.target.checked)}
                  className="h-4 w-4 rounded border"
                />
                <Brain className="h-4 w-4 text-violet-500" />
                <span className="text-sm">
                  Lär AI:n av denna korrigering (förbättrar framtida
                  bokföringar)
                </span>
              </label>

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
                        <img
                          src={url}
                          alt={att.filename}
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
                      <p className="text-xs text-muted-foreground mt-1">
                        {entry.payload.reason ||
                          (entry.payload.rows_count
                            ? `${entry.payload.rows_count} rader`
                            : "")}
                      </p>
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
