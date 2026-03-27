"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { Plus, Trash2, ArrowLeft, Save } from "lucide-react";

const VAT_CODES = [
  { code: "MP1", label: "MP1 (25%)", rate: 0.25 },
  { code: "MP2", label: "MP2 (12%)", rate: 0.12 },
  { code: "MP3", label: "MP3 (6%)", rate: 0.06 },
  { code: "MF", label: "MF (0%)", rate: 0 },
];

function vatRate(code: string): number {
  return VAT_CODES.find((v) => v.code === code)?.rate ?? 0;
}

function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

function plus30(): string {
  const d = new Date();
  d.setDate(d.getDate() + 30);
  return d.toISOString().slice(0, 10);
}

interface InvoiceRowData {
  description: string;
  quantity: string;
  unitPrice: string;
  vatCode: string;
}

const emptyRow = (): InvoiceRowData => ({
  description: "",
  quantity: "1",
  unitPrice: "",
  vatCode: "MP1",
});

function formatSEK(ore: number): string {
  return new Intl.NumberFormat("sv-SE", {
    style: "currency",
    currency: "SEK",
  }).format(ore / 100);
}

export default function NewInvoicePage() {
  const router = useRouter();

  // Customer info
  const [customerName, setCustomerName] = useState("");
  const [orgNumber, setOrgNumber] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");

  // Dates
  const [invoiceDate, setInvoiceDate] = useState(todayStr);
  const [dueDate, setDueDate] = useState(plus30);

  // Rows
  const [rows, setRows] = useState<InvoiceRowData[]>([emptyRow()]);

  // State
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateRow = (index: number, field: keyof InvoiceRowData, value: string) => {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, [field]: value } : r)));
  };

  const addRow = () => setRows((prev) => [...prev, emptyRow()]);

  const removeRow = (index: number) => {
    if (rows.length <= 1) return;
    setRows((prev) => prev.filter((_, i) => i !== index));
  };

  // Computed totals
  const computedRows = useMemo(
    () =>
      rows.map((r) => {
        const qty = parseInt(r.quantity) || 0;
        const price = Math.round(parseFloat(r.unitPrice) * 100) || 0; // öre
        const exVat = qty * price;
        const vat = Math.round(exVat * vatRate(r.vatCode));
        const incVat = exVat + vat;
        return { exVat, vat, incVat, vatCode: r.vatCode };
      }),
    [rows]
  );

  const totalExVat = computedRows.reduce((s, r) => s + r.exVat, 0);
  const totalVat = computedRows.reduce((s, r) => s + r.vat, 0);
  const totalIncVat = totalExVat + totalVat;

  // VAT breakdown by code
  const vatBreakdown = useMemo(() => {
    const map: Record<string, number> = {};
    computedRows.forEach((r) => {
      if (r.vat > 0) {
        map[r.vatCode] = (map[r.vatCode] || 0) + r.vat;
      }
    });
    return map;
  }, [computedRows]);

  const handleSubmit = async () => {
    if (!customerName.trim()) {
      setError("Kundnamn krävs");
      return;
    }
    const hasEmptyRow = rows.some(
      (r) => !r.description.trim() || !r.quantity || !r.unitPrice
    );
    if (hasEmptyRow) {
      setError("Alla rader måste ha beskrivning, antal och à-pris");
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      const payload = {
        customer_name: customerName.trim(),
        customer_org_number: orgNumber.trim() || undefined,
        customer_email: email.trim() || undefined,
        invoice_date: invoiceDate,
        due_date: dueDate,
        description: address.trim() || undefined,
        rows: rows.map((r) => ({
          description: r.description,
          quantity: parseInt(r.quantity) || 1,
          unit_price: Math.round(parseFloat(r.unitPrice) * 100) || 0,
          vat_code: r.vatCode,
        })),
      };
      await api.createInvoice(payload);
      router.push("/invoices");
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail?.error ||
        err?.response?.data?.detail ||
        err?.message ||
        "Något gick fel";
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setSubmitting(false);
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
          <h2 className="text-lg font-semibold">Kunduppgifter</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">
                Kundnamn <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={customerName}
                onChange={(e) => setCustomerName(e.target.value)}
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
                onChange={(e) => setOrgNumber(e.target.value)}
                placeholder="556123-4567"
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">E-post</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="faktura@foretag.se"
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Adress</label>
              <input
                type="text"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="Storgatan 1, 111 22 Stockholm"
                className={inputClass}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Dates */}
      <Card>
        <CardContent className="p-6 space-y-4">
          <h2 className="text-lg font-semibold">Datum</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">
                Fakturadatum
              </label>
              <input
                type="date"
                value={invoiceDate}
                onChange={(e) => setInvoiceDate(e.target.value)}
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
        </CardContent>
      </Card>

      {/* Invoice rows */}
      <Card>
        <CardContent className="p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Fakturarader</h2>
            <Button variant="outline" size="sm" onClick={addRow}>
              <Plus className="h-4 w-4 mr-1" />
              Lägg till rad
            </Button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-left p-3 font-medium text-muted-foreground">
                    Beskrivning
                  </th>
                  <th className="text-left p-3 font-medium text-muted-foreground w-20">
                    Antal
                  </th>
                  <th className="text-left p-3 font-medium text-muted-foreground w-28">
                    À-pris (kr)
                  </th>
                  <th className="text-left p-3 font-medium text-muted-foreground w-32">
                    Moms
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
                        type="number"
                        min="1"
                        value={row.quantity}
                        onChange={(e) =>
                          updateRow(i, "quantity", e.target.value)
                        }
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
                    <td className="p-2 text-right font-mono font-medium whitespace-nowrap">
                      {formatSEK(computedRows[i]?.incVat || 0)}
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
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Totalt ex moms</span>
              <span className="font-mono font-medium">
                {formatSEK(totalExVat)}
              </span>
            </div>
            {Object.entries(vatBreakdown).map(([code, amount]) => {
              const info = VAT_CODES.find((v) => v.code === code);
              return (
                <div key={code} className="flex justify-between">
                  <span className="text-muted-foreground">
                    Moms {info?.label || code}
                  </span>
                  <span className="font-mono">{formatSEK(amount)}</span>
                </div>
              );
            })}
            {totalVat > 0 && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Total moms</span>
                <span className="font-mono">{formatSEK(totalVat)}</span>
              </div>
            )}
            <div className="flex justify-between border-t pt-2 text-base font-semibold">
              <span>Totalt inkl moms</span>
              <span className="font-mono">{formatSEK(totalIncVat)}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex items-center justify-end gap-3">
        <Button
          variant="outline"
          onClick={() => router.push("/invoices")}
          disabled={submitting}
        >
          Avbryt
        </Button>
        <Button onClick={handleSubmit} disabled={submitting}>
          <Save className="h-4 w-4 mr-2" />
          {submitting ? "Sparar..." : "Spara som utkast"}
        </Button>
      </div>
    </div>
  );
}
