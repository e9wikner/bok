"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useVouchers,
  useAccounts,
  useLearningRules,
  useAnomalySummary,
  useHealth,
} from "@/hooks/useData";
import { formatCurrency, formatDate } from "@/lib/utils";
import {
  FileText,
  BookOpen,
  Brain,
  AlertTriangle,
  TrendingUp,
  Activity,
  ArrowUpRight,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";

const STATUS_COLORS: Record<string, string> = {
  draft: "#f59e0b",
  posted: "#3b82f6",
  booked: "#10b981",
};

export default function DashboardPage() {
  const { data: vouchersData, isLoading: vLoading } = useVouchers();
  const { data: accountsData, isLoading: aLoading } = useAccounts();
  const { data: rulesData, isLoading: rLoading } = useLearningRules();
  const { data: anomalyData } = useAnomalySummary();
  const { data: healthData } = useHealth();

  const totalVouchers = vouchersData?.total || 0;
  const vouchers = vouchersData?.vouchers || [];
  const aiGeneratedCount = vouchers.filter((v: any) => v.ai_generated).length;
  const learningRulesCount = rulesData?.rules?.length || 0;
  const accountCount =
    accountsData?.accounts?.length || accountsData?.length || 0;

  // Status distribution for chart
  const statusCounts = vouchers.reduce((acc: any, v: any) => {
    acc[v.status] = (acc[v.status] || 0) + 1;
    return acc;
  }, {});
  const pieData = Object.entries(statusCounts).map(([name, value]) => ({
    name: name === "draft" ? "Utkast" : name === "posted" ? "Bokförd" : name,
    value,
    color: STATUS_COLORS[name] || "#6b7280",
  }));

  // Recent vouchers for table
  const recentVouchers = vouchers.slice(0, 5);

  // Monthly distribution mock (from voucher dates)
  const monthlyData = vouchers.reduce((acc: any, v: any) => {
    const month = v.voucher_date?.substring(0, 7) || "Okänd";
    acc[month] = (acc[month] || 0) + 1;
    return acc;
  }, {});
  const barData = Object.entries(monthlyData)
    .map(([month, count]) => ({
      month: month.substring(5) || month,
      antal: count,
    }))
    .slice(-6);

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1400px] mx-auto">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">
            Översikt
          </h1>
          <p className="text-muted-foreground mt-1">
            Välkommen till ditt bokföringssystem
          </p>
        </div>
        <div className="flex items-center gap-2">
          {healthData ? (
            <Badge variant="success" className="gap-1">
              <CheckCircle2 className="h-3 w-3" /> System online
            </Badge>
          ) : (
            <Badge variant="destructive" className="gap-1">
              <XCircle className="h-3 w-3" /> Ingen anslutning
            </Badge>
          )}
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title="Verifikationer"
          value={totalVouchers}
          icon={FileText}
          color="blue"
          loading={vLoading}
          href="/vouchers"
        />
        <KpiCard
          title="Konton"
          value={accountCount}
          icon={BookOpen}
          color="emerald"
          loading={aLoading}
          href="/accounts"
        />
        <KpiCard
          title="AI-regler"
          value={learningRulesCount}
          icon={Brain}
          color="violet"
          loading={rLoading}
          href="/learning"
        />
        <KpiCard
          title="Anomalier"
          value={anomalyData?.total_anomalies || 0}
          icon={AlertTriangle}
          color="amber"
          loading={false}
          href="/reports"
          subtitle={
            anomalyData?.high_severity
              ? `${anomalyData.high_severity} allvarliga`
              : undefined
          }
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Bar chart */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-primary" />
              Verifikationer per månad
            </CardTitle>
          </CardHeader>
          <CardContent>
            {barData.length > 0 ? (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={barData}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    className="stroke-border"
                  />
                  <XAxis
                    dataKey="month"
                    className="text-xs fill-muted-foreground"
                  />
                  <YAxis className="text-xs fill-muted-foreground" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                      color: "hsl(var(--card-foreground))",
                    }}
                  />
                  <Bar
                    dataKey="antal"
                    fill="hsl(var(--primary))"
                    radius={[6, 6, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[240px] flex items-center justify-center text-muted-foreground">
                Ingen data tillgänglig
              </div>
            )}
          </CardContent>
        </Card>

        {/* Pie chart */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-primary" />
              Statusfördelning
            </CardTitle>
          </CardHeader>
          <CardContent>
            {pieData.length > 0 ? (
              <div className="flex flex-col items-center">
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={80}
                      paddingAngle={4}
                      dataKey="value"
                    >
                      {pieData.map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "8px",
                        color: "hsl(var(--card-foreground))",
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex gap-4 mt-2">
                  {pieData.map((d, i) => (
                    <div key={i} className="flex items-center gap-1.5 text-xs">
                      <div
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: d.color }}
                      />
                      <span className="text-muted-foreground">
                        {d.name} ({d.value as number})
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="h-[200px] flex items-center justify-center text-muted-foreground">
                Ingen data
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent vouchers */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Senaste verifikationer</CardTitle>
            <CardDescription>
              De {recentVouchers.length} senaste verifikationerna
            </CardDescription>
          </div>
          <Link
            href="/vouchers"
            className="text-sm text-primary hover:underline flex items-center gap-1"
          >
            Visa alla <ArrowUpRight className="h-3 w-3" />
          </Link>
        </CardHeader>
        <CardContent>
          {vLoading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : recentVouchers.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th className="pb-3 font-medium text-muted-foreground">
                      Nr
                    </th>
                    <th className="pb-3 font-medium text-muted-foreground">
                      Datum
                    </th>
                    <th className="pb-3 font-medium text-muted-foreground">
                      Beskrivning
                    </th>
                    <th className="pb-3 font-medium text-muted-foreground">
                      Status
                    </th>
                    <th className="pb-3 font-medium text-muted-foreground text-right">
                      Belopp
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {recentVouchers.map((v: any) => {
                    const totalDebit = v.rows?.reduce(
                      (s: number, r: any) => s + (r.debit || 0),
                      0
                    );
                    return (
                      <tr
                        key={v.id}
                        className="border-b last:border-0 hover:bg-muted/50 transition-colors"
                      >
                        <td className="py-3 font-medium">
                          <Link
                            href={`/vouchers/${v.id}`}
                            className="text-primary hover:underline"
                          >
                            {v.voucher_series || "A"}
                            {v.voucher_number}
                          </Link>
                        </td>
                        <td className="py-3 text-muted-foreground">
                          {formatDate(v.voucher_date)}
                        </td>
                        <td className="py-3 max-w-[200px] truncate">
                          {v.description}
                        </td>
                        <td className="py-3">
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
                        <td className="py-3 text-right font-mono">
                          {formatCurrency(totalDebit || 0)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-muted-foreground text-center py-8">
              Inga verifikationer ännu
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function KpiCard({
  title,
  value,
  icon: Icon,
  color,
  loading,
  href,
  subtitle,
}: {
  title: string;
  value: number;
  icon: any;
  color: string;
  loading: boolean;
  href: string;
  subtitle?: string;
}) {
  const colorMap: Record<string, string> = {
    blue: "bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400",
    emerald:
      "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400",
    violet:
      "bg-violet-100 text-violet-600 dark:bg-violet-900/30 dark:text-violet-400",
    amber:
      "bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400",
  };

  return (
    <Link href={href}>
      <Card className="hover:shadow-md transition-shadow cursor-pointer group">
        <CardContent className="p-4 lg:p-6">
          <div className="flex items-center justify-between mb-3">
            <div
              className={`h-10 w-10 rounded-lg flex items-center justify-center ${colorMap[color]}`}
            >
              <Icon className="h-5 w-5" />
            </div>
            <ArrowUpRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
          {loading ? (
            <Skeleton className="h-8 w-16 mb-1" />
          ) : (
            <p className="text-2xl lg:text-3xl font-bold">{value}</p>
          )}
          <p className="text-sm text-muted-foreground">{title}</p>
          {subtitle && (
            <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
              {subtitle}
            </p>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
