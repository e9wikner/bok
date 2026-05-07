"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowUpRight,
  Bot,
  CheckCircle2,
  ClipboardList,
  FileClock,
  FileText,
  Receipt,
  ShieldCheck,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAccountingCorrections,
  useComplianceIssues,
  useHealth,
  useIncomeStatement,
  useInvoiceDrafts,
  useVouchers,
} from "@/hooks/useData";
import { formatCurrency, formatDate } from "@/lib/utils";

export default function DashboardPage() {
  const currentYear = new Date().getFullYear();
  const { data: healthData } = useHealth();
  const { data: vouchersData, isLoading: vouchersLoading } = useVouchers(undefined, 10);
  const { data: draftVoucherData } = useVouchers("draft", 5);
  const { data: invoiceDraftData } = useInvoiceDrafts("needs_review");
  const { data: complianceData } = useComplianceIssues();
  const { data: correctionsData } = useAccountingCorrections(5);
  const { data: incomeData, isLoading: incomeLoading } = useIncomeStatement(currentYear);

  const vouchers = vouchersData?.vouchers || [];
  const draftVouchers = draftVoucherData?.vouchers || [];
  const invoiceDrafts = invoiceDraftData?.drafts || [];
  const complianceIssues = complianceData?.issues || [];

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 lg:p-8">
      <div className="flex flex-col gap-4 border-b pb-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight lg:text-3xl">Översikt</h1>
          <p className="mt-1 max-w-2xl text-muted-foreground">
            Daglig arbetsyta för granskning, agentutkast och bokföringsstatus.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={healthData ? "success" : "destructive"} className="gap-1">
            {healthData ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
            {healthData ? "System online" : "Ingen anslutning"}
          </Badge>
          <Badge variant="outline">Räkenskapsår {currentYear}</Badge>
        </div>
      </div>

      <section className="grid gap-4 lg:grid-cols-4">
        <WorkItem
          title="Fakturautkast"
          value={invoiceDrafts.length}
          description="Agentutkast att granska"
          href="/invoices/drafts"
          icon={Receipt}
          urgent={invoiceDrafts.length > 0}
        />
        <WorkItem
          title="Verifikationsutkast"
          value={draftVouchers.length}
          description="Utkast före bokföring"
          href="/vouchers?status=draft"
          icon={FileClock}
          urgent={draftVouchers.length > 0}
        />
        <WorkItem
          title="Varningar"
          value={complianceIssues.length}
          description="Compliance att kontrollera"
          href="/audit"
          icon={AlertTriangle}
          urgent={complianceIssues.length > 0}
        />
        <WorkItem
          title="Korrigeringar"
          value={correctionsData?.total || 0}
          description="Senaste agentläsbara rättelser"
          href="/learning"
          icon={Bot}
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-[1fr_420px]">
        <Card>
          <CardHeader>
            <CardTitle>Periodens läge</CardTitle>
            <CardDescription>Resultat för {currentYear}, baserat på bokförda verifikationer.</CardDescription>
          </CardHeader>
          <CardContent>
            {incomeLoading ? (
              <div className="grid gap-4 sm:grid-cols-4">
                {[...Array(4)].map((_, index) => (
                  <Skeleton key={index} className="h-20" />
                ))}
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-4">
                <Metric label="Intäkter" value={incomeData?.revenue || 0} />
                <Metric label="Kostnader" value={incomeData?.costs || 0} />
                <Metric label="Resultat" value={incomeData?.profit || 0} strong />
                <Metric label="Verifikationer" value={incomeData?.voucher_count || 0} numeric />
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Snabbåtgärder</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2">
            <QuickLink href="/invoices/drafts" icon={Receipt} label="Granska fakturautkast" />
            <QuickLink href="/vouchers/new" icon={FileText} label="Skapa verifikation" />
            <QuickLink href="/bokslut" icon={ClipboardList} label="Öppna bokslut" />
            <QuickLink href="/learning" icon={Bot} label="Agentinstruktioner" />
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Fakturautkast att granska</CardTitle>
              <CardDescription>Skapade av agenten från fakturaunderlag.</CardDescription>
            </div>
            <Link href="/invoices/drafts" className="text-sm text-primary hover:underline">
              Visa alla
            </Link>
          </CardHeader>
          <CardContent>
            {invoiceDrafts.length > 0 ? (
              <div className="divide-y">
                {invoiceDrafts.slice(0, 5).map((draft: any) => (
                  <RowLink
                    key={draft.id}
                    href={`/invoices/drafts/${draft.id}`}
                    title={draft.customer_name}
                    meta={`${draft.reference || "Ingen referens"} · ${formatDate(draft.invoice_date)} · ${draft.row_count} rader`}
                    value={formatCurrency(draft.amount_inc_vat || 0)}
                  />
                ))}
              </div>
            ) : (
              <Empty text="Inga fakturautkast väntar på granskning." />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Senaste verifikationer</CardTitle>
              <CardDescription>Senaste bokföringshändelserna.</CardDescription>
            </div>
            <Link href="/vouchers" className="text-sm text-primary hover:underline">
              Visa alla
            </Link>
          </CardHeader>
          <CardContent>
            {vouchersLoading ? (
              <div className="space-y-3">
                {[...Array(5)].map((_, index) => (
                  <Skeleton key={index} className="h-12 w-full" />
                ))}
              </div>
            ) : vouchers.length > 0 ? (
              <div className="divide-y">
                {vouchers.slice(0, 5).map((voucher: any) => (
                  <RowLink
                    key={voucher.id}
                    href={`/vouchers/${voucher.id}`}
                    title={`${voucher.series || "A"}${voucher.number} · ${voucher.description}`}
                    meta={`${formatDate(voucher.date)} · ${voucher.status === "posted" ? "Bokförd" : "Utkast"}`}
                    value={formatCurrency(voucher.total_debit || 0)}
                  />
                ))}
              </div>
            ) : (
              <Empty text="Inga verifikationer finns ännu." />
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function WorkItem({ title, value, description, href, icon: Icon, urgent = false }: any) {
  return (
    <Link href={href}>
      <Card className="h-full transition-colors hover:bg-muted/40">
        <CardContent className="p-4">
          <div className="mb-4 flex items-start justify-between">
            <div className={`rounded-lg border p-2 ${urgent ? "text-amber-600" : "text-muted-foreground"}`}>
              <Icon className="h-5 w-5" />
            </div>
            <ArrowUpRight className="h-4 w-4 text-muted-foreground" />
          </div>
          <p className="text-3xl font-semibold">{value}</p>
          <p className="mt-1 font-medium">{title}</p>
          <p className="text-sm text-muted-foreground">{description}</p>
        </CardContent>
      </Card>
    </Link>
  );
}

function Metric({ label, value, strong = false, numeric = false }: { label: string; value: number; strong?: boolean; numeric?: boolean }) {
  return (
    <div className="rounded-lg border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className={`mt-2 font-mono text-xl ${strong ? "font-bold" : "font-semibold"}`}>
        {numeric ? value : formatCurrency(value)}
      </p>
    </div>
  );
}

function QuickLink({ href, icon: Icon, label }: any) {
  return (
    <Link href={href}>
      <Button variant="outline" className="w-full justify-start gap-2">
        <Icon className="h-4 w-4" />
        {label}
      </Button>
    </Link>
  );
}

function RowLink({ href, title, meta, value }: { href: string; title: string; meta: string; value: string }) {
  return (
    <Link href={href} className="flex items-center justify-between gap-4 py-3 hover:text-primary">
      <div className="min-w-0">
        <p className="truncate font-medium">{title}</p>
        <p className="truncate text-sm text-muted-foreground">{meta}</p>
      </div>
      <span className="shrink-0 font-mono font-semibold">{value}</span>
    </Link>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
      <ShieldCheck className="h-4 w-4" />
      {text}
    </div>
  );
}
