'use client'

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useVouchers(status?: string, limit = 15, offset = 0) {
  return useQuery({
    queryKey: ['vouchers', status, limit, offset],
    queryFn: () => api.getVouchers(status, limit, offset),
    staleTime: 5 * 60 * 1000, // 5 minuter
  })
}

export function useVoucher(id: string) {
  return useQuery({
    queryKey: ['vouchers', id],
    queryFn: () => api.getVoucher(id),
    staleTime: 5 * 60 * 1000,
  })
}

export function useAccounts() {
  return useQuery({
    queryKey: ['accounts'],
    queryFn: () => api.getAccounts(),
    staleTime: 10 * 60 * 1000, // 10 minuter
  })
}

export function useLearningRules() {
  return useQuery({
    queryKey: ['learning-rules'],
    queryFn: () => api.getLearningRules(),
    staleTime: 10 * 60 * 1000,
  })
}
