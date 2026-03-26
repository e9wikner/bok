"use client";

import { useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnomalySummary, useAnomalies } from "@/hooks/useData";
import {
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCircle2,
  FileText,
  Calendar,
  Hash,
  RefreshCw,
  Filter,
  ChevronDown,
  ChevronRight,
  BarChart3,
} from "lucide-react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";

// ---- Types ----
type Severity = "all" | "critical" | "warning" | "info";

const ANOMALY_TYPE_LABELS: Record<string, string> = {
  unusual_amount: "Ovanligt belopp",
  duplicate_entry: "Dubblettbokning",
  missing_attachment: "Saknar bilaga",
  wrong_vat_code: "Felaktig momskod",
  weekend_transaction: "Helgtransaktion",
  missing_counter_entry: "Saknar motkonto",
  frequent_small_transactions: "Många små transaktioner",
  unusual_balance_change: "Ovanlig saldoförändring",
  abnormal_voucher_count: "Onormalt antal verifikationer",
};

const ANOMALY_TYPE_DESCRIPTIONS: Record<string, string> = {
  unusual_amount:
    "Transaktionens belopp avviker statistiskt (Z-score) från kontots normala nivå. Kan indikera inmatningsfel eller ovanlig händelse.",
  duplicate_entry:
    "En verifikation med samma belopp, datum och konton har bokförts mer än en gång. Kontrollera om det är en dubblettbokning.",
  missing_attachment:
    "Verifikationen saknar underlag (kvitto/faktura). Enligt Bokföringslagen (BFL) krävs verifikationsunderlag för alla bokföringsposter.",
  wrong_vat_code:
    "Momskoden på kontot stämmer inte överens med förväntad kod. Kan leda till felaktig momsdeklaration.",
  weekend_transaction:
    "Transaktionen är daterad på en lördag eller söndag. Vanligtvis ett datumfel – kontrollera och rätta om nödvändigt.",
  missing_counter_entry:
    "Verifikationen saknar balanserade debet/kreditposter. Alla verifikationer måste balansera enligt dubbel bokföring.",
  frequent_small_transactions:
    "Ovanligt många små transaktioner från samma motpart. Kan indikera splittring av transaktioner.",
  unusual_balance_change:
    "Kontots saldo har förändrats dramatiskt jämfört med tidigare perioder.",
  abnormal_voucher_count:
    "Antalet verifikationer i perioden avviker markant från det normala.",
};

const SEVERITY_LABELS: Record<Severity, string> = {
  all: "Alla",
  critical: "Kritiska",
  warning: "Varningar",
  info: "Information",
};

// ---- Helper components ----

function SeverityBadge({ severity }: { severity: string }) {
  if (severity === "critical") {
    return (
      <Badge className="gap-1 bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400 border-red-200 dark:border-red-800">
        <AlertCircle className="h-3 w-3" />
        Kritisk
      </Badge>
    );
  }
  if (severity === "warning") {
    return (
      <Badge className="gap-1 bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 border-amber-200 dark:border-amber-800">
        <AlertTriangle className="h-3 w-3" />
        Varning
      </Badge>
    );
  }
  return (
    <Badge className="gap-1 bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400 border-blue-200 dark:border-blue-800">
      <Info className="h-3 w-3" />
      Info
    </Badge>
  );
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 80
      ? "bg-red-500"
      : pct >= 50
      ? "bg-amber-400"
      : "bg-blue-400";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-muted-foreground font-mono w-8 text-right">{pct}%</span>
    </div>
  );
}

function AnomalyRow({ anomaly }: { anomaly: any }) {
  const [open, setOpen] = useState(false);
  const typeLabel = ANOMALY_TYPE_LABELS[anomaly.type] ?? anomaly.type;
  const typeDescription = ANOMALY_TYPE_DESCRIPTIONS[anomaly.type] ?? "";

  return (
    <div className="border-b last:border-0">
      <button
        className="w-full text-left px-4 py-3 hover:bg-muted/40 transition-colors flex items-start gap-3"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="mt-0.5 text-muted-foreground">
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <SeverityBadge severity={anomaly.severity} />
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
              {typeLabel}
            </span>
          </div>
          <p className="text-sm font-medium">{anomaly.title}</p>
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{anomaly.description}</p>
        </div>
        <div className="w-28 flex-shrink-0 hidden sm:block">
          <ScoreBar score={anomaly.score} />
        </div>
      </button>

      {open && (
        <div className="px-11 pb-4 space-y-3">
          {/* What this means */}
          {typeDescription && (
            <div className="bg-muted/40 rounded-lg p-3 text-sm text-muted-foreground">
              <p className="font-medium text-foreground mb-1">Vad betyder detta?</p>
              <p>{typeDescription}</p>
            </div>
          )}

          {/* Details grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
            {anomaly.entity_type === "voucher" && anomaly.entity_id && (
              <div>
                <p className="text-xs text-muted-foreground mb-0.5 flex items-center gap-1">
                  <FileText className="h-3 w-3" /> Verifikation
                </p>
                <Link
                  href={`/vouchers/${anomaly.entity_id}`}
                  className="text-primary hover:underline font-medium text-sm"
                  onClick={(e) => e.stopPropagation()}
                >
                  Öppna verifikation →
                </Link>
              </div>
            )}
            {anomaly.details?.account_code && (
              <div>
                <p className="text-xs text-muted-foreground mb-0.5 flex items-center gap-1">
                  <Hash className="h-3 w-3" /> Konto
                </p>
                <span className="font-mono font-medium">{anomaly.details.account_code}</span>
              </div>
            )}
            {anomaly.details?.voucher_date && (
              <div>
                <p className="text-xs text-muted-foreground mb-0.5 flex items-center gap-1">
                  <Calendar className="h-3 w-3" /> Datum
                </p>
                <span>{anomaly.details.voucher_date}</span>
              </div>
            )}
            {anomaly.details?.z_score !== undefined && (
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">Z-score</p>
                <span className="font-mono font-medium">{anomaly.details.z_score.toFixed(2)}</span>
              </div>
            )}
            {anomaly.details?.amount_ore !== undefined && (
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">Belopp</p>
                <span className="font-mono font-medium">
                  {(anomaly.details.amount_ore / 100).toLocaleString("sv-SE", {
                    style: "currency",
                    currency: "SEK",
                  })}
                </span>
              </div>
            )}
            {anomaly.details?.mean_ore !== undefined && (
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">Genomsnitt</p>
                <span className="font-mono text-muted-foreground">
                  {(anomaly.details.mean_ore / 100).toLocaleString("sv-SE", {
                    style: "currency",
                    currency: "SEK",
                  })}
                </span>
              </div>
            )}
            {anomaly.details?.duplicate_of && (
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">Dubblett av</p>
                <Link
                  href={`/vouchers/${anomaly.details.duplicate_of}`}
                  className="text-primary hover:underline font-mono text-xs"
                  onClick={(e) => e.stopPropagation()}
                >
                  {anomaly.details.duplicate_of.slice(0, 8)}…
                </Link>
              </div>
            )}
          </div>

          <p className="text-xs text-muted-foreground">
            Detekterades {new Date(anomaly.detected_at).toLocaleString("sv-SE")}
          </p>
        </div>
      )}
    </div>
  );
}

// ---- Main page ----

export default function AnomaliesPage() {
  const [severity, setSeverity] = useState<Severity>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const queryClient = useQueryClient();

  const { data: summary, isLoading: summaryLoading } = useAnomalySummary();
  const { data: anomaliesData, isLoading: listLoading } = useAnomalies(500);

  const allAnomalies: any[] = anomaliesData?.anomalies ?? [];

  // Filter client-side
  const filtered = allAnomalies.filter((a) => {
    if (severity !== "all" && a.severity !== severity) return false;
    if (typeFilter !== "all" && a.type !== typeFilter) return false;
    return true;
  });

  // Sort: critical first, then by score desc
  const sorted = [...filtered].sort((a, b) => {
    const order = { critical: 0, warning: 1, info: 2 };
    const so = (order[a.severity as keyof typeof order] ?? 3) - (order[b.severity as keyof typeof order] ?? 3);
    if (so !== 0) return so;
    return b.score - a.score;
  });

  // Available types from actual data
  const availableTypes = Array.from(new Set(allAnomalies.map((a) => a.type))).sort();

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["anomalies"] });
    queryClient.invalidateQueries({ queryKey: ["anomaly-summary"] });
  };

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1400px] mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">Anomalier</h1>
          <p className="text-muted-foreground mt-1">
            Automatisk granskning av bokföringen – misstänkta fel och avvikelser
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={handleRefresh} className="gap-2 flex-shrink-0">
          <RefreshCw className="h-4 w-4" />
          <span className="hidden sm:inline">Kör om analys</span>
        </Button>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <SummaryCard
          label="Totalt"
          value={summary?.total_anomalies ?? 0}
          icon={BarChart3}
          color="slate"
          loading={summaryLoading}
          onClick={() => { setSeverity("all"); setTypeFilter("all"); }}
          active={severity === "all" && typeFilter === "all"}
        />
        <SummaryCard
          label="Kritiska"
          value={summary?.critical_count ?? 0}
          icon={AlertCircle}
          color="red"
          loading={summaryLoading}
          onClick={() => { setSeverity("critical"); setTypeFilter("all"); }}
          active={severity === "critical"}
        />
        <SummaryCard
          label="Varningar"
          value={summary?.warning_count ?? 0}
          icon={AlertTriangle}
          color="amber"
          loading={summaryLoading}
          onClick={() => { setSeverity("warning"); setTypeFilter("all"); }}
          active={severity === "warning"}
        />
        <SummaryCard
          label="Information"
          value={summary?.info_count ?? 0}
          icon={Info}
          color="blue"
          loading={summaryLoading}
          onClick={() => { setSeverity("info"); setTypeFilter("all"); }}
          active={severity === "info"}
        />
      </div>

      {/* By-type breakdown */}
      {summary?.by_type && Object.keys(summary.by_type).length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Filter className="h-4 w-4" />
              Fördelning per typ
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setTypeFilter("all")}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors border ${
                  typeFilter === "all"
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-background hover:bg-muted border-border text-muted-foreground"
                }`}
              >
                Alla typer
              </button>
              {Object.entries(summary.by_type)
                .sort(([, a], [, b]) => (b as number) - (a as number))
                .map(([type, count]) => (
                  <button
                    key={type}
                    onClick={() => setTypeFilter(type === typeFilter ? "all" : type)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors border flex items-center gap-1.5 ${
                      typeFilter === type
                        ? "bg-primary text-primary-foreground border-primary"
                        : "bg-background hover:bg-muted border-border text-muted-foreground"
                    }`}
                  >
                    {ANOMALY_TYPE_LABELS[type] ?? type}
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded-full font-mono ${
                        typeFilter === type
                          ? "bg-primary-foreground/20 text-primary-foreground"
                          : "bg-muted text-foreground"
                      }`}
                    >
                      {count as number}
                    </span>
                  </button>
                ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Explainer */}
      <Card className="border-blue-200 dark:border-blue-900 bg-blue-50/50 dark:bg-blue-950/10">
        <CardContent className="p-4">
          <div className="flex gap-3">
            <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-blue-800 dark:text-blue-300 space-y-1">
              <p className="font-semibold">Vad är en anomali?</p>
              <p>
                En anomali är en automatiskt detekterad avvikelse i bokföringen – något som ser
                ovanligt ut jämfört med normala mönster eller bryter mot bokföringsregler. Det är{" "}
                <strong>inte nödvändigtvis ett fel</strong>, men varje anomali bör granskas och
                bedömas.
              </p>
              <p className="text-xs opacity-80 mt-1">
                Klicka på en rad för att expandera och se detaljer, samt länk till berörda verifikationer.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Anomaly list */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-amber-500" />
                {severity === "all" && typeFilter === "all"
                  ? "Alla anomalier"
                  : `Filtrerat: ${sorted.length} anomalier`}
              </CardTitle>
              <CardDescription>
                {sorted.length === 0
                  ? "Inga anomalier matchar filtret"
                  : `Visar ${sorted.length} av ${allAnomalies.length} • klicka på en rad för detaljer`}
              </CardDescription>
            </div>
            {(severity !== "all" || typeFilter !== "all") && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => { setSeverity("all"); setTypeFilter("all"); }}
                className="text-xs"
              >
                Rensa filter
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {listLoading ? (
            <div className="p-4 space-y-3">
              {[...Array(6)].map((_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : sorted.length === 0 ? (
            <div className="py-16 text-center text-muted-foreground">
              <CheckCircle2 className="h-12 w-12 mx-auto mb-4 opacity-30 text-emerald-500" />
              <p className="font-medium">Inga anomalier hittade</p>
              <p className="text-sm mt-1">
                {severity !== "all" || typeFilter !== "all"
                  ? "Prova att ta bort filtret"
                  : "Bokföringen ser korrekt ut!"}
              </p>
            </div>
          ) : (
            <div className="divide-y-0">
              {sorted.map((anomaly) => (
                <AnomalyRow key={anomaly.id} anomaly={anomaly} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  icon: Icon,
  color,
  loading,
  onClick,
  active,
}: {
  label: string;
  value: number;
  icon: any;
  color: string;
  loading: boolean;
  onClick: () => void;
  active: boolean;
}) {
  const colorMap: Record<string, string> = {
    slate: "bg-slate-100 text-slate-600 dark:bg-slate-900/30 dark:text-slate-400",
    red: "bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400",
    amber: "bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400",
    blue: "bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400",
  };

  return (
    <button onClick={onClick} className="text-left w-full">
      <Card
        className={`transition-all hover:shadow-md cursor-pointer ${
          active ? "ring-2 ring-primary" : ""
        }`}
      >
        <CardContent className="p-4">
          <div className={`h-9 w-9 rounded-lg flex items-center justify-center mb-3 ${colorMap[color]}`}>
            <Icon className="h-4 w-4" />
          </div>
          {loading ? (
            <Skeleton className="h-7 w-12 mb-1" />
          ) : (
            <p className="text-2xl font-bold">{value}</p>
          )}
          <p className="text-xs text-muted-foreground">{label}</p>
        </CardContent>
      </Card>
    </button>
  );
}
