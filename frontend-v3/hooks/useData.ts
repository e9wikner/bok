"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useTenant } from "./useTenant";

export function useCurrentTenant() {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["current-tenant", tenantId],
    queryFn: () => api.getCurrentTenant(),
    staleTime: 10 * 60 * 1000,
  });
}

export function useVouchers(status?: string, limit = 15, offset = 0, search?: string) {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["vouchers", tenantId, status, limit, offset, search],
    queryFn: () => api.getVouchers(status, limit, offset, search),
    staleTime: 5 * 60 * 1000,
  });
}

export function useVoucher(id: string) {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["voucher", tenantId, id],
    queryFn: () => api.getVoucher(id),
    staleTime: 5 * 60 * 1000,
  });
}

export function useAccounts() {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["accounts", tenantId],
    queryFn: () => api.getAccounts(),
    staleTime: 10 * 60 * 1000,
  });
}

export function useInvoices() {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["invoices", tenantId],
    queryFn: () => api.getInvoices(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useLearningRules() {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["learning-rules", tenantId],
    queryFn: () => api.getLearningRules(),
    staleTime: 10 * 60 * 1000,
  });
}

export function useLearningStats() {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["learning-stats", tenantId],
    queryFn: () => api.getLearningStats(),
    staleTime: 10 * 60 * 1000,
  });
}

export function useIncomeStatement(year?: number, month?: number) {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["income-statement", tenantId, year, month],
    queryFn: () => api.getIncomeStatement(year, month),
    staleTime: 5 * 60 * 1000,
  });
}

export function useBalanceSheet(year?: number) {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["balance-sheet", tenantId, year],
    queryFn: () => api.getBalanceSheet(year),
    staleTime: 5 * 60 * 1000,
  });
}

export function useTrialBalance(year?: number, period?: number) {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["trial-balance", tenantId, year, period],
    queryFn: () => api.getTrialBalance(year, period),
    staleTime: 5 * 60 * 1000,
  });
}

export function useGeneralLedger(accountCode: string, year?: number, month?: number) {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["general-ledger", tenantId, accountCode, year, month],
    queryFn: () => api.getGeneralLedger(accountCode, year, month),
    staleTime: 5 * 60 * 1000,
    enabled: !!accountCode,
  });
}

export function usePeriods(fiscalYearId?: string) {
  return useQuery({
    queryKey: ["periods", fiscalYearId],
    queryFn: () => api.getPeriods(),
    staleTime: 10 * 60 * 1000,
  });
}

export function useFiscalYears() {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["fiscal-years", tenantId],
    queryFn: () => api.getFiscalYears(),
    staleTime: 10 * 60 * 1000,
  });
}

export function useAnomalySummary() {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["anomaly-summary", tenantId],
    queryFn: () => api.getAnomalySummary(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useAnomalies(limit = 50) {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["anomalies", tenantId, limit],
    queryFn: () => api.getAnomalies(limit),
    staleTime: 5 * 60 * 1000,
  });
}

export function useComplianceIssues() {
  const { tenantId } = useTenant();
  return useQuery({
    queryKey: ["compliance-issues", tenantId],
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
