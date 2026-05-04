"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Boxes, Plus, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useArticles } from "@/hooks/useData";
import { api, Article } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

const VAT_CODES = [
  { value: "MP1", label: "MP1 - 25%" },
  { value: "MP2", label: "MP2 - 12%" },
  { value: "MP3", label: "MP3 - 6%" },
  { value: "MF", label: "MF - 0%" },
];

export default function ArticlesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [articleNumber, setArticleNumber] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [unit, setUnit] = useState("h");
  const [unitPrice, setUnitPrice] = useState("");
  const [vatCode, setVatCode] = useState("MP1");
  const [revenueAccount, setRevenueAccount] = useState("3010");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data, isLoading } = useArticles(search || undefined);
  const articles: Article[] = data?.articles || [];

  const resetForm = () => {
    setArticleNumber("");
    setName("");
    setDescription("");
    setUnit("h");
    setUnitPrice("");
    setVatCode("MP1");
    setRevenueAccount("3010");
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.createArticle({
        article_number: articleNumber.trim(),
        name: name.trim(),
        description: description.trim() || undefined,
        unit: unit.trim() || "st",
        unit_price: Math.round((parseFloat(unitPrice) || 0) * 100),
        vat_code: vatCode,
        revenue_account: revenueAccount.trim(),
      });
      resetForm();
      await queryClient.invalidateQueries({ queryKey: ["articles"] });
    } catch (err: any) {
      const msg = err?.response?.data?.detail?.error || err?.message || "Kunde inte skapa artikeln.";
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setSubmitting(false);
    }
  };

  const inputClass =
    "w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

  return (
    <div className="mx-auto max-w-[1200px] space-y-6 p-4 lg:p-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight lg:text-3xl">
            <Boxes className="h-6 w-6 text-primary" />
            Artiklar
          </h1>
          <p className="mt-1 text-muted-foreground">Standardrader som agenten kan använda när fakturautkast skapas.</p>
        </div>
        <Link href="/invoices">
          <Button variant="outline">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Till fakturor
          </Button>
        </Link>
      </div>

      <Card>
        <CardContent className="p-5">
          <form onSubmit={submit} className="space-y-4">
            <div className="flex items-center gap-2">
              <Plus className="h-4 w-4 text-primary" />
              <h2 className="font-semibold">Ny artikel</h2>
            </div>
            {error && <p className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">{error}</p>}
            <div className="grid gap-3 md:grid-cols-4">
              <div>
                <label className="mb-1 block text-sm font-medium">Artikelnummer</label>
                <input className={inputClass} value={articleNumber} onChange={(e) => setArticleNumber(e.target.value)} required />
              </div>
              <div className="md:col-span-2">
                <label className="mb-1 block text-sm font-medium">Namn</label>
                <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Enhet</label>
                <input className={inputClass} value={unit} onChange={(e) => setUnit(e.target.value)} />
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="md:col-span-2">
                <label className="mb-1 block text-sm font-medium">Beskrivning</label>
                <input className={inputClass} value={description} onChange={(e) => setDescription(e.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Pris exkl. moms</label>
                <input className={inputClass} inputMode="decimal" value={unitPrice} onChange={(e) => setUnitPrice(e.target.value)} placeholder="1200" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Moms</label>
                <select className={inputClass} value={vatCode} onChange={(e) => setVatCode(e.target.value)}>
                  {VAT_CODES.map((code) => (
                    <option key={code.value} value={code.value}>{code.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="sm:w-48">
                <label className="mb-1 block text-sm font-medium">Intäktskonto</label>
                <input className={inputClass} value={revenueAccount} onChange={(e) => setRevenueAccount(e.target.value)} />
              </div>
              <Button type="submit" disabled={submitting}>{submitting ? "Sparar..." : "Skapa artikel"}</Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <div className="border-b p-4">
            <div className="relative max-w-md">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                className={`${inputClass} pl-9`}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Sök artikelnummer, namn eller beskrivning..."
              />
            </div>
          </div>
          {isLoading ? (
            <div className="space-y-3 p-6">
              {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
            </div>
          ) : articles.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">Inga artiklar hittades.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="p-4 text-left font-medium text-muted-foreground">Artikel</th>
                    <th className="p-4 text-left font-medium text-muted-foreground">Beskrivning</th>
                    <th className="p-4 text-left font-medium text-muted-foreground">Moms</th>
                    <th className="p-4 text-left font-medium text-muted-foreground">Konto</th>
                    <th className="p-4 text-right font-medium text-muted-foreground">Pris</th>
                  </tr>
                </thead>
                <tbody>
                  {articles.map((article) => (
                    <tr key={article.id} className="border-b last:border-0">
                      <td className="p-4">
                        <div className="font-mono text-xs text-muted-foreground">{article.article_number}</div>
                        <div className="font-medium">{article.name}</div>
                      </td>
                      <td className="max-w-[420px] p-4">{article.description || "-"}</td>
                      <td className="p-4">{article.vat_code}</td>
                      <td className="p-4 font-mono">{article.revenue_account}</td>
                      <td className="p-4 text-right font-mono">{formatCurrency(article.unit_price)} / {article.unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
