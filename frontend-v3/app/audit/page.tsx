"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAuditLog } from "@/hooks/useData";
import { formatCurrency } from "@/lib/utils";
import { ScrollText, User, Clock, Package, FileText, RefreshCw } from "lucide-react";

const ENTITY_COLORS: Record<string, string> = {
  voucher: "bg-blue-100 text-blue-800",
  opening_balance: "bg-purple-100 text-purple-800",
  fiscal_year: "bg-green-100 text-green-800",
  account: "bg-yellow-100 text-yellow-800",
  invoice: "bg-orange-100 text-orange-800",
};

const ACTION_COLORS: Record<string, string> = {
  created: "bg-emerald-100 text-emerald-800",
  updated: "bg-amber-100 text-amber-800",
  posted: "bg-blue-100 text-blue-800",
  deleted: "bg-red-100 text-red-800",
  locked: "bg-gray-100 text-gray-800",
};

export default function AuditLogPage() {
  const [filter, setFilter] = useState<string>("");
  const { data, isLoading } = useAuditLog(100);

  if (isLoading) {
    return (
      <div className="container mx-auto py-8 px-4">
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

  // Filter entries
  const filteredEntries = entries.filter((entry: any) => {
    if (!filter) return true;
    const search = filter.toLowerCase();
    return (
      entry.entity_type?.toLowerCase().includes(search) ||
      entry.action?.toLowerCase().includes(search) ||
      entry.actor?.toLowerCase().includes(search) ||
      entry.entity_id?.toLowerCase().includes(search)
    );
  });

  const formatPayload = (payload: any) => {
    if (!payload) return null;
    
    const items = [];
    
    if (payload.series && payload.number !== undefined) {
      items.push(`${payload.series}${payload.number}`);
    }
    if (payload.year) {
      items.push(`År: ${payload.year}`);
    }
    if (payload.accounts_count !== undefined) {
      items.push(`Konton: ${payload.accounts_count}`);
    }
    if (payload.rows_count !== undefined) {
      items.push(`Rader: ${payload.rows_count}`);
    }
    if (payload.fiscal_year_id) {
      items.push(`Räkenskapsår: ${payload.fiscal_year_id.slice(0, 8)}...`);
    }
    if (payload.total_debit !== undefined) {
      items.push(`Debet: ${formatCurrency(payload.total_debit)}`);
    }
    if (payload.total_credit !== undefined) {
      items.push(`Kredit: ${formatCurrency(payload.total_credit)}`);
    }
    
    return items.length > 0 ? items.join(" • ") : JSON.stringify(payload).slice(0, 100);
  };

  const getEntityIcon = (entityType: string) => {
    switch (entityType) {
      case "voucher":
        return <FileText className="h-4 w-4" />;
      case "opening_balance":
        return <Package className="h-4 w-4" />;
      default:
        return <ScrollText className="h-4 w-4" />;
    }
  };

  return (
    <div className="container mx-auto py-8 px-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-2xl">
                <ScrollText className="h-6 w-6 text-primary" />
                Logg
              </CardTitle>
              <CardDescription>
                Händelselogg för systemet • {entries.length} poster
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Sök i loggen..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {filteredEntries.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                <ScrollText className="h-12 w-12 mx-auto mb-4 opacity-30" />
                <p>Inga loggposter hittades</p>
              </div>
            ) : (
              filteredEntries.map((entry: any) => (
                <div
                  key={entry.id}
                  className="flex items-start gap-4 p-4 rounded-lg border hover:bg-muted/30 transition-colors"
                >
                  <div className="mt-1">
                    {getEntityIcon(entry.entity_type)}
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge className={ENTITY_COLORS[entry.entity_type] || "bg-gray-100"}>
                        {entry.entity_type}
                      </Badge>
                      <Badge className={ACTION_COLORS[entry.action] || "bg-gray-100"}>
                        {entry.action}
                      </Badge>
                      <span className="text-xs text-muted-foreground font-mono">
                        {entry.entity_id.slice(0, 12)}...
                      </span>
                    </div>
                    
                    {entry.payload && (
                      <p className="mt-2 text-sm text-muted-foreground">
                        {formatPayload(entry.payload)}
                      </p>
                    )}
                  </div>
                  
                  <div className="text-right text-xs text-muted-foreground space-y-1">
                    <div className="flex items-center gap-1">
                      <User className="h-3 w-3" />
                      {entry.actor}
                    </div>
                    <div className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {new Date(entry.timestamp).toLocaleString("sv-SE", {
                        year: "numeric",
                        month: "2-digit",
                        day: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
