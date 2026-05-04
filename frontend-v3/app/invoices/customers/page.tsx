"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Building2, Plus, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useCustomers } from "@/hooks/useData";
import { api, Customer } from "@/lib/api";

export default function CustomersPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [name, setName] = useState("");
  const [orgNumber, setOrgNumber] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");
  const [paymentTermsDays, setPaymentTermsDays] = useState("30");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data, isLoading } = useCustomers(search || undefined);
  const customers: Customer[] = data?.customers || [];

  const inputClass =
    "w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.createCustomer({
        name: name.trim(),
        org_number: orgNumber.trim() || undefined,
        email: email.trim() || undefined,
        address: address.trim() || undefined,
        payment_terms_days: parseInt(paymentTermsDays) || 0,
      });
      setName("");
      setOrgNumber("");
      setEmail("");
      setAddress("");
      setPaymentTermsDays("30");
      await queryClient.invalidateQueries({ queryKey: ["customers"] });
    } catch (err: any) {
      const msg = err?.response?.data?.detail?.error || err?.message || "Kunde inte skapa kunden.";
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1200px] space-y-6 p-4 lg:p-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight lg:text-3xl">
            <Building2 className="h-6 w-6 text-primary" />
            Kunder
          </h1>
          <p className="mt-1 text-muted-foreground">Kundregister för manuell fakturering och agentutkast.</p>
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
              <h2 className="font-semibold">Ny kund</h2>
            </div>
            {error && <p className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">{error}</p>}
            <div className="grid gap-3 md:grid-cols-4">
              <div className="md:col-span-2">
                <label className="mb-1 block text-sm font-medium">Namn</label>
                <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Organisationsnummer</label>
                <input className={inputClass} value={orgNumber} onChange={(e) => setOrgNumber(e.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Betalningsvillkor</label>
                <input className={inputClass} inputMode="numeric" value={paymentTermsDays} onChange={(e) => setPaymentTermsDays(e.target.value)} />
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium">E-post</label>
                <input className={inputClass} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Adress</label>
                <input className={inputClass} value={address} onChange={(e) => setAddress(e.target.value)} />
              </div>
            </div>
            <Button type="submit" disabled={submitting}>{submitting ? "Sparar..." : "Skapa kund"}</Button>
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
                placeholder="Sök namn eller organisationsnummer..."
              />
            </div>
          </div>
          {isLoading ? (
            <div className="space-y-3 p-6">
              {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
            </div>
          ) : customers.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">Inga kunder hittades.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="p-4 text-left font-medium text-muted-foreground">Kund</th>
                    <th className="p-4 text-left font-medium text-muted-foreground">Organisationsnummer</th>
                    <th className="p-4 text-left font-medium text-muted-foreground">E-post</th>
                    <th className="p-4 text-left font-medium text-muted-foreground">Adress</th>
                    <th className="p-4 text-right font-medium text-muted-foreground">Villkor</th>
                  </tr>
                </thead>
                <tbody>
                  {customers.map((customer) => (
                    <tr key={customer.id} className="border-b last:border-0">
                      <td className="p-4 font-medium">{customer.name}</td>
                      <td className="p-4 font-mono">{customer.org_number || "-"}</td>
                      <td className="p-4">{customer.email || "-"}</td>
                      <td className="p-4">{customer.address || "-"}</td>
                      <td className="p-4 text-right">{customer.payment_terms_days} dagar</td>
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
