"use client";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useLearningRules, useLearningStats } from "@/hooks/useData";
import { formatDate } from "@/lib/utils";
import { Brain, Sparkles, Target, Zap, Star, Tag, Hash, Type, DollarSign } from "lucide-react";

const PATTERN_ICONS: Record<string, any> = {
  keyword: Tag,
  regex: Hash,
  counterparty: Type,
  amount: DollarSign,
};

export default function LearningPage() {
  const { data: rulesData, isLoading: rulesLoading } = useLearningRules();
  const { data: statsData } = useLearningStats();

  const rules = rulesData?.rules || [];
  const goldenRules = rules.filter((r: any) => r.is_golden);
  const activeRules = rules.filter((r: any) => !r.is_golden);

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1400px] mx-auto">
      <div>
        <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">AI-lärande</h1>
        <p className="text-muted-foreground mt-1">
          Regler som AI:n lärt sig från dina korrigeringar
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Totala regler"
          value={rules.length}
          icon={Brain}
          color="violet"
        />
        <StatCard
          title="Gyllene regler"
          value={goldenRules.length}
          icon={Star}
          color="amber"
        />
        <StatCard
          title="Aktiva regler"
          value={activeRules.length}
          icon={Zap}
          color="blue"
        />
        <StatCard
          title="Totala korrigeringar"
          value={statsData?.total_corrections || 0}
          icon={Target}
          color="emerald"
        />
      </div>

      {/* Golden rules */}
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
              {goldenRules.map((rule: any) => (
                <RuleCard key={rule.id} rule={rule} golden />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Active rules */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            Inlärda regler
          </CardTitle>
          <CardDescription>
            Regler genererade från dina korrigeringar
          </CardDescription>
        </CardHeader>
        <CardContent>
          {rulesLoading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          ) : activeRules.length > 0 ? (
            <div className="grid gap-3">
              {activeRules.map((rule: any) => (
                <RuleCard key={rule.id} rule={rule} />
              ))}
            </div>
          ) : (
            <div className="py-12 text-center text-muted-foreground">
              <Brain className="h-12 w-12 mx-auto mb-4 opacity-30" />
              <p>Inga inlärda regler ännu</p>
              <p className="text-sm mt-1">
                Korrigera verifikationer för att AI:n ska börja lära sig
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function RuleCard({ rule, golden }: { rule: any; golden?: boolean }) {
  const Icon = PATTERN_ICONS[rule.pattern_type] || Tag;
  const confidence = Math.round((rule.confidence || 0) * 100);

  return (
    <div
      className={`p-4 rounded-lg border ${
        golden
          ? "border-amber-200 bg-amber-50/50 dark:border-amber-900 dark:bg-amber-950/20"
          : "hover:bg-muted/30"
      } transition-colors`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
            <Icon className="h-4 w-4 text-primary" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium">{rule.pattern_value}</span>
              <Badge variant="outline" className="text-xs">
                {rule.pattern_type}
              </Badge>
              {golden && (
                <Badge variant="warning" className="text-xs gap-1">
                  <Star className="h-3 w-3" /> Gyllene
                </Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              Konto: <span className="font-mono">{rule.corrected_account}</span>
            </p>
          </div>
        </div>
        <div className="text-right flex-shrink-0">
          <div className="flex items-center gap-1">
            <div className="h-2 w-16 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${confidence}%` }}
              />
            </div>
            <span className="text-xs text-muted-foreground w-8">
              {confidence}%
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            {rule.usage_count} användningar
          </p>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string;
  value: number;
  icon: any;
  color: string;
}) {
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
