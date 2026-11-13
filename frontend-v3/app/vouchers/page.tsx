"use client";

import { Fragment, useState, useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useVouchers, useFiscalYears } from "@/hooks/useData";
import { groupByMonth, formatMonthLabel } from "@/lib/voucherMonths";
import { formatCurrency, formatDate, formatFiscalYearLabel, formatVerifikationsnummer } from "@/lib/utils";
import {
  FileText,
  ChevronDown,
  ChevronRight,
  Filter,
  Search,
  Plus,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
} from "lucide-react";

// Listan är grupperad per månad och hämtas hel; månaderna sköter överblicken.
const LOAD_LIMIT = 5000;

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

function getCurrentFiscalYearId(fiscalYears: any[]): string | undefined {
  if (!fiscalYears || fiscalYears.length === 0) return undefined;

  const today = new Date().toISOString().split("T")[0];

  // Find the fiscal year that contains today's date
  const current = fiscalYears.find((fy) => {
    return today >= fy.start_date && today <= fy.end_date;
  });

  if (current) return current.id;

  // Fallback: return the fiscal year with the latest start date
  const sorted = [...fiscalYears].sort(
    (a, b) => new Date(b.start_date).getTime() - new Date(a.start_date).getTime()
  );
  return sorted[0]?.id;
}

export default function VouchersPage() {
  const searchParams = useSearchParams();
  const initialStatus = searchParams.get("status") || "";
  const initialFiscalYearMode = searchParams.get("fiscalYear");
  const [status, setStatus] = useState(initialStatus);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [fiscalYearId, setFiscalYearId] = useState<string | undefined>(undefined);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [hideEmpty, setHideEmpty] = useState(true);
  const debouncedSearch = useDebounce(search, 300);

  const { data: fiscalYearsData } = useFiscalYears();
  const fiscalYears = fiscalYearsData?.fiscal_years || [];
  const hasInitializedFiscalYear = useRef(false);

  // Default to current fiscal year when data loads
  useEffect(() => {
    if (hasInitializedFiscalYear.current) return;
    if (!fiscalYearsData?.fiscal_years || fiscalYearsData.fiscal_years.length === 0) return;

    if (initialFiscalYearMode === "all") {
      hasInitializedFiscalYear.current = true;
      setFiscalYearId(undefined);
      return;
    }

    if (!fiscalYearId) {
      const currentId = getCurrentFiscalYearId(fiscalYearsData.fiscal_years);
      hasInitializedFiscalYear.current = true;
      setFiscalYearId(currentId);
    }
  }, [fiscalYearsData, fiscalYearId, initialFiscalYearMode]);

  const { data, isLoading } = useVouchers(
    status || undefined,
    LOAD_LIMIT,
    0,
    debouncedSearch || undefined,
    sortBy,
    sortOrder,
    fiscalYearId,
    "IB,B" // Exclude opening balance and B-series correction vouchers from regular list
  );

  function toggleSort(column: string) {
    if (sortBy === column) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortOrder("desc");
    }
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
  const selectedYear = fiscalYears.find((fy: any) => fy.id === fiscalYearId);
  // Utan sökning/statusfilter visas årets alla månader; med filter bara träffarna.
  const filtered = !!debouncedSearch || !!status;
  let groups = groupByMonth(
    vouchers,
    selectedYear && !filtered
      ? { start: selectedYear.start_date, end: selectedYear.end_date }
      : undefined,
  );
  if (sortBy === "date" && sortOrder === "asc") groups = [...groups].reverse();
  const emptyCount = groups.filter((g) => g.vouchers.length === 0).length;
  const visibleGroups = hideEmpty ? groups.filter((g) => g.vouchers.length > 0) : groups;
  const allCollapsed =
    visibleGroups.length > 0 && visibleGroups.every((g) => collapsed.has(g.key));

  function toggleMonth(key: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

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
            <div className="flex items-center gap-2 flex-wrap">
              {fiscalYears.map((fy: any) => (
                <Button
                  key={fy.id}
                  variant={fiscalYearId === fy.id ? "default" : "outline"}
                  size="sm"
                  onClick={() => {
                    setFiscalYearId(fy.id);
                                  }}
                >
                  {formatFiscalYearLabel(fy)}
                </Button>
              ))}
              <Button
                variant={fiscalYearId === undefined ? "default" : "outline"}
                size="sm"
                onClick={() => {
                  setFiscalYearId(undefined);
                              }}
              >
                Alla år
              </Button>
              <Filter className="h-4 w-4 text-muted-foreground" />
              {statusOptions.map((opt) => (
                <Button
                  key={opt.value}
                  variant={status === opt.value ? "default" : "outline"}
                  size="sm"
                  onClick={() => {
                    setStatus(opt.value);
                                  }}
                >
                  {opt.label}
                </Button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Månadsverktyg */}
      {!isLoading && groups.length > 0 && (
        <div className="flex items-center justify-between gap-3 flex-wrap text-sm">
          <p className="text-muted-foreground">{total} verifikationer</p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                setCollapsed(allCollapsed ? new Set() : new Set(visibleGroups.map((g) => g.key)))
              }
            >
              {allCollapsed ? "Fäll ut alla" : "Fäll ihop alla"}
            </Button>
            {emptyCount > 0 && (
              <Button variant="outline" size="sm" onClick={() => setHideEmpty((h) => !h)}>
                {hideEmpty ? `Visa tomma månader (${emptyCount})` : "Dölj tomma månader"}
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[...Array(8)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : visibleGroups.length > 0 ? (
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
                  {visibleGroups.map((g) => {
                    const isCollapsed = collapsed.has(g.key);
                    const Chevron = isCollapsed ? ChevronRight : ChevronDown;
                    return (
                  <Fragment key={g.key}>
                  <tr className="border-b bg-muted/30">
                    <td colSpan={6} className="p-0">
                      <button
                        type="button"
                        onClick={() => toggleMonth(g.key)}
                        aria-expanded={!isCollapsed}
                        className="w-full flex items-center gap-2 px-4 py-2 font-medium capitalize hover:bg-muted/50 transition-colors text-left"
                      >
                        <Chevron className="h-4 w-4" />
                        {formatMonthLabel(g.key)}
                        <span className="hidden sm:inline text-xs font-normal text-muted-foreground normal-case">
                          {g.vouchers.length} verifikationer
                        </span>
                      </button>
                    </td>
                  </tr>
                  {!isCollapsed && g.vouchers.map((v: any) => (
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
                            {formatVerifikationsnummer(v.number)}
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
                          {v.row_count || 0}
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
                          {formatCurrency(v.total_debit || 0)}
                        </td>
                      </tr>
                  ))}
                  </Fragment>
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
    </div>
  );
}
