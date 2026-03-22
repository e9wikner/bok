"use client";

import { useState } from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useVouchers } from "@/hooks/useData";
import { formatCurrency, formatDate } from "@/lib/utils";
import {
  FileText,
  ChevronLeft,
  ChevronRight,
  Filter,
  Search,
} from "lucide-react";

const PAGE_SIZE = 15;

const statusOptions = [
  { value: "", label: "Alla" },
  { value: "draft", label: "Utkast" },
  { value: "posted", label: "Bokförda" },
];

export default function VouchersPage() {
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");

  const { data, isLoading } = useVouchers(
    status || undefined,
    PAGE_SIZE,
    page * PAGE_SIZE
  );

  const vouchers = data?.vouchers || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  const filtered = search
    ? vouchers.filter(
        (v: any) =>
          v.description?.toLowerCase().includes(search.toLowerCase()) ||
          String(v.number).includes(search)
      )
    : vouchers;

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1400px] mx-auto">
      <div>
        <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">
          Verifikationer
        </h1>
        <p className="text-muted-foreground mt-1">
          Hantera och granska verifikationer
        </p>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                placeholder="Sök verifikationer..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-9 pr-4 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              {statusOptions.map((opt) => (
                <Button
                  key={opt.value}
                  variant={status === opt.value ? "default" : "outline"}
                  size="sm"
                  onClick={() => {
                    setStatus(opt.value);
                    setPage(0);
                  }}
                >
                  {opt.label}
                </Button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[...Array(8)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : filtered.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left p-4 font-medium text-muted-foreground">
                      Nummer
                    </th>
                    <th className="text-left p-4 font-medium text-muted-foreground">
                      Datum
                    </th>
                    <th className="text-left p-4 font-medium text-muted-foreground">
                      Beskrivning
                    </th>
                    <th className="text-left p-4 font-medium text-muted-foreground">
                      Rader
                    </th>
                    <th className="text-left p-4 font-medium text-muted-foreground">
                      Status
                    </th>
                    <th className="text-right p-4 font-medium text-muted-foreground">
                      Belopp
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((v: any) => {
                    const totalDebit = v.rows?.reduce(
                      (s: number, r: any) => s + (r.debit || 0),
                      0
                    );
                    return (
                      <tr
                        key={v.id}
                        className="border-b last:border-0 hover:bg-muted/30 transition-colors"
                      >
                        <td className="p-4">
                          <Link
                            href={`/vouchers/${v.id}`}
                            className="font-medium text-primary hover:underline flex items-center gap-2"
                          >
                            <FileText className="h-4 w-4" />
                            {v.series || "A"}
                            {v.number}
                          </Link>
                        </td>
                        <td className="p-4 text-muted-foreground">
                          {formatDate(v.date)}
                        </td>
                        <td className="p-4 max-w-[300px] truncate">
                          {v.description}
                          {v.created_by === "ai" && (
                            <Badge variant="secondary" className="ml-2 text-xs">
                              AI
                            </Badge>
                          )}
                        </td>
                        <td className="p-4 text-muted-foreground">
                          {v.rows?.length || 0}
                        </td>
                        <td className="p-4">
                          <Badge
                            variant={
                              v.status === "posted"
                                ? "success"
                                : v.status === "draft"
                                ? "warning"
                                : "secondary"
                            }
                          >
                            {v.status === "draft"
                              ? "Utkast"
                              : v.status === "posted"
                              ? "Bokförd"
                              : v.status}
                          </Badge>
                        </td>
                        <td className="p-4 text-right font-mono">
                          {formatCurrency(totalDebit || 0)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-12 text-center text-muted-foreground">
              <FileText className="h-12 w-12 mx-auto mb-4 opacity-30" />
              <p>Inga verifikationer hittades</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Visar {page * PAGE_SIZE + 1}-
            {Math.min((page + 1) * PAGE_SIZE, total)} av {total}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm px-2">
              {page + 1} / {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
