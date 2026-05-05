"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAccountingPatternEvaluations,
  useAccountingPatterns,
  useLearningRules,
  useLearningStats,
} from "@/hooks/useData";
import { api } from "@/lib/api";
import { Brain, Sparkles, Target, Star, Tag, Hash, Type, DollarSign, PlayCircle, CheckCircle2, XCircle, GitCompare } from "lucide-react";

const PATTERN_ICONS: Record<string, any> = {
  keyword: Tag,
  regex: Hash,
  counterparty: Type,
  amount: DollarSign,
};

export default function LearningPage() {
  const queryClient = useQueryClient();
  const { data: rulesData, isLoading: rulesLoading } = useLearningRules();
  const { data: statsData } = useLearningStats();
  const { data: suggestedData, isLoading: suggestedLoading } = useAccountingPatterns("suggested", true);
  const { data: activePatternsData } = useAccountingPatterns("active", false);
  const { data: evaluationsData } = useAccountingPatternEvaluations();
  const [working, setWorking] = useState<"analyze" | "evaluate" | string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const rules = rulesData?.rules || [];
  const goldenRules = rules.filter((r: any) => r.is_golden);
  const activeRules = rules.filter((r: any) => !r.is_golden);
  const suggestedPatterns = suggestedData?.patterns || [];
  const activePatterns = activePatternsData?.patterns || [];
  const latestEvaluation = evaluationsData?.evaluations?.[0];

  const refreshPatterns = async () => {
    await queryClient.invalidateQueries({ queryKey: ["accounting-patterns"] });
    await queryClient.invalidateQueries({ queryKey: ["accounting-pattern-evaluations"] });
  };

  const analyze = async () => {
    setWorking("analyze");
    setMessage(null);
    try {
      const result = await api.analyzeAccountingPatterns({ min_examples: 2 });
      await refreshPatterns();
      setMessage(`${result.suggested_created_or_updated} regelförslag skapade eller uppdaterade från ${result.vouchers_analyzed} verifikationer.`);
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || err?.message || "Analysen misslyckades.");
    } finally {
      setWorking(null);
    }
  };

  const evaluate = async () => {
    setWorking("evaluate");
    setMessage(null);
    try {
      const result = await api.createAccountingPatternEvaluation({
        name: "Backtest aktiva + föreslagna regler",
        include_all_suggested: true,
      });
      await refreshPatterns();
      setMessage(`Backtest klart: kandidatens snittscore ${Math.round((result.summary?.candidate?.average_score || 0) * 100)}%.`);
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || err?.message || "Backtest misslyckades.");
    } finally {
      setWorking(null);
    }
  };

  const approve = async (id: string) => {
    setWorking(id);
    try {
      await api.approveAccountingPattern(id);
      await refreshPatterns();
    } finally {
      setWorking(null);
    }
  };

  const reject = async (id: string) => {
    setWorking(id);
    try {
      await api.rejectAccountingPattern(id);
      await refreshPatterns();
    } finally {
      setWorking(null);
    }
  };

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1400px] mx-auto">
      <div>
        <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">AI-lärande</h1>
        <p className="text-muted-foreground mt-1">
          Inlärda regler, bokföringsmönster och backtest innan regler aktiveras
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Inlärda regler" value={rules.length} icon={Brain} color="violet" />
        <StatCard title="Aktiva mönster" value={activePatterns.length} icon={CheckCircle2} color="emerald" />
        <StatCard title="Föreslagna mönster" value={suggestedPatterns.length} icon={Sparkles} color="blue" />
        <StatCard title="Korrigeringar" value={statsData?.total_corrections || 0} icon={Target} color="amber" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <GitCompare className="h-5 w-5 text-primary" />
            Bokföringsmönster
          </CardTitle>
          <CardDescription>
            Skapa föreslagna regler från historiska verifikationer och jämför dem mot aktiva regler innan godkännande.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button onClick={analyze} disabled={!!working} className="gap-2">
              <PlayCircle className="h-4 w-4" />
              {working === "analyze" ? "Analyserar..." : "Analysera befintliga verifikationer"}
            </Button>
            <Button onClick={evaluate} disabled={!!working} variant="outline" className="gap-2">
              <GitCompare className="h-4 w-4" />
              {working === "evaluate" ? "Jämför..." : "Jämför aktiva + föreslagna mot historik"}
            </Button>
          </div>
          {message && <p className="text-sm text-muted-foreground">{message}</p>}
          {latestEvaluation && <EvaluationSummary evaluation={latestEvaluation} />}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            Föreslagna bokföringsmönster
          </CardTitle>
          <CardDescription>Regler som kan testas av agenten men inte används för faktisk bokföring förrän de godkänns.</CardDescription>
        </CardHeader>
        <CardContent>
          {suggestedLoading ? (
            <div className="space-y-3">
              {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}
            </div>
          ) : suggestedPatterns.length > 0 ? (
            <div className="grid gap-3">
              {suggestedPatterns.map((pattern: any) => (
                <AccountingPatternCard
                  key={pattern.id}
                  pattern={pattern}
                  working={working === pattern.id}
                  onApprove={() => approve(pattern.id)}
                  onReject={() => reject(pattern.id)}
                />
              ))}
            </div>
          ) : (
            <EmptyState text="Inga föreslagna bokföringsmönster ännu. Kör analysen för att skapa förslag." />
          )}
        </CardContent>
      </Card>

      {goldenRules.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Star className="h-5 w-5 text-amber-500" />
              Gyllene regler
            </CardTitle>
            <CardDescription>Bekräftade regler med hög tillförlitlighet</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3">
              {goldenRules.map((rule: any) => <RuleCard key={rule.id} rule={rule} golden />)}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-primary" />
            Inlärda korrigeringsregler
          </CardTitle>
          <CardDescription>Regler genererade från användarkorrigeringar</CardDescription>
        </CardHeader>
        <CardContent>
          {rulesLoading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}
            </div>
          ) : activeRules.length > 0 ? (
            <div className="grid gap-3">
              {activeRules.map((rule: any) => <RuleCard key={rule.id} rule={rule} />)}
            </div>
          ) : (
            <EmptyState text="Inga inlärda korrigeringsregler ännu." />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function AccountingPatternCard({
  pattern,
  working,
  onApprove,
  onReject,
}: {
  pattern: any;
  working: boolean;
  onApprove: () => void;
  onReject: () => void;
}) {
  const confidence = Math.round((pattern.confidence || 0) * 100);
  const rows = pattern.voucher_template?.rows || [];
  const examples = pattern.examples || [];

  return (
    <div className="rounded-lg border p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold">{pattern.name}</h3>
            <Badge variant="outline">{pattern.status}</Badge>
            <Badge variant="secondary">{confidence}%</Badge>
            <span className="text-sm text-muted-foreground">{pattern.sample_count} exempel</span>
          </div>
          <p className="text-sm text-muted-foreground">
            Matchar: {(pattern.match_config?.description_contains || []).join(", ") || "-"}
          </p>
          <div className="flex flex-wrap gap-2 text-xs">
            {rows.map((row: any, index: number) => (
              <span key={`${row.account}-${index}`} className="rounded-md border px-2 py-1 font-mono">
                {row.account} {row.side === "debit" ? "debet" : "kredit"} {Math.round((row.ratio || 0) * 100)}%
              </span>
            ))}
          </div>
          {examples.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Exempel: {examples.slice(0, 3).map((ex: any) => `${ex.voucher.series}${ex.voucher.number} ${ex.voucher.description}`).join(" · ")}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={onApprove} disabled={working} className="gap-1">
            <CheckCircle2 className="h-4 w-4" />
            Godkänn
          </Button>
          <Button size="sm" variant="outline" onClick={onReject} disabled={working} className="gap-1">
            <XCircle className="h-4 w-4" />
            Avvisa
          </Button>
        </div>
      </div>
    </div>
  );
}

function EvaluationSummary({ evaluation }: { evaluation: any }) {
  const summary = evaluation.summary || {};
  return (
    <div className="space-y-3 rounded-lg border bg-muted/20 p-4">
      <div className="grid gap-3 md:grid-cols-4">
        <Metric
          label="Testfall"
          value={summary.cases_total || 0}
          description="Historiska bokförda verifikationer som backtesten försökte återskapa."
        />
        <Metric
          label="Baseline snitt"
          value={`${Math.round((summary.baseline?.average_score || 0) * 100)}%`}
          description="Träffsäkerhet med endast redan godkända aktiva bokföringsmönster."
        />
        <Metric
          label="Candidate snitt"
          value={`${Math.round((summary.candidate?.average_score || 0) * 100)}%`}
          description="Träffsäkerhet med aktiva mönster plus föreslagna mönster."
        />
        <Metric
          label="Förbättringar/regressioner"
          value={`${summary.improvements || 0}/${summary.regressions || 0}`}
          description="Antal testfall där Candidate blev bättre respektive sämre än Baseline."
        />
      </div>
      <p className="text-xs text-muted-foreground">
        Föreslagna regler används bara i backtestet. De påverkar inte faktisk bokföring förrän de godkänns.
      </p>
    </div>
  );
}

function Metric({ label, value, description }: { label: string; value: string | number; description: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold">{value}</p>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="py-12 text-center text-muted-foreground">
      <Brain className="h-12 w-12 mx-auto mb-4 opacity-30" />
      <p>{text}</p>
    </div>
  );
}

function RuleCard({ rule, golden }: { rule: any; golden?: boolean }) {
  const Icon = PATTERN_ICONS[rule.pattern_type] || Tag;
  const confidence = Math.round((rule.confidence || 0) * 100);

  return (
    <div className={`p-4 rounded-lg border ${golden ? "border-amber-200 bg-amber-50/50 dark:border-amber-900 dark:bg-amber-950/20" : "hover:bg-muted/30"} transition-colors`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
            <Icon className="h-4 w-4 text-primary" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium">{rule.pattern_value}</span>
              <Badge variant="outline" className="text-xs">{rule.pattern_type}</Badge>
              {golden && <Badge variant="warning" className="text-xs gap-1"><Star className="h-3 w-3" /> Gyllene</Badge>}
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              Konto: <span className="font-mono">{rule.corrected_account}</span>
            </p>
          </div>
        </div>
        <div className="text-right flex-shrink-0">
          <div className="flex items-center gap-1">
            <div className="h-2 w-16 bg-muted rounded-full overflow-hidden">
              <div className="h-full rounded-full bg-primary" style={{ width: `${confidence}%` }} />
            </div>
            <span className="text-xs text-muted-foreground w-8">{confidence}%</span>
          </div>
          <p className="text-xs text-muted-foreground mt-1">{rule.usage_count} användningar</p>
        </div>
      </div>
    </div>
  );
}

function StatCard({ title, value, icon: Icon, color }: { title: string; value: number; icon: any; color: string }) {
  const colorMap: Record<string, string> = {
    violet: "bg-violet-100 text-violet-600 dark:bg-violet-900/30 dark:text-violet-400",
    amber: "bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400",
    blue: "bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400",
    emerald: "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400",
  };

  return (
    <Card>
      <CardContent className="p-4">
        <div className={`h-10 w-10 rounded-lg flex items-center justify-center ${colorMap[color]} mb-3`}>
          <Icon className="h-5 w-5" />
        </div>
        <p className="text-2xl font-bold">{value}</p>
        <p className="text-sm text-muted-foreground">{title}</p>
      </CardContent>
    </Card>
  );
}
