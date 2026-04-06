"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useVouchers, useFiscalYears } from "@/hooks/useData";
import { formatCurrency, formatDate } from "@/lib/utils";
import {
  FileText,
  ChevronLeft,
  ChevronRight,
  Filter,
  Search,
  Plus,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
} from "lucide-react";

const PAGE_SIZE = 15;

const statusOptions = [
  { value: "", label: "Alla" },
  { value: "draft", label: "Utkast" },
  { value: "posted", label: "Bokförda" },
];

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debouncedValue;
}

export default function VouchersPage() {
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [fiscalYearId, setFiscalYearId] = useState<string | undefined>(undefined);
  const debouncedSearch = useDebounce(search, 300);

  const { data: fiscalYearsData } = useFiscalYears();
  const fiscalYears = fiscalYearsData?.fiscal_years || [];

  // Reset to page 0 when search term changes
  const prevSearch = useRef(debouncedSearch);
  useEffect(() => {
    if (prevSearch.current !== debouncedSearch) {
      setPage(0);
      prevSearch.current = debouncedSearch;
    }
  }, [debouncedSearch]);

  const { data, isLoading } = useVouchers(
    status || undefined,
    PAGE_SIZE,
    page * PAGE_SIZE,
    debouncedSearch || undefined,
    sortBy,
    sortOrder,
    fiscalYearId
  );

  function toggleSort(column: string) {
    if (sortBy === column) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortOrder("desc");
    }
    setPage(0);
  }

  function SortIcon({ column }: { column: string }) {
    if (sortBy !== column) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-40" />;
    return sortOrder === "asc" ? (
      <ArrowUp className="h-3 w-3 ml-1" />
    ) : (
      <ArrowDown className="h-3 w-3 ml-1" />
    );
  }

  const vouchers = data?.vouchers || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1400px] mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">
            Verifikationer
          </h1>
          <p className="text-muted-foreground mt-1">
            Hantera och granska verifikationer
          </p>
        </div>
        <Link href="/vouchers/new">
          <Button>
            <Plus className="h-4 w-4 mr-2" />
            Ny verifikation
          </Button>
        </Link>
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
              <select
                value={fiscalYearId || ""}
                onChange={(e) => {
                  setFiscalYearId(e.target.value || undefined);
                  setPage(0);
                }}
                className="h-9 rounded-md border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">Alla år</option>
                {fiscalYears.map((fy: any) => (
                  <option key={fy.id} value={fy.id}>
                    {fy.start_date.slice(0, 4)}
                  </option>
                ))}
              </select>
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
          ) : vouchers.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th
                      className="text-left p-4 font-medium text-muted-foreground cursor-pointer select-none hover:text-foreground transition-colors"
                      onClick={() => toggleSort("number")}
                    >
                      <span className="inline-flex items-center">
                        Nummer
                        <SortIcon column="number" />
                      </span>
                    </th>
                    <th
                      className="text-left p-4 font-medium text-muted-foreground cursor-pointer select-none hover:text-foreground transition-colors"
                      onClick={() => toggleSort("date")}
                    >
                      <span className="inline-flex items-center">
                        Datum
                        <SortIcon column="date" />
                      </span>
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
                  {vouchers.map((v: any) => {
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
