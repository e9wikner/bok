"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAccounts, usePeriods } from "@/hooks/useData";
import { api } from "@/lib/api";
import { Plus, Trash2, ArrowLeft, Check, AlertTriangle } from "lucide-react";

interface VoucherRowForm {
  account: string;
  description: string;
  debit: string;
  credit: string;
}

function emptyRow(): VoucherRowForm {
  return { account: "", description: "", debit: "", credit: "" };
}

function parseOre(value: string): number {
  const num = parseFloat(value.replace(",", "."));
  if (isNaN(num)) return 0;
  return Math.round(num * 100);
}

function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function NewVoucherPage() {
  const router = useRouter();
  const { data: accountsData } = useAccounts();
  const { data: periodsData } = usePeriods();

  const accounts = accountsData?.accounts || [];
  const periods = useMemo(() => periodsData?.periods || [], [periodsData]);

  const [date, setDate] = useState(todayStr());
  const [description, setDescription] = useState("");
  const [periodId, setPeriodId] = useState("");
  const [rows, setRows] = useState<VoucherRowForm[]>([emptyRow(), emptyRow()]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Auto-select period based on date
  const matchedPeriod = useMemo(() => {
    if (periodId) return periodId;
    if (!date || periods.length === 0) return "";
    const p = periods.find(
      (p: any) => date >= p.start_date && date <= p.end_date && !p.locked
    );
    return p?.id || "";
  }, [date, periods, periodId]);

  const totalDebit = useMemo(
    () => rows.reduce((sum, r) => sum + parseOre(r.debit), 0),
    [rows]
  );
  const totalCredit = useMemo(
    () => rows.reduce((sum, r) => sum + parseOre(r.credit), 0),
    [rows]
  );
  const isBalanced = totalDebit === totalCredit && totalDebit > 0;
  const diff = totalDebit - totalCredit;

  const updateRow = (idx: number, field: keyof VoucherRowForm, value: string) => {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, [field]: value } : r)));
  };

  const addRow = () => setRows((prev) => [...prev, emptyRow()]);

  const removeRow = (idx: number) => {
    if (rows.length <= 2) return;
    setRows((prev) => prev.filter((_, i) => i !== idx));
  };

  const canSave =
    isBalanced &&
    description.trim() !== "" &&
    (matchedPeriod || periodId) &&
    rows.every((r) => r.account !== "");

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      await api.createVoucher({
        series: "A",
        date,
        period_id: matchedPeriod || periodId,
        description: description.trim(),
        rows: rows.map((r) => ({
          account: r.account,
          debit: parseOre(r.debit),
          credit: parseOre(r.credit),
          description: r.description || undefined,
        })),
        auto_post: false,
      });
      router.push("/vouchers");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : detail?.error || "Något gick fel vid sparande"
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1000px] mx-auto">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="outline" size="sm" onClick={() => router.push("/vouchers")}>
          <ArrowLeft className="h-4 w-4 mr-1" />
          Tillbaka
        </Button>
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">
            Ny verifikation
          </h1>
          <p className="text-muted-foreground mt-1">
            Skapa en ny bokföringspost
          </p>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <Card className="border-red-300 bg-red-50 dark:bg-red-950/20">
          <CardContent className="p-4 text-red-700 dark:text-red-400 text-sm flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {error}
          </CardContent>
        </Card>
      )}

      {/* Basic info */}
      <Card>
        <CardContent className="p-4 space-y-4">
          <h2 className="font-semibold text-lg">Verifikationsinfo</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">
                Datum
              </label>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">
                Period
              </label>
              <select
                value={matchedPeriod || periodId}
                onChange={(e) => setPeriodId(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">Välj period...</option>
                {periods.map((p: any) => (
                  <option key={p.id} value={p.id} disabled={p.locked}>
                    {p.year}-{String(p.month).padStart(2, "0")}
                    {p.locked ? " (låst)" : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-1">
              <label className="block text-sm font-medium text-muted-foreground mb-1">
                Serie
              </label>
              <input
                type="text"
                value="A"
                disabled
                className="w-full px-3 py-2 rounded-lg border bg-muted text-sm"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">
              Beskrivning
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="T.ex. Konsultfaktura #1042"
              className="w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
        </CardContent>
      </Card>

      {/* Rows */}
      <Card>
        <CardContent className="p-4 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-lg">Konteringsrader</h2>
            <Button variant="outline" size="sm" onClick={addRow}>
              <Plus className="h-4 w-4 mr-1" />
              Lägg till rad
            </Button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-left p-2 font-medium text-muted-foreground">
                    Konto
                  </th>
                  <th className="text-left p-2 font-medium text-muted-foreground">
                    Beskrivning
                  </th>
                  <th className="text-right p-2 font-medium text-muted-foreground">
                    Debet (kr)
                  </th>
                  <th className="text-right p-2 font-medium text-muted-foreground">
                    Kredit (kr)
                  </th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => (
                  <tr key={idx} className="border-b last:border-0">
                    <td className="p-2">
                      <select
                        value={row.account}
                        onChange={(e) => updateRow(idx, "account", e.target.value)}
                        className="w-full px-2 py-1.5 rounded border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring min-w-[180px]"
                      >
                        <option value="">Välj konto...</option>
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
                        value={row.description}
                        onChange={(e) =>
                          updateRow(idx, "description", e.target.value)
                        }
                        placeholder="Valfri"
                        className="w-full px-2 py-1.5 rounded border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring min-w-[120px]"
                      />
                    </td>
                    <td className="p-2">
                      <input
                        type="text"
                        inputMode="decimal"
                        value={row.debit}
                        onChange={(e) => updateRow(idx, "debit", e.target.value)}
                        placeholder="0,00"
                        className="w-full px-2 py-1.5 rounded border bg-background text-sm text-right focus:outline-none focus:ring-2 focus:ring-ring min-w-[100px] font-mono"
                      />
                    </td>
                    <td className="p-2">
                      <input
                        type="text"
                        inputMode="decimal"
                        value={row.credit}
                        onChange={(e) => updateRow(idx, "credit", e.target.value)}
                        placeholder="0,00"
                        className="w-full px-2 py-1.5 rounded border bg-background text-sm text-right focus:outline-none focus:ring-2 focus:ring-ring min-w-[100px] font-mono"
                      />
                    </td>
                    <td className="p-2">
                      <button
                        onClick={() => removeRow(idx)}
                        disabled={rows.length <= 2}
                        className="p-1 rounded hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed text-muted-foreground hover:text-red-500 transition-colors"
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

      {/* Balance indicator */}
      <Card
        className={
          isBalanced
            ? "border-green-300 dark:border-green-700"
            : "border-red-300 dark:border-red-700"
        }
      >
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {isBalanced ? (
                <div className="h-6 w-6 rounded-full bg-green-500 flex items-center justify-center">
                  <Check className="h-4 w-4 text-white" />
                </div>
              ) : (
                <div className="h-6 w-6 rounded-full bg-red-500 flex items-center justify-center">
                  <AlertTriangle className="h-4 w-4 text-white" />
                </div>
              )}
              <span
                className={`font-medium ${
                  isBalanced
                    ? "text-green-700 dark:text-green-400"
                    : "text-red-700 dark:text-red-400"
                }`}
              >
                {isBalanced
                  ? "Balanserar"
                  : diff > 0
                  ? `Debet överstiger kredit med ${(Math.abs(diff) / 100).toFixed(2)} kr`
                  : diff < 0
                  ? `Kredit överstiger debet med ${(Math.abs(diff) / 100).toFixed(2)} kr`
                  : "Ange belopp"}
              </span>
            </div>
            <div className="flex gap-6 text-sm font-mono">
              <span className="text-muted-foreground">
                Debet:{" "}
                <span className="font-semibold text-foreground">
                  {(totalDebit / 100).toFixed(2)} kr
                </span>
              </span>
              <span className="text-muted-foreground">
                Kredit:{" "}
                <span className="font-semibold text-foreground">
                  {(totalCredit / 100).toFixed(2)} kr
                </span>
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex items-center gap-3 justify-end">
        <Button variant="outline" onClick={() => router.push("/vouchers")}>
          Avbryt
        </Button>
        <Button onClick={handleSave} disabled={!canSave || saving}>
          {saving ? "Sparar..." : "Spara som utkast"}
        </Button>
      </div>
    </div>
  );
}
