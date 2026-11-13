"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { IntakeKind, IntakeStatus } from "@/lib/api";

export function useVouchers(status?: string, limit = 15, offset = 0, search?: string, sortBy?: string, sortOrder?: string, fiscalYearId?: string, excludeSeries?: string) {
  return useQuery({
    queryKey: ["vouchers", status, limit, offset, search, sortBy, sortOrder, fiscalYearId, excludeSeries],
    queryFn: () => api.getVouchers(status, limit, offset, search, sortBy, sortOrder, fiscalYearId, excludeSeries),
    staleTime: 5 * 60 * 1000,
  });
}

export function useVoucher(id: string) {
  return useQuery({
    queryKey: ["voucher", id],
    queryFn: () => api.getVoucher(id),
    staleTime: 5 * 60 * 1000,
  });
}

export function useVoucherSourceContext(voucherId?: string) {
  return useQuery({
    queryKey: ["voucher-source-context", voucherId],
    queryFn: () => api.getVoucherSourceContext(voucherId as string),
    staleTime: 60 * 1000,
    enabled: !!voucherId,
  });
}

export function useCorrectionNotes(voucherId?: string) {
  return useQuery({
    queryKey: ["correction-notes", voucherId],
    queryFn: () => api.getCorrectionNotes(voucherId as string),
    staleTime: 60 * 1000,
    enabled: !!voucherId,
  });
}

export function useIntakeWorkspace(params?: {
  status?: IntakeStatus;
  kind?: IntakeKind;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: [
      "intake-workspace",
      params?.status,
      params?.kind,
      params?.limit,
      params?.offset,
    ],
    queryFn: () => api.getIntakeWorkspace(params),
    staleTime: 60 * 1000,
  });
}

export function useDropzoneStatus() {
  return useQuery({
    queryKey: ["dropzone-status"],
    queryFn: () => api.getDropzoneStatus(),
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
  });
}

export function useIntakeDetail(kind?: IntakeKind, id?: string) {
  return useQuery({
    queryKey: ["intake-detail", kind, id],
    queryFn: () => api.getIntakeDetail(kind as IntakeKind, id as string),
    staleTime: 60 * 1000,
    enabled: !!kind && !!id,
  });
}

export function useBankInputConnections() {
  return useQuery({
    queryKey: ["bank-input-connections"],
    queryFn: () => api.getBankInputConnections(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useAccounts() {
  return useQuery({
    queryKey: ["accounts"],
    queryFn: () => api.getAccounts(),
    staleTime: 10 * 60 * 1000,
  });
}

export function useInvoices(status?: string, limit?: number, offset?: number, search?: string) {
  return useQuery({
    queryKey: ["invoices", status, limit, offset, search],
    queryFn: () => api.getInvoices(status, limit, offset, search),
    staleTime: 5 * 60 * 1000,
  });
}

export function useInvoiceDrafts(status?: string) {
  return useQuery({
    queryKey: ["invoice-drafts", status],
    queryFn: () => api.getInvoiceDrafts(status),
    staleTime: 2 * 60 * 1000,
  });
}

export function useInvoiceDraft(id: string) {
  return useQuery({
    queryKey: ["invoice-draft", id],
    queryFn: () => api.getInvoiceDraft(id),
    staleTime: 2 * 60 * 1000,
    enabled: !!id,
  });
}

export function useCustomers(search?: string) {
  return useQuery({
    queryKey: ["customers", search],
    queryFn: () => api.getCustomers(search),
    staleTime: 5 * 60 * 1000,
  });
}

export function useArticles(search?: string) {
  return useQuery({
    queryKey: ["articles", search],
    queryFn: () => api.getArticles(search),
    staleTime: 5 * 60 * 1000,
  });
}

export function useAccountingCorrections(limit = 25) {
  return useQuery({
    queryKey: ["accounting-corrections", limit],
    queryFn: () => api.getAccountingCorrections(limit),
    staleTime: 60 * 1000,
  });
}

export function useIncomeStatement(year?: number, month?: number, fiscalYearId?: string) {
  return useQuery({
    queryKey: ["income-statement", year, month, fiscalYearId],
    queryFn: () => api.getIncomeStatement(year, month, fiscalYearId),
    staleTime: 5 * 60 * 1000,
  });
}

export function usePeriods(fiscalYearId?: string) {
  return useQuery({
    queryKey: ["periods", fiscalYearId],
    queryFn: () => api.getPeriods(fiscalYearId),
    staleTime: 10 * 60 * 1000,
  });
}

export function useFiscalYears() {
  return useQuery({
    queryKey: ["fiscal-years"],
    queryFn: () => api.getFiscalYears(),
    staleTime: 10 * 60 * 1000,
  });
}

export function useComplianceIssues() {
  return useQuery({
    queryKey: ["compliance-issues"],
    queryFn: () => api.getComplianceIssues(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => api.getHealth(),
    staleTime: 30 * 1000,
    retry: 1,
  });
}

