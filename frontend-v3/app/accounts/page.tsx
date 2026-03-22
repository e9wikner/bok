"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAccounts } from "@/hooks/useData";
import { formatCurrency } from "@/lib/utils";
import { BookOpen, Search, ChevronDown, ChevronRight } from "lucide-react";

const TYPE_LABELS: Record<string, string> = {
  asset: "Tillgångar",
  liability: "Skulder",
  equity: "Eget kapital",
  revenue: "Intäkter",
  expense: "Kostnader",
};

const TYPE_COLORS: Record<string, string> = {
  asset: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  liability: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  equity: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  revenue: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  expense: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
};

export default function AccountsPage() {
  const { data, isLoading } = useAccounts();
  const [search, setSearch] = useState("");
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(
    new Set(["asset", "liability", "equity", "revenue", "expense"])
  );

  const accounts = data?.accounts || data || [];

  const filtered = search
    ? accounts.filter(
        (a: any) =>
          a.name?.toLowerCase().includes(search.toLowerCase()) ||
          a.code?.includes(search)
      )
    : accounts;

  const grouped = filtered.reduce((acc: any, a: any) => {
    const type = a.account_type || "other";
    if (!acc[type]) acc[type] = [];
    acc[type].push(a);
    return acc;
  }, {});

  const toggleType = (type: string) => {
    setExpandedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1400px] mx-auto">
      <div>
        <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">
          Kontoplan
        </h1>
        <p className="text-muted-foreground mt-1">
          BAS 2026 kontoplan med {accounts.length} konton
        </p>
      </div>

      {/* Search */}
      <Card>
        <CardContent className="p-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Sök konto (nummer eller namn)..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
        </CardContent>
      </Card>

      {/* Grouped accounts */}
      {isLoading ? (
        <div className="space-y-4">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          {Object.entries(grouped).map(([type, accs]: [string, any]) => (
            <Card key={type}>
              <button
                onClick={() => toggleType(type)}
                className="w-full flex items-center justify-between p-4 lg:p-6 hover:bg-muted/30 transition-colors rounded-t-xl"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`px-3 py-1 rounded-lg text-sm font-medium ${
                      TYPE_COLORS[type] || "bg-gray-100 text-gray-700"
                    }`}
                  >
                    {TYPE_LABELS[type] || type}
                  </div>
                  <span className="text-sm text-muted-foreground">
                    {accs.length} konton
                  </span>
                </div>
                {expandedTypes.has(type) ? (
                  <ChevronDown className="h-5 w-5 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-5 w-5 text-muted-foreground" />
                )}
              </button>
              {expandedTypes.has(type) && (
                <CardContent className="pt-0">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left pb-2 font-medium text-muted-foreground">
                            Kod
                          </th>
                          <th className="text-left pb-2 font-medium text-muted-foreground">
                            Kontonamn
                          </th>
                          <th className="text-right pb-2 font-medium text-muted-foreground">
                            Saldo
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {accs.map((a: any) => (
                          <tr
                            key={a.code}
                            className="border-b last:border-0 hover:bg-muted/30 transition-colors"
                          >
                            <td className="py-2.5 font-mono font-medium text-primary">
                              {a.code}
                            </td>
                            <td className="py-2.5">{a.name}</td>
                            <td className="py-2.5 text-right font-mono">
                              {a.balance != null
                                ? formatCurrency(a.balance)
                                : "-"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
