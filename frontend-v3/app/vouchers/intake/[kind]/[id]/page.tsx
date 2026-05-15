"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Download,
  ExternalLink,
  FileText,
  Hash,
  Landmark,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useIntakeDetail } from "@/hooks/useData";
import type { IntakeDetailResponse, IntakeKind, IntakeStatus } from "@/lib/api";
import { formatDate } from "@/lib/utils";

const statusLabels: Record<IntakeStatus, string> = {
  pending: "Väntar",
  processing: "Bearbetas",
  processed: "Klar",
  skipped: "Hoppad över",
  failed: "Misslyckad",
  needs_attention: "Behöver granskas",
  deleted: "Borttagen",
};

const sourceTypeLabels: Record<string, string> = {
  receipt: "Kvitto",
  supplier_invoice: "Leverantörsfaktura",
  customer_invoice: "Kundfaktura",
  reimbursement: "Utlägg/ersättning",
  other: "Annat",
};

export default function IntakeDetailPage() {
  const params = useParams<{ kind?: string; id?: string }>();
  const kind = toIntakeKind(params.kind);
  const id = typeof params.id === "string" ? params.id : undefined;
  const { data: item, isLoading, isError } = useIntakeDetail(kind, id);

  if (!kind || !id) {
    return (
      <DetailFrame>
        <BackLink />
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            Intagsposten kunde inte identifieras.
          </CardContent>
        </Card>
      </DetailFrame>
    );
  }

  if (isLoading) {
    return (
      <DetailFrame>
        <BackLink />
        <Skeleton className="h-24 w-full" />
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </DetailFrame>
    );
  }

  if (isError || !item) {
    return (
      <DetailFrame>
        <BackLink />
        <Card>
          <CardContent className="p-6 space-y-3">
            <p className="text-sm text-muted-foreground">
              Intagsposten hittades inte eller kunde inte läsas.
            </p>
            <Link href="/vouchers/intake">
              <Button variant="outline">Tillbaka till intag</Button>
            </Link>
          </CardContent>
        </Card>
      </DetailFrame>
    );
  }

  const actionableError = getActionableError(item);
  const linkedVoucherIds = getLinkedVoucherIds(item);

  return (
    <DetailFrame>
      <BackLink />

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <TypeBadge kind={item.kind} />
            <StatusBadge status={item.status} />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">
            {item.kind === "bank_input" ? "Bankfil" : "Underlag"}
          </h1>
          <p className="max-w-3xl break-words text-sm text-muted-foreground">
            {item.original_filename}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {linkedVoucherIds.map((voucherId, index) => (
            <Link key={voucherId} href={`/vouchers/${voucherId}`}>
              <Button className="gap-2">
                <ExternalLink className="h-4 w-4" />
                {index === 0 ? "Öppna verifikation" : `Verifikation ${index + 1}`}
              </Button>
            </Link>
          ))}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-primary" />
            Status
          </CardTitle>
          <CardDescription>
            Aktuell intagsstatus och kopplingar till bokföringen.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <SummaryField label="Status" value={statusLabels[item.status]} />
            <SummaryField label="Uppladdad" value={formatDate(item.uploaded_at)} />
            <SummaryField label="Uppladdad av" value={item.uploaded_by || "okänd"} />
            <SummaryField
              label="Länkade verifikationer"
              value={linkedVoucherIds.length ? String(linkedVoucherIds.length) : "Inga"}
            />
          </div>

          {actionableError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-destructive" />
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-destructive">
                    Kräver granskning
                  </p>
                  <p className="whitespace-pre-wrap break-words text-sm text-foreground">
                    {actionableError}
                  </p>
                </div>
              </div>
            </div>
          )}

          {linkedVoucherIds.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {linkedVoucherIds.map((voucherId) => (
                <Link key={voucherId} href={`/vouchers/${voucherId}`}>
                  <Button variant="outline" size="sm" className="gap-2">
                    <ExternalLink className="h-3.5 w-3.5" />
                    Öppna verifikation {voucherId}
                  </Button>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              Fil
            </CardTitle>
            <CardDescription>
              Filmetadata och autentiserad nedladdningslänk.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <SummaryField label="Filnamn" value={item.original_filename} />
              <SummaryField label="MIME" value={item.mime_type || "-"} />
              <SummaryField label="Storlek" value={formatBytes(item.size_bytes)} />
              <SummaryField
                label="SHA-256"
                value={item.sha256 ? item.sha256.slice(0, 12) : "-"}
                icon={<Hash className="h-4 w-4 text-muted-foreground" />}
              />
            </div>

            <a href={item.download_url} target="_blank" rel="noopener noreferrer">
              <Button variant="outline" className="gap-2">
                <Download className="h-4 w-4" />
                Öppna fil
              </Button>
            </a>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {item.kind === "bank_input" ? (
                <Landmark className="h-5 w-5 text-primary" />
              ) : (
                <FileText className="h-5 w-5 text-primary" />
              )}
              Metadata
            </CardTitle>
            <CardDescription>
              Intagsspecifik information för agentens arbetsmaterial.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            {item.kind === "voucher_source" ? (
              <>
                <SummaryField
                  label="Typ"
                  value={
                    item.source_type
                      ? sourceTypeLabels[item.source_type] || item.source_type
                      : "-"
                  }
                />
                <SummaryField label="Förklaring" value={item.explanation || "-"} />
                <SummaryField
                  label="Senaste sammanfattning"
                  value={item.latest_processing_summary || "-"}
                />
                <SummaryField
                  label="Senaste fel"
                  value={item.latest_error_detail || "-"}
                />
              </>
            ) : (
              <>
                <SummaryField label="Bankkonto" value={item.bank_connection_id} />
                <SummaryField
                  label="Format"
                  value={item.detected_format || "Inte identifierat"}
                />
                <SummaryField
                  label="Importerade rader"
                  value={String(item.imported_count)}
                />
                <SummaryField
                  label="Hoppade över"
                  value={String(item.skipped_count)}
                />
                <SummaryField
                  label="Transaktioner"
                  value={String(item.transaction_count)}
                />
                <SummaryField label="Parse-fel" value={item.parse_error || "-"} />
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </DetailFrame>
  );
}

function DetailFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-[1100px] space-y-6 p-4 lg:p-8">{children}</div>
  );
}

function BackLink() {
  return (
    <Link
      href="/vouchers/intake"
      className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="h-4 w-4" />
      Tillbaka till intag
    </Link>
  );
}

function SummaryField({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="min-w-0 rounded-lg border bg-muted/20 p-3">
      <p className="text-xs font-semibold uppercase text-muted-foreground">
        {label}
      </p>
      <div className="mt-1 flex items-start gap-2">
        {icon}
        <p className="break-words text-sm text-foreground">{value}</p>
      </div>
    </div>
  );
}

function TypeBadge({ kind }: { kind: IntakeKind }) {
  return (
    <Badge variant="outline" className="gap-1.5">
      {kind === "bank_input" ? (
        <Landmark className="h-3 w-3" />
      ) : (
        <FileText className="h-3 w-3" />
      )}
      {kind === "bank_input" ? "Bankfil" : "Underlag"}
    </Badge>
  );
}

function StatusBadge({ status }: { status: IntakeStatus }) {
  const variant =
    status === "processed"
      ? "success"
      : status === "failed"
      ? "destructive"
      : status === "needs_attention"
      ? "warning"
      : status === "pending"
      ? "secondary"
      : "outline";

  return <Badge variant={variant}>{statusLabels[status]}</Badge>;
}

function toIntakeKind(value?: string): IntakeKind | undefined {
  if (value === "voucher_source" || value === "bank_input") {
    return value;
  }
  return undefined;
}

function getActionableError(item: IntakeDetailResponse) {
  if (item.status !== "failed" && item.status !== "needs_attention") {
    return "";
  }
  if (item.kind === "bank_input") {
    return item.parse_error || "Bankfilen behöver granskas.";
  }
  return (
    item.latest_error_detail ||
    item.latest_processing_summary ||
    "Underlaget behöver granskas."
  );
}

function getLinkedVoucherIds(item: IntakeDetailResponse) {
  const ids = new Set(item.linked_voucher_ids || []);
  item.voucher_links?.forEach((link) => ids.add(link.voucher_id));
  return Array.from(ids);
}

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0 KB";
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
