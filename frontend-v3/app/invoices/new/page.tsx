"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useArticles, useCustomers } from "@/hooks/useData";
import { api, Article, Customer, InvoiceDraftPayload, IssuedInvoice } from "@/lib/api";
import { describeInvoiceError, downloadInvoicePdf, normaliseQuantity } from "@/lib/fakturering";
import { Plus, Trash2, ArrowLeft, Save, FileText, Download, CheckCircle2 } from "lucide-react";

const VAT_CODES = [
  { code: "MP1", label: "MP1 (25%)", rate: 0.25 },
  { code: "MP2", label: "MP2 (12%)", rate: 0.12 },
  { code: "MP3", label: "MP3 (6%)", rate: 0.06 },
  { code: "MF", label: "MF (0%)", rate: 0 },
];

function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

function plus30(): string {
  const d = new Date();
  d.setDate(d.getDate() + 30);
  return d.toISOString().slice(0, 10);
}

function datePlusDays(dateString: string, days: number): string {
  const d = new Date(`${dateString}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

interface InvoiceRowData {
  articleId: string;
  description: string;
  /** As typed: "7,5" or "7.5". */
  quantity: string;
  unit: string;
  unitPrice: string;
  vatCode: string;
  revenueAccount: string;
}

interface InvoicePreview {
  rows: {
    index: number;
    amount_ex_vat: number;
    vat_amount: number;
    amount_inc_vat: number;
    vat_code: string;
  }[];
  vat_breakdown: {
    vat_code: string;
    vat_rate: number;
    amount_ex_vat: number;
    vat_amount: number;
    amount_inc_vat: number;
  }[];
  totals: {
    amount_ex_vat: number;
    vat_amount: number;
    amount_inc_vat: number;
  };
}

const emptyRow = (): InvoiceRowData => ({
  articleId: "",
  description: "",
  quantity: "1",
  unit: "",
  unitPrice: "",
  vatCode: "MP1",
  revenueAccount: "3010",
});

function formatSEK(ore: number): string {
  return new Intl.NumberFormat("sv-SE", {
    style: "currency",
    currency: "SEK",
  }).format(ore / 100);
}

export default function NewInvoicePage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: customersData } = useCustomers();
  const { data: articlesData } = useArticles();
  const customers: Customer[] = customersData?.customers || [];
  const articles: Article[] = articlesData?.articles || [];

  // Customer info
  const [selectedCustomerId, setSelectedCustomerId] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [orgNumber, setOrgNumber] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");
  const [reference, setReference] = useState("");
  const [invoiceNumber, setInvoiceNumber] = useState("");

  // Dates
  const [invoiceDate, setInvoiceDate] = useState(todayStr);
  const [dueDate, setDueDate] = useState(plus30);
  const [deliveryFrom, setDeliveryFrom] = useState("");
  const [deliveryTo, setDeliveryTo] = useState("");
  const [deliveryMonth, setDeliveryMonth] = useState("");

  // Rows
  const [rows, setRows] = useState<InvoiceRowData[]>([emptyRow()]);

  // State
  // The draft this page has saved; a second save or issue updates it.
  const [draftId, setDraftId] = useState<string | null>(null);
  const [issued, setIssued] = useState<IssuedInvoice | null>(null);
  const [submitting, setSubmitting] = useState<"save" | "issue" | "pdf" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<InvoicePreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const applyCustomer = (customerId: string) => {
    setSelectedCustomerId(customerId);
    const customer = customers.find((c) => c.id === customerId);
    if (!customer) return;
    setCustomerName(customer.name || "");
    setOrgNumber(customer.org_number || "");
    setEmail(customer.email || "");
    setAddress(customer.address || "");
    setDueDate(datePlusDays(invoiceDate, customer.payment_terms_days ?? 30));
  };

  const updateRow = (index: number, field: keyof InvoiceRowData, value: string) => {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, [field]: value } : r)));
  };

  const applyArticle = (index: number, articleId: string) => {
    const article = articles.find((item) => item.id === articleId);
    if (!article) {
      updateRow(index, "articleId", "");
      return;
    }
    setRows((prev) =>
      prev.map((row, rowIndex) =>
        rowIndex === index
          ? {
              ...row,
              articleId: article.id,
              description: article.description || article.name,
              unit: article.unit || row.unit,
              unitPrice: (article.unit_price / 100).toString(),
              vatCode: article.vat_code,
              revenueAccount: article.revenue_account,
            }
          : row
      )
    );
  };

  const addRow = () => setRows((prev) => [...prev, emptyRow()]);

  const removeRow = (index: number) => {
    if (rows.length <= 1) return;
    setRows((prev) => prev.filter((_, i) => i !== index));
  };

  const previewPayload = useMemo(
    () => ({
      rows: rows.map((r) => ({
        description: r.description,
        quantity: normaliseQuantity(r.quantity) || "1",
        unit: r.unit.trim() || null,
        unit_price: Math.round(parseFloat(r.unitPrice) * 100) || 0,
        vat_code: r.vatCode,
        revenue_account: r.revenueAccount || undefined,
      })),
    }),
    [rows],
  );

  const loadPreview = useCallback(async () => {
    try {
      const response = await api.previewInvoice(previewPayload);
      setPreview(response);
      setPreviewError(null);
    } catch (err: any) {
      setPreview(null);
      const msg =
        err?.response?.data?.detail?.error ||
        err?.response?.data?.detail ||
        err?.message ||
        "Kunde inte förhandsgranska fakturan";
      setPreviewError(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
  }, [previewPayload]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      loadPreview();
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [loadPreview]);

  const validate = (): boolean => {
    if (!customerName.trim()) {
      setError("Kundnamn krävs");
      return false;
    }
    const hasEmptyRow = rows.some(
      (r) => !r.description.trim() || !r.quantity.trim() || !r.unitPrice
    );
    if (hasEmptyRow) {
      setError("Alla rader måste ha beskrivning, antal och à-pris");
      return false;
    }
    setError(null);
    return true;
  };

  const draftPayload = (): InvoiceDraftPayload => ({
    customer_id: selectedCustomerId || null,
    customer_name: customerName.trim(),
    customer_org_number: orgNumber.trim() || null,
    customer_email: email.trim() || null,
    customer_address: address.trim() || null,
    reference: reference.trim() || null,
    invoice_number: invoiceNumber.trim() || null,
    invoice_date: invoiceDate,
    due_date: dueDate,
    delivery_from: deliveryFrom || null,
    delivery_to: deliveryTo || null,
    delivery_month: deliveryMonth || null,
    status: "draft",
    rows: rows.map((r) => ({
      article_id: r.articleId || null,
      description: r.description,
      quantity: normaliseQuantity(r.quantity),
      unit: r.unit.trim() || null,
      unit_price: Math.round(parseFloat(r.unitPrice) * 100) || 0,
      vat_code: r.vatCode,
      revenue_account: r.revenueAccount || null,
      source_note: null,
    })),
    agent_notes: {
      summary: null,
      confidence: null,
      warnings: [],
    },
  });

  // Creates the draft the first time, then replaces it (PUT takes it whole).
  const saveDraft = async (): Promise<string> => {
    const payload = draftPayload();
    const draft = draftId
      ? await api.updateInvoiceDraft(draftId, payload)
      : await api.createInvoiceDraft(payload);
    setDraftId(draft.id);
    await queryClient.invalidateQueries({ queryKey: ["invoice-drafts"] });
    return draft.id;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setSubmitting("save");
    try {
      const id = await saveDraft();
      router.push(`/invoices/drafts/${id}`);
    } catch (err: unknown) {
      setError(describeInvoiceError(err, "Kunde inte spara utkastet."));
    } finally {
      setSubmitting(null);
    }
  };

  // Utfärda (SPEC-fakturering.md §5): save the draft, then issue it. The
  // voucher is posted and the invoice locked; all or nothing.
  const handleIssue = async () => {
    if (!validate()) return;
    setSubmitting("issue");
    let saved = false;
    try {
      const id = await saveDraft();
      saved = true;
      const result = await api.issueInvoiceDraft(id);
      setIssued(result);
      await queryClient.invalidateQueries({ queryKey: ["invoice-drafts"] });
      await queryClient.invalidateQueries({ queryKey: ["invoices"] });
    } catch (err: unknown) {
      setError(
        describeInvoiceError(err, "Kunde inte utfärda fakturan. Ingenting bokfördes.") +
          (saved ? " Utkastet är sparat." : "")
      );
    } finally {
      setSubmitting(null);
    }
  };

  const handleDownload = async () => {
    if (!issued) return;
    setSubmitting("pdf");
    try {
      await downloadInvoicePdf({
        id: issued.invoice_id,
        invoice_number: issued.invoice_number,
        pdf_url: issued.pdf_url,
      });
    } catch (err: unknown) {
      setError(describeInvoiceError(err, "Kunde inte ladda ner PDF:en."));
    } finally {
      setSubmitting(null);
    }
  };

  const inputClass =
    "w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring";

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1000px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">
            Ny faktura
          </h1>
          <p className="text-muted-foreground mt-1">
            Skapa en ny kundfaktura
          </p>
        </div>
        <Button variant="outline" onClick={() => router.push("/invoices")}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Tillbaka
        </Button>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:bg-red-950 dark:border-red-800 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Customer info */}
      <Card>
        <CardContent className="p-6 space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-lg font-semibold">Kunduppgifter</h2>
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/invoices/customers")}
            >
              Hantera kunder
            </Button>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">
              Använd sparad kund
            </label>
            <select
              value={selectedCustomerId}
              onChange={(e) => applyCustomer(e.target.value)}
              className={inputClass}
            >
              <option value="">Välj kund eller fyll i manuellt</option>
              {customers.map((customer) => (
                <option key={customer.id} value={customer.id}>
                  {customer.name}
                  {customer.org_number ? ` · ${customer.org_number}` : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">
                Kundnamn <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={customerName}
                onChange={(e) => {
                  setSelectedCustomerId("");
                  setCustomerName(e.target.value);
                }}
                placeholder="Företag AB"
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">
                Organisationsnummer
              </label>
              <input
                type="text"
                value={orgNumber}
                onChange={(e) => {
                  setSelectedCustomerId("");
                  setOrgNumber(e.target.value);
                }}
                placeholder="556123-4567"
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">E-post</label>
              <input
                type="email"
                value={email}
                onChange={(e) => {
                  setSelectedCustomerId("");
                  setEmail(e.target.value);
                }}
                placeholder="faktura@foretag.se"
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Er referens</label>
              <input
                type="text"
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                placeholder="Kundens kontaktperson"
                className={inputClass}
              />
            </div>
            <div className="sm:col-span-2">
              <label className="block text-sm font-medium mb-1">Kundadress</label>
              <textarea
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder={"Storgatan 1\n111 22 Stockholm"}
                rows={3}
                className={inputClass}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Dates */}
      <Card>
        <CardContent className="p-6 space-y-4">
          <h2 className="text-lg font-semibold">Nummer och datum</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">
                Fakturanummer
              </label>
              <input
                type="text"
                value={invoiceNumber}
                onChange={(e) => setInvoiceNumber(e.target.value)}
                placeholder="2026-1"
                className={`${inputClass} font-mono`}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">
                Fakturadatum
              </label>
              <input
                type="date"
                value={invoiceDate}
                onChange={(e) => {
                  const nextDate = e.target.value;
                  setInvoiceDate(nextDate);
                  const customer = customers.find((c) => c.id === selectedCustomerId);
                  if (customer) {
                    setDueDate(datePlusDays(nextDate, customer.payment_terms_days ?? 30));
                  }
                }}
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">
                Förfallodatum
              </label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className={inputClass}
              />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Leverans från</label>
              <input
                type="date"
                value={deliveryFrom}
                onChange={(e) => setDeliveryFrom(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Leverans till</label>
              <input
                type="date"
                value={deliveryTo}
                onChange={(e) => setDeliveryTo(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Eller leveransmånad</label>
              <input
                type="month"
                value={deliveryMonth}
                onChange={(e) => setDeliveryMonth(e.target.value)}
                className={inputClass}
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Leveransdatum eller, om det exakta datumet inte är känt, leveransmånad.
          </p>
        </CardContent>
      </Card>

      {/* Invoice rows */}
      <Card>
        <CardContent className="p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Fakturarader</h2>
            <div className="flex flex-wrap justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => router.push("/invoices/articles")}
              >
                Hantera artiklar
              </Button>
              <Button variant="outline" size="sm" onClick={addRow}>
                <Plus className="h-4 w-4 mr-1" />
                Lägg till rad
              </Button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[1060px] text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-left p-3 font-medium text-muted-foreground w-56">
                    Artikel
                  </th>
                  <th className="text-left p-3 font-medium text-muted-foreground">
                    Beskrivning
                  </th>
                  <th className="text-left p-3 font-medium text-muted-foreground w-20">
                    Antal
                  </th>
                  <th className="text-left p-3 font-medium text-muted-foreground w-20">
                    Enhet
                  </th>
                  <th className="text-left p-3 font-medium text-muted-foreground w-28">
                    À-pris (kr)
                  </th>
                  <th className="text-left p-3 font-medium text-muted-foreground w-32">
                    Moms
                  </th>
                  <th className="text-left p-3 font-medium text-muted-foreground w-28">
                    Konto
                  </th>
                  <th className="text-right p-3 font-medium text-muted-foreground w-28">
                    Totalt inkl moms
                  </th>
                  <th className="p-3 w-10" />
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="p-2 align-top">
                      <select
                        value={row.articleId}
                        onChange={(e) => applyArticle(i, e.target.value)}
                        className={inputClass}
                      >
                        <option value="">Välj artikel</option>
                        {articles.map((article) => (
                          <option key={article.id} value={article.id}>
                            {article.article_number} · {article.name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="p-2">
                      <input
                        type="text"
                        value={row.description}
                        onChange={(e) =>
                          updateRow(i, "description", e.target.value)
                        }
                        placeholder="Beskrivning"
                        className={inputClass}
                      />
                    </td>
                    <td className="p-2">
                      <input
                        type="text"
                        inputMode="decimal"
                        aria-label="Antal"
                        value={row.quantity}
                        onChange={(e) =>
                          updateRow(i, "quantity", e.target.value)
                        }
                        placeholder="7,5"
                        className={`${inputClass} text-right font-mono`}
                      />
                    </td>
                    <td className="p-2">
                      <input
                        type="text"
                        aria-label="Enhet"
                        value={row.unit}
                        onChange={(e) => updateRow(i, "unit", e.target.value)}
                        placeholder="st"
                        className={inputClass}
                      />
                    </td>
                    <td className="p-2">
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={row.unitPrice}
                        onChange={(e) =>
                          updateRow(i, "unitPrice", e.target.value)
                        }
                        placeholder="0.00"
                        className={inputClass}
                      />
                    </td>
                    <td className="p-2">
                      <select
                        value={row.vatCode}
                        onChange={(e) =>
                          updateRow(i, "vatCode", e.target.value)
                        }
                        className={inputClass}
                      >
                        {VAT_CODES.map((v) => (
                          <option key={v.code} value={v.code}>
                            {v.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="p-2">
                      <input
                        type="text"
                        value={row.revenueAccount}
                        onChange={(e) =>
                          updateRow(i, "revenueAccount", e.target.value)
                        }
                        placeholder="3010"
                        className={`${inputClass} font-mono`}
                      />
                    </td>
                    <td className="p-2 text-right font-mono font-medium whitespace-nowrap">
                      {formatSEK(preview?.rows?.[i]?.amount_inc_vat || 0)}
                    </td>
                    <td className="p-2">
                      <button
                        type="button"
                        onClick={() => removeRow(i)}
                        disabled={rows.length <= 1}
                        className="p-1 text-muted-foreground hover:text-red-500 disabled:opacity-30 transition-colors"
                        title="Ta bort rad"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Summary */}
      <Card>
        <CardContent className="p-6 space-y-3">
          <h2 className="text-lg font-semibold">Summering</h2>
          {previewError && (
            <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300">
              {previewError}
            </p>
          )}
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Totalt ex moms</span>
              <span className="font-mono font-medium">
                {formatSEK(preview?.totals.amount_ex_vat || 0)}
              </span>
            </div>
            {(preview?.vat_breakdown || []).map((vat) => {
              const info = VAT_CODES.find((v) => v.code === vat.vat_code);
              return (
                <div key={vat.vat_code} className="flex justify-between">
                  <span className="text-muted-foreground">
                    Moms {info?.label || vat.vat_code}
                  </span>
                  <span className="font-mono">{formatSEK(vat.vat_amount)}</span>
                </div>
              );
            })}
            {(preview?.totals.vat_amount || 0) > 0 && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Total moms</span>
                <span className="font-mono">{formatSEK(preview?.totals.vat_amount || 0)}</span>
              </div>
            )}
            <div className="flex justify-between border-t pt-2 text-base font-semibold">
              <span>Totalt inkl moms</span>
              <span className="font-mono">{formatSEK(preview?.totals.amount_inc_vat || 0)}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Actions */}
      {issued ? (
        <div className="flex flex-wrap items-center justify-end gap-3">
          <p className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="h-4 w-4" />
            Faktura {issued.invoice_number} är utfärdad och bokförd.
          </p>
          <Button variant="outline" onClick={handleDownload} disabled={!!submitting}>
            <Download className="h-4 w-4 mr-2" />
            {submitting === "pdf" ? "Hämtar..." : "Ladda ner PDF"}
          </Button>
          <Button onClick={() => router.push(`/invoices/${issued.invoice_id}`)}>
            Visa fakturan
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-end gap-3">
          <span className="font-mono text-xs text-muted-foreground">
            Bokförs och låses vid utfärdande
          </span>
          <Button
            variant="outline"
            onClick={() => router.push("/invoices")}
            disabled={!!submitting}
          >
            Avbryt
          </Button>
          <Button variant="outline" onClick={handleSubmit} disabled={!!submitting}>
            <Save className="h-4 w-4 mr-2" />
            {submitting === "save" ? "Sparar..." : "Spara som utkast"}
          </Button>
          <Button onClick={handleIssue} disabled={!!submitting}>
            <FileText className="h-4 w-4 mr-2" />
            {submitting === "issue" ? "Utfärdar..." : "Utfärda"}
          </Button>
        </div>
      )}
    </div>
  );
}
