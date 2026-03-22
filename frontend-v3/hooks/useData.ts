"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useVouchers(status?: string, limit = 15, offset = 0) {
  return useQuery({
    queryKey: ["vouchers", status, limit, offset],
    queryFn: () => api.getVouchers(status, limit, offset),
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

export function useInvoices() {
  return useQuery({
    queryKey: ["invoices"],
    queryFn: () => api.getInvoices(),
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

export function useIncomeStatement(periodId?: string) {
  return useQuery({
    queryKey: ["income-statement", periodId],
    queryFn: () => api.getIncomeStatement(periodId),
    staleTime: 5 * 60 * 1000,
  });
}

export function useBalanceSheet(periodId?: string) {
  return useQuery({
    queryKey: ["balance-sheet", periodId],
    queryFn: () => api.getBalanceSheet(periodId),
    staleTime: 5 * 60 * 1000,
  });
}

export function useTrialBalance() {
  return useQuery({
    queryKey: ["trial-balance"],
    queryFn: () => api.getTrialBalance(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useAnomalySummary() {
  return useQuery({
    queryKey: ["anomaly-summary"],
    queryFn: () => api.getAnomalySummary(),
    staleTime: 5 * 60 * 1000,
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
