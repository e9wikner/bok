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

