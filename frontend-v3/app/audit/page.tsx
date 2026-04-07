"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAuditLog } from "@/hooks/useData";
import { formatCurrency } from "@/lib/utils";
import { ScrollText, RefreshCw, Search } from "lucide-react";

const ACTION_SHORT: Record<string, string> = {
  created: "NY",
  updated: "UPD",
  posted: "BOK",
  deleted: "DEL",
  locked: "LÅS",
};

const ACTION_COLORS: Record<string, string> = {
  created: "bg-emerald-50 text-emerald-700 border-emerald-200",
  updated: "bg-amber-50 text-amber-700 border-amber-200",
  posted: "bg-blue-50 text-blue-700 border-blue-200",
  deleted: "bg-red-50 text-red-700 border-red-200",
  locked: "bg-gray-50 text-gray-700 border-gray-200",
};

const ENTITY_SHORT: Record<string, string> = {
  voucher: "VER",
  opening_balance: "IB",
  fiscal_year: "ÅR",
  account: "KONTO",
  invoice: "FAKT",
};

export default function AuditLogPage() {
  const [filter, setFilter] = useState<string>("");
  const { data, isLoading } = useAuditLog(200);

  if (isLoading) {
    return (
      <div className="container mx-auto py-6 px-4 max-w-5xl">
        <Card>
          <CardContent className="p-8 text-center">
            <RefreshCw className="h-8 w-8 animate-spin mx-auto text-muted-foreground" />
            <p className="mt-4 text-muted-foreground">Laddar logg...</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const entries = data?.entries || [];

  const filteredEntries = entries.filter((entry: any) => {
    if (!filter) return true;
    const search = filter.toLowerCase();
    return (
      entry.entity_type?.toLowerCase().includes(search) ||
      entry.action?.toLowerCase().includes(search) ||
      entry.actor?.toLowerCase().includes(search)
    );
  });

  const formatPayload = (payload: any): string => {
    if (!payload) return "";
    
    const parts: string[] = [];
    
    if (payload.series && payload.number !== undefined) {
      parts.push(`${payload.series}${payload.number}`);
    }
    if (payload.year) {
      parts.push(`${payload.year}`);
    }
    if (payload.accounts_count !== undefined) {
      parts.push(`${payload.accounts_count} konton`);
    }
    if (payload.rows_count !== undefined) {
      parts.push(`${payload.rows_count} rader`);
    }
    if (payload.total_debit !== undefined && payload.total_credit !== undefined) {
      parts.push(formatCurrency(payload.total_debit));
    }
    
    return parts.join(" • ");
  };

  const formatTime = (timestamp: string): string => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 1) return "just nu";
    if (diffMins < 60) return `${diffMins}m`;
    if (diffHours < 24) return `${diffHours}t`;
    if (diffDays < 7) return `${diffDays}d`;
    
    return date.toLocaleDateString("sv-SE", { 
      month: "short", 
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  // Group entries by date
  const groupedEntries = filteredEntries.reduce((groups: any, entry: any) => {
    const date = new Date(entry.timestamp).toLocaleDateString("sv-SE", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
    if (!groups[date]) groups[date] = [];
    groups[date].push(entry);
    return groups;
  }, {});

  return (
    <div className="container mx-auto py-6 px-4 max-w-5xl">
      <Card className="overflow-hidden">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-xl">
                <ScrollText className="h-5 w-5 text-primary" />
                Logg
              </CardTitle>
              <CardDescription className="text-xs">
                {entries.length} händelser
              </CardDescription>
            </div>
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <input
                type="text"
                placeholder="Sök..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="pl-7 pr-3 py-1.5 rounded-md border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-ring w-48"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {filteredEntries.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <ScrollText className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Inga loggposter hittades</p>
            </div>
          ) : (
            <div className="divide-y">
              {Object.entries(groupedEntries).map(([date, dayEntries]: [string, any]) => (
                <div key={date}>
                  <div className="bg-muted/50 px-4 py-1.5 text-xs font-medium text-muted-foreground sticky top-0">
                    {date}
                  </div>
                  <table className="w-full text-sm">
                    <tbody>
                      {dayEntries.map((entry: any) => (
                        <tr 
                          key={entry.id} 
                          className="hover:bg-muted/30 transition-colors border-b last:border-b-0"
                        >
                          <td className="py-1.5 pl-4 pr-2 w-16">
                            <Badge 
                              variant="outline" 
                              className={`text-[10px] px-1 py-0 h-5 font-medium ${ACTION_COLORS[entry.action] || "bg-gray-50 text-gray-700"}`}
                            >
                              {ACTION_SHORT[entry.action] || entry.action.slice(0, 3).toUpperCase()}
                            </Badge>
                          </td>
                          <td className="py-1.5 px-2 w-20">
                            <span className="text-xs font-medium text-muted-foreground">
                              {ENTITY_SHORT[entry.entity_type] || entry.entity_type.slice(0, 4).toUpperCase()}
                            </span>
                          </td>
                          <td className="py-1.5 px-2 w-20">
                            <span className="text-xs font-mono text-muted-foreground">
                              {entry.entity_id.slice(0, 8)}
                            </span>
                          </td>
                          <td className="py-1.5 px-2">
                            <span className="text-xs text-muted-foreground truncate max-w-[200px] inline-block">
                              {formatPayload(entry.payload)}
                            </span>
                          </td>
                          <td className="py-1.5 px-2 text-right">
                            <span className="text-xs text-muted-foreground">
                              {entry.actor}
                            </span>
                          </td>
                          <td className="py-1.5 pl-2 pr-4 text-right w-20">
                            <span className="text-xs text-muted-foreground tabular-nums">
                              {formatTime(entry.timestamp)}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
