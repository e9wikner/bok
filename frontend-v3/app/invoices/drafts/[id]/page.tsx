"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Download,
  FileText,
  Plus,
  Save,
  Trash2,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAccounts, useArticles, useInvoiceDraft } from "@/hooks/useData";
import { api, InvoiceDraftPayload } from "@/lib/api";
import {
  describeInvoiceError,
  downloadInvoicePdf,
  errorDetail,
  formatQuantity,
  normaliseQuantity,
} from "@/lib/fakturering";
import { formatCurrency } from "@/lib/utils";

type DraftRow = {
  article_id?: string | null;
  description?: string | null;
  /** As typed: "7,5" or "7.5". */
  quantity: string;
  unit?: string | null;
  unit_price?: number | null;
  vat_code?: string | null;
  revenue_account?: string | null;
  source_note?: string | null;
  // Not edited here, but PUT replaces the draft, so they go back as they came.
  article_number?: string | null;
  delivery_from?: string | null;
  delivery_to?: string | null;
  delivery_month?: string | null;
};

const VAT_CODES = ["MP1", "MP2", "MP3", "MF"];

const STATUS_LABELS: Record<string, string> = {
  draft: "Utkast",
  needs_review: "Att granska",
  issued: "Utfärdad",
  sent: "Skickad",
  rejected: "Avvisad",
};

export default function InvoiceDraftPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const draftId = String(params.id);
  const { data: draft, isLoading } = useInvoiceDraft(draftId);
  const { data: articlesData } = useArticles();
  const { data: accountsData } = useAccounts();
  const articles = articlesData?.articles || [];
  const accounts = accountsData?.accounts || [];

  const [working, setWorking] = useState<"save" | "issue" | "reject" | "pdf" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  // Set when /issue answers `draft_already_issued`: the invoice it points to.
  const [issuedInvoiceId, setIssuedInvoiceId] = useState<string | null>(null);
  const [form, setForm] = useState<any>(null);

  useEffect(() => {
    if (!draft) return;
    setForm({
      customer_id: draft.customer_id || null,
      customer_name: draft.customer_name || "",
      customer_org_number: draft.customer_org_number || "",
      customer_email: draft.customer_email || "",
      invoice_date: draft.invoice_date || "",
      due_date: draft.due_date || "",
      reference: draft.reference || "",
      description: draft.description || "",
      invoice_number: draft.invoice_number || "",
      customer_address: draft.customer_address || "",
      delivery_from: draft.delivery_from || "",
      delivery_to: draft.delivery_to || "",
      delivery_month: draft.delivery_month || "",
      status: draft.status === "draft" ? "draft" : "needs_review",
      agent_summary: draft.agent_notes?.summary || "",
      agent_confidence:
        typeof draft.agent_notes?.confidence === "number"
          ? draft.agent_notes.confidence
          : null,
      agent_warnings: draft.agent_notes?.warnings?.join("\n") || "",
      rows: (draft.rows || []).map((row: any) => ({
        article_id: row.article_id || null,
        description: row.description || "",
        quantity: formatQuantity(row.quantity ?? 1),
        unit: row.unit || "",
        unit_price: row.unit_price ?? 0,
        vat_code: row.vat_code || "MP1",
        revenue_account: row.revenue_account || "3010",
        source_note: row.source_note || "",
        article_number: row.article_number || null,
        delivery_from: row.delivery_from || null,
        delivery_to: row.delivery_to || null,
        delivery_month: row.delivery_month || null,
      })),
    });
  }, [draft]);

  if (isLoading || !form) {
    return (
      <div className="mx-auto max-w-[1200px] space-y-4 p-4 lg:p-8">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!draft) {
    return <div className="p-8 text-muted-foreground">Fakturautkastet hittades inte.</div>;
  }

  const isIssued = draft.status === "issued" || draft.status === "sent";
  const isLocked = isIssued || draft.status === "rejected";
  const updateField = (field: string, value: any) => {
    setForm((current: any) => ({ ...current, [field]: value }));
  };

  const updateRow = (index: number, field: keyof DraftRow, value: any) => {
    setForm((current: any) => ({
      ...current,
      rows: current.rows.map((row: DraftRow, rowIndex: number) =>
        rowIndex === index ? { ...row, [field]: value } : row
      ),
    }));
  };

  const applyArticle = (index: number, articleId: string) => {
    const article = articles.find((item: any) => item.id === articleId);
    if (!article) {
      updateRow(index, "article_id", null);
      return;
    }
    setForm((current: any) => ({
      ...current,
      rows: current.rows.map((row: DraftRow, rowIndex: number) =>
        rowIndex === index
          ? {
              ...row,
              article_id: article.id,
              article_number: article.article_number,
              unit: row.unit || article.unit,
              description: row.description || article.description || article.name,
              unit_price: row.unit_price || article.unit_price,
              vat_code: row.vat_code || article.vat_code,
              revenue_account: row.revenue_account || article.revenue_account,
            }
          : row
      ),
    }));
  };

  const addRow = () => {
    setForm((current: any) => ({
      ...current,
      rows: [
        ...current.rows,
        {
          article_id: null,
          description: "",
          quantity: "1",
          unit: "",
          unit_price: 0,
          vat_code: "MP1",
          revenue_account: "3010",
          source_note: "",
        },
      ],
    }));
  };

  const removeRow = (index: number) => {
    setForm((current: any) => ({
      ...current,
      rows: current.rows.filter((_: DraftRow, rowIndex: number) => rowIndex !== index),
    }));
  };

  // PUT replaces the whole draft: every field goes along, or it is cleared.
  const payload = (): InvoiceDraftPayload => ({
    customer_id: form.customer_id || null,
    customer_name: form.customer_name || null,
    customer_org_number: form.customer_org_number || null,
    customer_email: form.customer_email || null,
    invoice_date: form.invoice_date,
    due_date: form.due_date || null,
    reference: form.reference || null,
    description: form.description || null,
    invoice_number: form.invoice_number.trim() || null,
    customer_address: form.customer_address.trim() || null,
    delivery_from: form.delivery_from || null,
    delivery_to: form.delivery_to || null,
    delivery_month: form.delivery_month || null,
    status: form.status || "needs_review",
    rows: form.rows.map((row: DraftRow) => ({
      article_id: row.article_id || null,
      description: row.description || null,
      quantity: normaliseQuantity(row.quantity) || "1",
      unit: row.unit?.trim() || null,
      unit_price: row.unit_price === null || row.unit_price === undefined ? null : Number(row.unit_price),
      vat_code: row.vat_code || null,
      revenue_account: row.revenue_account || null,
      source_note: row.source_note || null,
      article_number: row.article_number || null,
      delivery_from: row.delivery_from || null,
      delivery_to: row.delivery_to || null,
      delivery_month: row.delivery_month || null,
    })),
    agent_notes: {
      summary: form.agent_summary || null,
      confidence: form.agent_confidence,
      warnings: form.agent_warnings
        ? form.agent_warnings.split("\n").map((line: string) => line.trim()).filter(Boolean)
        : [],
    },
  });

  const save = async () => {
    setWorking("save");
    setMessage(null);
    try {
      const updated = await api.updateInvoiceDraft(draftId, payload());
      setMessage("Utkastet sparades.");
      queryClient.setQueryData(["invoice-draft", draftId], updated);
      await queryClient.invalidateQueries({ queryKey: ["invoice-drafts"] });
    } catch (error: any) {
      setMessage(describeInvoiceError(error, "Kunde inte spara utkastet."));
    } finally {
      setWorking(null);
    }
  };

  // Utfärda (SPEC-fakturering.md §5): save what is on screen, then issue.
  // Issuing posts the voucher and locks the invoice; all or nothing.
  const issue = async () => {
    setWorking("issue");
    setMessage(null);
    setIssuedInvoiceId(null);
    try {
      await api.updateInvoiceDraft(draftId, payload());
      const result = await api.issueInvoiceDraft(draftId);
      await queryClient.invalidateQueries({ queryKey: ["invoice-draft", draftId] });
      await queryClient.invalidateQueries({ queryKey: ["invoice-drafts"] });
      await queryClient.invalidateQueries({ queryKey: ["invoices"] });
      setMessage(`Faktura ${result.invoice_number} är utfärdad och bokförd.`);
    } catch (error: any) {
      const detail = errorDetail(error);
      if (detail?.code === "draft_already_issued" && detail.invoice_id) {
        setIssuedInvoiceId(detail.invoice_id);
      }
      setMessage(describeInvoiceError(error, "Kunde inte utfärda fakturan. Ingenting bokfördes."));
    } finally {
      setWorking(null);
    }
  };

  const downloadPdf = async () => {
    if (!draft.approved_invoice_id) return;
    setWorking("pdf");
    try {
      await downloadInvoicePdf({
        id: draft.approved_invoice_id,
        invoice_number: draft.invoice_number,
        pdf_url: draft.status === "issued" ? draft.pdf_url : null,
      });
    } catch (error: any) {
      setMessage(describeInvoiceError(error, "Kunde inte ladda ner PDF:en."));
    } finally {
      setWorking(null);
    }
  };

  const reject = async () => {
    setWorking("reject");
    setMessage(null);
    try {
      await api.rejectInvoiceDraft(draftId);
      await queryClient.invalidateQueries({ queryKey: ["invoice-drafts"] });
      router.push("/invoices");
    } catch (error: any) {
      setMessage(describeInvoiceError(error, "Kunde inte avvisa utkastet."));
    } finally {
      setWorking(null);
    }
  };

  return (
    <div className="mx-auto max-w-[1200px] space-y-6 p-4 lg:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight lg:text-3xl">Fakturautkast</h1>
          <p className="mt-1 text-muted-foreground">
            Granska och justera agentens utkast innan fakturan utfärdas och bokförs.
          </p>
        </div>
        <Badge variant={isIssued ? "default" : "outline"}>{STATUS_LABELS[draft.status] || draft.status}</Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Fakturauppgifter</CardTitle>
          <CardDescription>
            Backend räknar om moms och totaler när utkastet sparas.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <Field label="Fakturanummer" value={form.invoice_number} disabled={isLocked} placeholder="2026-1" onChange={(value) => updateField("invoice_number", value)} />
          <Field label="Er referens" value={form.reference} disabled={isLocked} onChange={(value) => updateField("reference", value)} />
          <Field label="Kundnamn" value={form.customer_name} disabled={isLocked} onChange={(value) => updateField("customer_name", value)} />
          <Field label="Organisationsnummer" value={form.customer_org_number} disabled={isLocked} onChange={(value) => updateField("customer_org_number", value)} />
          <label className="space-y-1">
            <span className="text-sm font-medium">Kundadress</span>
            <textarea
              value={form.customer_address}
              disabled={isLocked}
              onChange={(event) => updateField("customer_address", event.target.value)}
              placeholder={"Storgatan 1\n111 22 Stockholm"}
              className="min-h-[72px] w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-60"
            />
          </label>
          <Field label="E-post" value={form.customer_email} disabled={isLocked} onChange={(value) => updateField("customer_email", value)} />
          <Field label="Fakturadatum" type="date" value={form.invoice_date} disabled={isLocked} onChange={(value) => updateField("invoice_date", value)} />
          <Field label="Förfallodatum" type="date" value={form.due_date} disabled={isLocked} onChange={(value) => updateField("due_date", value)} />
          <div className="space-y-1 md:col-span-2">
            <span className="text-sm font-medium">Leverans</span>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Från" type="date" value={form.delivery_from} disabled={isLocked} onChange={(value) => updateField("delivery_from", value)} />
              <Field label="Till" type="date" value={form.delivery_to} disabled={isLocked} onChange={(value) => updateField("delivery_to", value)} />
              <Field label="Eller månad" type="month" value={form.delivery_month} disabled={isLocked} onChange={(value) => updateField("delivery_month", value)} />
            </div>
            <p className="text-xs text-muted-foreground">
              Leveransdatum eller, om det exakta datumet inte är känt, leveransmånad.
            </p>
          </div>
          <label className="space-y-1 md:col-span-2">
            <span className="text-sm font-medium">Beskrivning</span>
            <textarea
              value={form.description}
              disabled={isLocked}
              onChange={(event) => updateField("description", event.target.value)}
              className="min-h-[72px] w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-60"
            />
          </label>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-primary" />
            Agentens bedömning
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-[1fr_180px]">
          <label className="space-y-1">
            <span className="text-sm font-medium">Sammanfattning</span>
            <textarea
              value={form.agent_summary}
              disabled={isLocked}
              onChange={(event) => updateField("agent_summary", event.target.value)}
              className="min-h-[80px] w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-60"
            />
          </label>
          <Field
            label="Konfidens"
            type="number"
            value={form.agent_confidence ?? ""}
            disabled={isLocked}
            onChange={(value) => updateField("agent_confidence", value === "" ? null : Number(value))}
          />
          <label className="space-y-1 md:col-span-2">
            <span className="text-sm font-medium">Varningar</span>
            <textarea
              value={form.agent_warnings}
              disabled={isLocked}
              onChange={(event) => updateField("agent_warnings", event.target.value)}
              className="min-h-[72px] w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-60"
              placeholder="En varning per rad"
            />
          </label>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Fakturarader</CardTitle>
            <CardDescription>
              Artiklar, konto och moms visas så att utkastet kan korrigeras innan utfärdande.
            </CardDescription>
          </div>
          {!isLocked && (
            <Button variant="outline" size="sm" onClick={addRow} className="gap-2">
              <Plus className="h-4 w-4" />
              Rad
            </Button>
          )}
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full min-w-[1060px] text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="p-3 text-left font-medium text-muted-foreground">Artikel</th>
                <th className="p-3 text-left font-medium text-muted-foreground">Beskrivning</th>
                <th className="p-3 text-right font-medium text-muted-foreground">Antal</th>
                <th className="p-3 text-left font-medium text-muted-foreground">Enhet</th>
                <th className="p-3 text-right font-medium text-muted-foreground">Pris</th>
                <th className="p-3 text-left font-medium text-muted-foreground">Moms</th>
                <th className="p-3 text-left font-medium text-muted-foreground">Konto</th>
                <th className="p-3 text-left font-medium text-muted-foreground">Källa</th>
                <th className="p-3 text-right font-medium text-muted-foreground">Total</th>
                <th className="w-12 p-3" />
              </tr>
            </thead>
            <tbody>
              {form.rows.map((row: DraftRow, index: number) => (
                <tr key={index} className="border-b last:border-0 align-top">
                  <td className="p-2">
                    <select
                      value={row.article_id || ""}
                      disabled={isLocked}
                      onChange={(event) => applyArticle(index, event.target.value)}
                      className="w-36 rounded border bg-background px-2 py-1.5 text-sm disabled:opacity-60"
                    >
                      <option value="">Ingen</option>
                      {articles.map((article: any) => (
                        <option key={article.id} value={article.id}>
                          {article.article_number} {article.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="p-2">
                    <input
                      value={row.description || ""}
                      disabled={isLocked}
                      onChange={(event) => updateRow(index, "description", event.target.value)}
                      className="w-56 rounded border bg-background px-2 py-1.5 text-sm disabled:opacity-60"
                    />
                  </td>
                  <td className="p-2">
                    <input
                      type="text"
                      inputMode="decimal"
                      aria-label="Antal"
                      value={row.quantity}
                      disabled={isLocked}
                      onChange={(event) => updateRow(index, "quantity", event.target.value)}
                      className="w-20 rounded border bg-background px-2 py-1.5 text-right font-mono text-sm disabled:opacity-60"
                    />
                  </td>
                  <td className="p-2">
                    <input
                      aria-label="Enhet"
                      value={row.unit || ""}
                      disabled={isLocked}
                      placeholder="st"
                      onChange={(event) => updateRow(index, "unit", event.target.value)}
                      className="w-16 rounded border bg-background px-2 py-1.5 text-sm disabled:opacity-60"
                    />
                  </td>
                  <td className="p-2">
                    <input
                      type="number"
                      value={row.unit_price ?? 0}
                      disabled={isLocked}
                      onChange={(event) => updateRow(index, "unit_price", Number(event.target.value))}
                      className="w-28 rounded border bg-background px-2 py-1.5 text-right font-mono text-sm disabled:opacity-60"
                    />
                  </td>
                  <td className="p-2">
                    <select
                      value={row.vat_code || "MP1"}
                      disabled={isLocked}
                      onChange={(event) => updateRow(index, "vat_code", event.target.value)}
                      className="w-20 rounded border bg-background px-2 py-1.5 text-sm disabled:opacity-60"
                    >
                      {VAT_CODES.map((code) => (
                        <option key={code} value={code}>{code}</option>
                      ))}
                    </select>
                  </td>
                  <td className="p-2">
                    <select
                      value={row.revenue_account || "3010"}
                      disabled={isLocked}
                      onChange={(event) => updateRow(index, "revenue_account", event.target.value)}
                      className="w-44 rounded border bg-background px-2 py-1.5 text-sm disabled:opacity-60"
                    >
                      {accounts.map((account: any) => (
                        <option key={account.code} value={account.code}>
                          {account.code} {account.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="p-2">
                    <input
                      value={row.source_note || ""}
                      disabled={isLocked}
                      onChange={(event) => updateRow(index, "source_note", event.target.value)}
                      className="w-40 rounded border bg-background px-2 py-1.5 text-sm disabled:opacity-60"
                    />
                  </td>
                  <td className="p-3 text-right font-mono font-medium">
                    {draft.rows?.[index]?.amount_inc_vat !== undefined
                      ? formatCurrency(draft.rows[index].amount_inc_vat)
                      : "-"}
                  </td>
                  <td className="p-2 text-right">
                    {!isLocked && form.rows.length > 1 && (
                      <Button variant="ghost" size="sm" onClick={() => removeRow(index)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="grid gap-4 p-4 sm:grid-cols-3">
          <Amount label="Exkl. moms" value={draft.amount_ex_vat || 0} />
          <Amount label="Moms" value={draft.vat_amount || 0} />
          <Amount label="Att fakturera" value={draft.amount_inc_vat || 0} strong />
        </CardContent>
      </Card>

      {message && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <AlertTriangle className="h-4 w-4" />
          {message}
        </p>
      )}

      {issuedInvoiceId && (
        <Link href={`/invoices/${issuedInvoiceId}`} className="text-sm text-primary hover:underline">
          Visa den utfärdade fakturan
        </Link>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {!isLocked && (
          <>
            <Button onClick={issue} disabled={!!working} className="gap-2">
              <FileText className="h-4 w-4" />
              {working === "issue" ? "Utfärdar..." : "Utfärda"}
            </Button>
            <Button variant="outline" onClick={save} disabled={!!working} className="gap-2">
              <Save className="h-4 w-4" />
              {working === "save" ? "Sparar..." : "Spara ändringar"}
            </Button>
            <Button variant="outline" onClick={reject} disabled={!!working} className="gap-2">
              <XCircle className="h-4 w-4" />
              {working === "reject" ? "Avvisar..." : "Avvisa utkast"}
            </Button>
            <span className="font-mono text-xs text-muted-foreground">
              Bokförs och låses vid utfärdande
            </span>
          </>
        )}
        {isIssued && (
          <>
            <p className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="h-4 w-4" />
              {draft.status === "issued" ? "Fakturan är utfärdad och bokförd." : "Fakturan är skickad och bokförd."}
            </p>
            {draft.approved_invoice_id && (
              <>
                <Button variant="outline" onClick={downloadPdf} disabled={!!working} className="gap-2">
                  <Download className="h-4 w-4" />
                  {working === "pdf" ? "Hämtar..." : "Ladda ner PDF"}
                </Button>
                <Button variant="outline" onClick={() => router.push(`/invoices/${draft.approved_invoice_id}`)}>
                  Visa fakturan
                </Button>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  disabled = false,
  placeholder,
}: {
  label: string;
  value: string | number;
  onChange: (value: string) => void;
  type?: string;
  disabled?: boolean;
  placeholder?: string;
}) {
  return (
    <label className="space-y-1">
      <span className="text-sm font-medium">{label}</span>
      <input
        type={type}
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-60"
      />
    </label>
  );
}

function Amount({ label, value, strong = false }: { label: string; value: number; strong?: boolean }) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className={`font-mono text-xl ${strong ? "font-bold" : "font-semibold"}`}>
        {formatCurrency(value)}
      </p>
    </div>
  );
}
