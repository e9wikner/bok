"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

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

export function useLearningRules() {
  return useQuery({
    queryKey: ["learning-rules"],
    queryFn: () => api.getLearningRules(),
    staleTime: 10 * 60 * 1000,
  });
}

export function useLearningStats() {
  return useQuery({
    queryKey: ["learning-stats"],
    queryFn: () => api.getLearningStats(),
    staleTime: 10 * 60 * 1000,
  });
}

export function useIncomeStatement(year?: number, month?: number) {
  return useQuery({
    queryKey: ["income-statement", year, month],
    queryFn: () => api.getIncomeStatement(year, month),
    staleTime: 5 * 60 * 1000,
  });
}

export function useBalanceSheet(year?: number) {
  return useQuery({
    queryKey: ["balance-sheet", year],
    queryFn: () => api.getBalanceSheet(year),
    staleTime: 5 * 60 * 1000,
  });
}

export function useReportOptions() {
  return useQuery({
    queryKey: ["report-options"],
    queryFn: () => api.getReportOptions(),
    staleTime: 10 * 60 * 1000,
  });
}

export function useGeneralLedger(accountCode: string, year?: number, month?: number) {
  return useQuery({
    queryKey: ["general-ledger", accountCode, year, month],
    queryFn: () => api.getGeneralLedger(accountCode, year, month),
    staleTime: 5 * 60 * 1000,
    enabled: !!accountCode,
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

export function useAuditLog(limit = 100, entityType?: string, action?: string) {
  return useQuery({
    queryKey: ["audit-log", limit, entityType, action],
    queryFn: () => api.getAuditLog(limit, entityType, action),
    staleTime: 30 * 1000,
  });
}
