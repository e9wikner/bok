"use client";

import { useParams } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { useState, useCallback, useEffect } from "react";
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
import {
  useVoucher,
  useAccounts,
  useVoucherSourceContext,
  useCorrectionNotes,
} from "@/hooks/useData";
import { api } from "@/lib/api";
import type {
  CorrectionNote,
  IntakeStatus,
  Voucher,
  VoucherSourceContext,
} from "@/lib/api";
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

const correctionNoteStatusLabels: Record<CorrectionNote["status"], string> = {
  pending: "Väntar på agent",
  suggested: "Förslag klart",
  applied: "Tillämpad",
  dismissed: "Avfärdad",
  rejected: "Ingen lösning",
};

function correctionNoteStatusVariant(
  status: CorrectionNote["status"]
): "success" | "secondary" | "warning" {
  if (status === "applied") return "success";
  if (status === "dismissed" || status === "rejected") return "secondary";
  return "warning";
}

function formatOreInput(amountInOre: number): string {
  if (!amountInOre) return "";
  return (amountInOre / 100).toFixed(2).replace(".", ",");
}

function parseOreInput(value: string): number {
  const parsed = Number.parseFloat(value.replace(",", "."));
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
}

async function openAuthenticatedBlob(
  fetchBlob: () => Promise<Blob>,
  onError: () => void
) {
  const target = window.open("about:blank", "_blank");
  if (target) {
    target.opener = null;
  }
  try {
    const blob = await fetchBlob();
    const objectUrl = URL.createObjectURL(blob);
    if (target) {
      target.location.href = objectUrl;
    } else {
      window.location.assign(objectUrl);
    }
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  } catch {
    target?.close();
    onError();
  }
}

export default function VoucherDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { data: voucher, isLoading } = useVoucher(id);
  const { data: accountsData } = useAccounts();
  const { data: sourceContext, isLoading: sourceContextLoading } =
    useVoucherSourceContext(id);
  const { data: correctionNotes = [] } = useCorrectionNotes(id);
  const accounts = accountsData?.accounts || [];
  const activeCorrectionNote = correctionNotes.find((note) =>
    ["pending", "suggested"].includes(note.status)
  );
  const terminalCorrectionNotes = correctionNotes.filter((note) =>
    ["applied", "dismissed", "rejected"].includes(note.status)
  );
  const suggestedVoucherId =
    activeCorrectionNote?.status === "suggested"
      ? activeCorrectionNote.suggested_voucher_id
      : undefined;
  const { data: suggestedDraft } = useQuery<Voucher>({
    queryKey: ["voucher", suggestedVoucherId],
    queryFn: () => api.getVoucher(suggestedVoucherId as string),
    staleTime: 60 * 1000,
    enabled: !!suggestedVoucherId,
  });

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
  const [sourceFileError, setSourceFileError] = useState<string | null>(null);
  const [correctionNoteText, setCorrectionNoteText] = useState("");
  const [correctionNoteSaving, setCorrectionNoteSaving] = useState(false);
  const [correctionNoteActionId, setCorrectionNoteActionId] = useState<string | null>(null);
  const [suggestedRows, setSuggestedRows] = useState<any[]>([]);

  // Correction visualization state
  const [rowView, setRowView] = useState<"original" | "net" | "diff">("original");

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
      setSourceFileError(null);
      await openAuthenticatedBlob(
        () => api.getIntakeFile(source.kind, source.id),
        () => setSourceFileError("Kunde inte öppna källfilen.")
      );
    },
    []
  );

  useEffect(() => {
    if (!suggestedDraft?.rows) return;
    setSuggestedRows(
      suggestedDraft.rows.map((row) => ({
        account_code: row.account_code,
        debit: formatOreInput(row.debit || 0),
        credit: formatOreInput(row.credit || 0),
        description: row.description || "",
      }))
    );
  }, [suggestedDraft?.id, suggestedDraft?.rows]);

  // Reset row view when voucher changes
  useEffect(() => {
    setRowView("original");
  }, [id]);

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
        debit: formatOreInput(r.debit || 0),
        credit: formatOreInput(r.credit || 0),
        description: r.description || "",
      }))
    );
    setIsEditing(true);
    setSaveResult(null);
    setRowView("original");
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
          debit: parseOreInput(r.debit || ""),
          credit: parseOreInput(r.credit || ""),
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

  const invalidateCorrectionNoteState = (note?: CorrectionNote | null) => {
    queryClient.invalidateQueries({ queryKey: ["correction-notes", voucher.id] });
    queryClient.invalidateQueries({ queryKey: ["voucher-source-context", voucher.id] });
    queryClient.invalidateQueries({ queryKey: ["accounting-corrections"] });
    if (note?.suggested_voucher_id) {
      queryClient.invalidateQueries({ queryKey: ["voucher", note.suggested_voucher_id] });
    }
  };

  const handleCreateCorrectionNote = async () => {
    const trimmed = correctionNoteText.trim();
    if (!trimmed) return;
    setCorrectionNoteSaving(true);
    setSaveResult(null);
    try {
      await api.createCorrectionNote(voucher.id, trimmed);
      setCorrectionNoteText("");
      invalidateCorrectionNoteState(null);
      setSaveResult({
        ok: true,
        msg: "Noteringen har skickats till agenten.",
      });
    } catch (err: any) {
      const code = err?.response?.data?.detail?.code;
      setSaveResult({
        ok: false,
        msg:
          code === "correction_note_active_exists"
            ? "Det finns redan en aktiv korrigeringsnotering för verifikationen."
            : "Korrigeringsnoteringen kunde inte sparas. Försök igen.",
      });
      queryClient.invalidateQueries({ queryKey: ["correction-notes", voucher.id] });
    } finally {
      setCorrectionNoteSaving(false);
    }
  };

  const handleDismissCorrectionNote = async (
    note: CorrectionNote,
    confirmation: string,
    successMessage: string
  ) => {
    if (!confirm(confirmation)) return;
    setCorrectionNoteActionId(note.id);
    setSaveResult(null);
    try {
      await api.dismissCorrectionNote(voucher.id, note.id);
      invalidateCorrectionNoteState(note);
      setSaveResult({ ok: true, msg: successMessage });
    } catch (err: any) {
      setSaveResult({
        ok: false,
        msg: err?.message || "Kunde inte avfärda korrigeringsnoteringen.",
      });
    } finally {
      setCorrectionNoteActionId(null);
    }
  };

  const updateSuggestedRow = (index: number, field: string, value: string) => {
    setSuggestedRows((prev) =>
      prev.map((row, i) => (i === index ? { ...row, [field]: value } : row))
    );
  };

  const handleApproveSuggestedCorrection = async () => {
    if (!activeCorrectionNote) return;
    setCorrectionNoteActionId(activeCorrectionNote.id);
    setSaveResult(null);
    try {
      const rows = suggestedRows.map((row) => ({
        account: row.account_code,
        debit: parseOreInput(row.debit || ""),
        credit: parseOreInput(row.credit || ""),
        description: row.description || undefined,
      }));
      const posted = await api.approveCorrectionNote(
        voucher.id,
        activeCorrectionNote.id,
        rows
      );
      queryClient.invalidateQueries({ queryKey: ["voucher", id] });
      if (activeCorrectionNote.suggested_voucher_id) {
        queryClient.invalidateQueries({
          queryKey: ["voucher", activeCorrectionNote.suggested_voucher_id],
        });
      }
      queryClient.invalidateQueries({ queryKey: ["correction-notes", id] });
      queryClient.invalidateQueries({ queryKey: ["voucher-source-context", id] });
      queryClient.invalidateQueries({ queryKey: ["vouchers"] });
      queryClient.invalidateQueries({ queryKey: ["accounting-corrections"] });
      setSaveResult({
        ok: true,
        msg: `Korrigeringen bokfördes som ${posted.series}-serie.`,
      });
    } catch (err: any) {
      setSaveResult({
        ok: false,
        msg: err?.message || "Kunde inte bokföra korrigeringen.",
      });
    } finally {
      setCorrectionNoteActionId(null);
    }
  };

  const attachmentUrl = (attId: string) =>
    api.getAttachmentUrl(id, attId);

  const suggestedDebit = suggestedRows.reduce(
    (sum, row) => sum + parseOreInput(row.debit || ""),
    0
  );
  const suggestedCredit = suggestedRows.reduce(
    (sum, row) => sum + parseOreInput(row.credit || ""),
    0
  );
  const suggestedBalanced = suggestedDebit === suggestedCredit;

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
          {["agent", "ai"].includes(voucher.created_by) && (
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

      {/* B-series correction banner */}
      {voucher.correction_of && (
        <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-4 dark:border-amber-900/50 dark:bg-amber-950/20">
          <div className="flex items-center gap-2 text-sm font-medium text-amber-800 dark:text-amber-300">
            <History className="h-4 w-4" />
            Detta är en korrigeringsverifikation (B-serie).
          </div>
          <p className="mt-1 text-sm text-amber-700 dark:text-amber-400">
            Visa den sammanfogade vyn på originalverifikationen för att se nettot.
          </p>
          <Link
            href={`/vouchers/${voucher.correction_of}`}
            className="mt-2 inline-flex items-center gap-1 text-sm text-primary hover:underline"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Gå till originalverifikation {voucher.correction_of}
          </Link>
        </div>
      )}

      {/* Corrected badge on original */}
      {correctionChain.length > 0 && !voucher.correction_of && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50/60 p-4 dark:border-emerald-900/50 dark:bg-emerald-950/20">
          <div className="flex items-center gap-2 text-sm font-medium text-emerald-800 dark:text-emerald-300">
            <CheckCircle2 className="h-4 w-4" />
            Denna verifikation har korrigerats.
          </div>
          <p className="mt-1 text-sm text-emerald-700 dark:text-emerald-400">
            Se nettot efter korrigering under konteringsrader nedan.
          </p>
        </div>
      )}

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

      {voucher.status === "posted" && !voucher.correction_of && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Pencil className="h-5 w-5 text-primary" />
              Korrigeringsnotering
            </CardTitle>
            <CardDescription>
              Skriv vad som behöver rättas så kan agenten föreslå en B-serie-korrigering.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {activeCorrectionNote ? (
              <div className="space-y-4">
                <div className="rounded-md border bg-muted/30 p-3">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Badge
                      variant={correctionNoteStatusVariant(activeCorrectionNote.status)}
                    >
                      {correctionNoteStatusLabels[activeCorrectionNote.status]}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {formatDate(activeCorrectionNote.created_at)}
                    </span>
                  </div>
                  <p className="whitespace-pre-wrap break-words text-sm">
                    {activeCorrectionNote.note_text}
                  </p>
                  {activeCorrectionNote.status === "rejected" &&
                    activeCorrectionNote.rejection_reason && (
                      <p className="mt-2 text-sm text-muted-foreground">
                        Agenten kunde inte föreslå en korrigering:{" "}
                        {activeCorrectionNote.rejection_reason}
                      </p>
                    )}
                </div>

                {["pending", "suggested"].includes(activeCorrectionNote.status) && (
                  <div className="flex flex-wrap items-center gap-3">
                    <Button
                      variant="outline"
                      onClick={() =>
                        handleDismissCorrectionNote(
                          activeCorrectionNote,
                          "Avfärda notering: agenten kommer inte att föreslå någon korrigering för denna notering.",
                          "Noteringen har avfärdats."
                        )
                      }
                      disabled={correctionNoteActionId === activeCorrectionNote.id}
                    >
                      Avfärda notering
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <label
                    htmlFor="correction-note-text"
                    className="mb-1 block text-sm font-medium"
                  >
                    Notering
                  </label>
                  <textarea
                    id="correction-note-text"
                    value={correctionNoteText}
                    onChange={(event) => setCorrectionNoteText(event.target.value)}
                    placeholder="Exempel: Bankavgiften ska bokföras på 6570 utan moms."
                    className="w-full rounded-lg border bg-background px-3 py-2 text-sm min-h-[88px] focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    onClick={handleCreateCorrectionNote}
                    disabled={
                      correctionNoteSaving || correctionNoteText.trim().length === 0
                    }
                  >
                    {correctionNoteSaving ? "Skickar..." : "Skicka till agent"}
                  </Button>
                </div>
              </div>
            )}

            {terminalCorrectionNotes.length > 0 && (
              <div className="space-y-3">
                {terminalCorrectionNotes.map((note) => (
                  <div
                    key={note.id}
                    className="rounded-md border bg-muted/30 p-3"
                  >
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <Badge variant={correctionNoteStatusVariant(note.status)}>
                        {correctionNoteStatusLabels[note.status]}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {formatDate(note.resolved_at || note.updated_at || note.created_at)}
                      </span>
                    </div>
                    {note.status === "rejected" && (
                      <p className="mb-1 text-sm font-medium">
                        Agenten kunde inte föreslå en korrigering
                      </p>
                    )}
                    <p className="whitespace-pre-wrap break-words text-sm">
                      {note.note_text}
                    </p>
                    {note.rejection_reason && (
                      <p className="mt-2 text-sm text-muted-foreground">
                        {note.rejection_reason}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activeCorrectionNote?.status === "suggested" &&
        activeCorrectionNote.suggested_voucher_id && (
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Brain className="h-5 w-5 text-primary" />
                    Föreslagen korrigering
                  </CardTitle>
                  <CardDescription>
                    Granska raderna innan korrigeringen bokförs. Originalverifikationen ändras inte.
                  </CardDescription>
                </div>
                <Badge variant="warning">Förslag klart</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="text-left p-3 font-medium text-muted-foreground">
                        Konto
                      </th>
                      <th className="text-left p-3 font-medium text-muted-foreground">
                        Beskrivning
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
                    {suggestedRows.map((row, index) => (
                      <tr key={index} className="border-b last:border-0">
                        <td className="p-2">
                          <select
                            value={row.account_code}
                            onChange={(event) =>
                              updateSuggestedRow(
                                index,
                                "account_code",
                                event.target.value
                              )
                            }
                            className="w-full rounded border bg-background px-2 py-1.5 text-sm font-mono"
                          >
                            {accounts.map((account: any) => (
                              <option key={account.code} value={account.code}>
                                {account.code} — {account.name}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="p-2">
                          <input
                            type="text"
                            value={row.description || ""}
                            onChange={(event) =>
                              updateSuggestedRow(
                                index,
                                "description",
                                event.target.value
                              )
                            }
                            className="w-full rounded border bg-background px-2 py-1.5 text-sm"
                          />
                        </td>
                        <td className="p-2">
                          <input
                            type="text"
                            inputMode="decimal"
                            value={row.debit || ""}
                            onChange={(event) =>
                              updateSuggestedRow(index, "debit", event.target.value)
                            }
                            className="w-full rounded border bg-background px-2 py-1.5 text-sm text-right font-mono"
                            placeholder="0"
                          />
                        </td>
                        <td className="p-2">
                          <input
                            type="text"
                            inputMode="decimal"
                            value={row.credit || ""}
                            onChange={(event) =>
                              updateSuggestedRow(index, "credit", event.target.value)
                            }
                            className="w-full rounded border bg-background px-2 py-1.5 text-sm text-right font-mono"
                            placeholder="0"
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 font-bold">
                      <td className="p-3" colSpan={2}>
                        Summa
                      </td>
                      <td className="p-3 text-right font-mono">
                        {formatCurrency(suggestedDebit)}
                      </td>
                      <td className="p-3 text-right font-mono">
                        {formatCurrency(suggestedCredit)}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>

              {!suggestedBalanced && (
                <p className="text-sm text-destructive">
                  Förslaget måste balansera innan det kan bokföras.
                </p>
              )}

              <div className="flex flex-wrap items-center gap-3">
                <Button
                  onClick={handleApproveSuggestedCorrection}
                  disabled={
                    !suggestedBalanced ||
                    suggestedRows.length === 0 ||
                    correctionNoteActionId === activeCorrectionNote.id
                  }
                >
                  {correctionNoteActionId === activeCorrectionNote.id
                    ? "Bokför..."
                    : "Bokför korrigering"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() =>
                    handleDismissCorrectionNote(
                      activeCorrectionNote,
                      "Avfärda förslag: utkastet tas bort och förslaget sparas i historiken för agentens lärande.",
                      "Förslaget har avfärdats och sparats i historiken."
                    )
                  }
                  disabled={correctionNoteActionId === activeCorrectionNote.id}
                >
                  Avfärda förslag
                </Button>
              </div>
            </CardContent>
          </Card>
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
                  : correctionChain.length > 0 && !voucher.correction_of
                  ? "Original, netto och ändringar för korrigerad verifikation"
                  : "Debet och kredit per konto"}
              </CardDescription>
            </div>
            {isEditing && (
              <Button variant="ghost" size="sm" onClick={cancelEditing}>
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
          {!isEditing && correctionChain.length > 0 && !voucher.correction_of && (
            <div className="mt-3 flex gap-1">
              <Button
                variant={rowView === "original" ? "default" : "outline"}
                size="sm"
                onClick={() => setRowView("original")}
              >
                Original
              </Button>
              <Button
                variant={rowView === "net" ? "default" : "outline"}
                size="sm"
                onClick={() => setRowView("net")}
              >
                Netto
              </Button>
              <Button
                variant={rowView === "diff" ? "default" : "outline"}
                size="sm"
                onClick={() => setRowView("diff")}
              >
                Ändringar
              </Button>
            </div>
          )}
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            {isEditing ? (
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
                  {editedRows.map((row, i) => (
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
                          type="text"
                          inputMode="decimal"
                          value={row.debit || ""}
                          onChange={(e) =>
                            updateRow(
                              i,
                              "debit",
                              e.target.value
                            )
                          }
                          className="w-full rounded border bg-background px-2 py-1.5 text-sm text-right font-mono"
                          placeholder="0"
                        />
                      </td>
                      <td className="p-2">
                        <input
                          type="text"
                          inputMode="decimal"
                          value={row.credit || ""}
                          onChange={(e) =>
                            updateRow(
                              i,
                              "credit",
                              e.target.value
                            )
                          }
                          className="w-full rounded border bg-background px-2 py-1.5 text-sm text-right font-mono"
                          placeholder="0"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : rowView === "net" && correctionChain.length > 0 ? (
              <NetRowsTable
                correctionChain={correctionChain}
                accountNames={accounts}
              />
            ) : rowView === "diff" && correctionChain.length > 0 ? (
              <CorrectionDiffTable
                voucher={voucher}
                correctionChain={correctionChain}
                accountNames={accounts}
              />
            ) : (
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
                  {voucher.rows?.map((row: any, i: number) => (
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
              </table>
            )}
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
        error={sourceFileError}
        onOpenSourceFile={openSourceFile}
      />

      <AgentProcessingSection
        isLoading={sourceContextLoading}
        processingNotes={processingNotes}
      />

      {showCorrectionChain && (
        <CorrectionMetaSection
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

function NetRowsTable({
  correctionChain,
  accountNames,
}: {
  correctionChain: VoucherSourceContext["correction_chain"];
  accountNames: { code: string; name: string }[];
}) {
  const latest = correctionChain[correctionChain.length - 1];
  const netRows = latest?.corrected_data?.rows || [];
  const totalDebit = netRows.reduce((s, r) => s + (r.debit || 0), 0);
  const totalCredit = netRows.reduce((s, r) => s + (r.credit || 0), 0);
  const nameMap = new Map(accountNames.map((a) => [a.code, a.name]));

  return (
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
        {netRows.map((row, i) => (
          <tr key={i} className="border-b last:border-0 hover:bg-muted/30">
            <td className="p-3 font-mono font-medium">{row.account_code}</td>
            <td className="p-3 text-muted-foreground">
              {nameMap.get(row.account_code) || "-"}
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
      <tfoot>
        <tr className="border-t-2 font-bold">
          <td className="p-3" colSpan={2}>
            Summa
          </td>
          <td className="p-3 text-right font-mono">
            {formatCurrency(totalDebit)}
          </td>
          <td className="p-3 text-right font-mono">
            {formatCurrency(totalCredit)}
          </td>
        </tr>
      </tfoot>
    </table>
  );
}

function CorrectionDiffTable({
  voucher,
  correctionChain,
  accountNames,
}: {
  voucher: any;
  correctionChain: VoucherSourceContext["correction_chain"];
  accountNames: { code: string; name: string }[];
}) {
  const latest = correctionChain[correctionChain.length - 1];
  const originalRows = latest?.original_data?.rows || voucher.rows || [];
  const correctedRows = latest?.corrected_data?.rows || [];
  const nameMap = new Map(accountNames.map((a) => [a.code, a.name]));

  // Aggregate by account code for a compact diff view
  const agg = new Map<
    string,
    { beforeDebit: number; beforeCredit: number; afterDebit: number; afterCredit: number }
  >();

  for (const row of originalRows) {
    const key = row.account_code;
    const cur = agg.get(key) || { beforeDebit: 0, beforeCredit: 0, afterDebit: 0, afterCredit: 0 };
    cur.beforeDebit += row.debit || 0;
    cur.beforeCredit += row.credit || 0;
    agg.set(key, cur);
  }

  for (const row of correctedRows) {
    const key = row.account_code;
    const cur = agg.get(key) || { beforeDebit: 0, beforeCredit: 0, afterDebit: 0, afterCredit: 0 };
    cur.afterDebit += row.debit || 0;
    cur.afterCredit += row.credit || 0;
    agg.set(key, cur);
  }

  // Only show accounts where something changed
  const changed = Array.from(agg.entries()).filter(([, v]) => {
    return v.beforeDebit !== v.afterDebit || v.beforeCredit !== v.afterCredit;
  });

  if (changed.length === 0) {
    return (
      <p className="text-center text-sm text-muted-foreground py-6">
        Inga ändringar mellan original och korrigerad verifikation.
      </p>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b bg-muted/50">
          <th className="text-left p-3 font-medium text-muted-foreground">
            Konto
          </th>
          <th className="text-right p-3 font-medium text-muted-foreground">
            Före (D/K)
          </th>
          <th className="text-right p-3 font-medium text-muted-foreground">
            Efter (D/K)
          </th>
          <th className="text-right p-3 font-medium text-muted-foreground">
            Delta
          </th>
        </tr>
      </thead>
      <tbody>
        {changed.map(([accountCode, v]) => {
          const debitDelta = v.afterDebit - v.beforeDebit;
          const creditDelta = v.afterCredit - v.beforeCredit;
          return (
            <tr key={accountCode} className="border-b last:border-0 hover:bg-muted/30">
              <td className="p-3">
                <span className="font-mono font-medium">{accountCode}</span>
                <span className="ml-2 text-muted-foreground text-xs">
                  {nameMap.get(accountCode) || "-"}
                </span>
              </td>
              <td className="p-3 text-right font-mono text-muted-foreground">
                {formatCurrency(v.beforeDebit)} / {formatCurrency(v.beforeCredit)}
              </td>
              <td className="p-3 text-right font-mono">
                {formatCurrency(v.afterDebit)} / {formatCurrency(v.afterCredit)}
              </td>
              <td className="p-3 text-right font-mono">
                {debitDelta !== 0 && (
                  <span className={debitDelta > 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
                    D {debitDelta > 0 ? "+" : ""}
                    {formatCurrency(Math.abs(debitDelta))}
                  </span>
                )}
                {debitDelta !== 0 && creditDelta !== 0 && (
                  <span className="mx-1 text-muted-foreground">·</span>
                )}
                {creditDelta !== 0 && (
                  <span className={creditDelta > 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
                    K {creditDelta > 0 ? "+" : ""}
                    {formatCurrency(Math.abs(creditDelta))}
                  </span>
                )}
                {debitDelta === 0 && creditDelta === 0 && (
                  <span className="text-muted-foreground">-</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function SourceMaterialSection({
  isLoading,
  sourceMaterials,
  error,
  onOpenSourceFile,
}: {
  isLoading: boolean;
  sourceMaterials: VoucherSourceContext["source_material"];
  error: string | null;
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
        {error && (
          <p className="mb-3 rounded border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
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

function CorrectionMetaSection({
  correctionOf,
  correctionChain,
}: {
  currentVoucherId: string;
  correctionOf?: string | null;
  correctionChain: VoucherSourceContext["correction_chain"];
}) {
  if (correctionChain.length === 0 && !correctionOf) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <History className="h-5 w-5 text-primary" />
          Korrigeringshistorik
        </CardTitle>
        <CardDescription>
          Metadata för bokförda korrigeringar.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {correctionChain.map((entry) => (
          <div key={entry.id} className="rounded-lg border p-4">
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <Badge variant="outline">{entry.change_type || "korrigering"}</Badge>
              <span className="text-xs text-muted-foreground">
                {entry.timestamp ? formatDate(entry.timestamp) : "-"}
              </span>
            </div>
            <p className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">Anledning:</span>{" "}
              {entry.correction_reason || "Ingen anledning angiven"}
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              <span className="font-medium text-foreground">Aktör:</span>{" "}
              {entry.actor || "okänd"}
            </p>
            {entry.correction_voucher_id && (
              <p className="text-sm text-muted-foreground mt-1">
                <span className="font-medium text-foreground">Korrigeringsverifikation:</span>{" "}
                <Link
                  href={`/vouchers/${entry.correction_voucher_id}`}
                  className="text-primary hover:underline"
                >
                  {entry.correction_voucher_id}
                </Link>
              </p>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
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
