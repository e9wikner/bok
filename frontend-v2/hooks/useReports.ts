'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useIncomeStatement(year?: number, month?: number) {
  return useQuery({
    queryKey: ['income-statement', year, month],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (year) params.append('year', year.toString())
      if (month) params.append('month', month.toString())
      const { data } = await fetch(
        `/api/v1/reports/income-statement?${params}`,
        { headers: { 'Authorization': `Bearer dev-key-change-in-production` } }
      ).then(r => r.json())
      return data
    },
    staleTime: 10 * 60 * 1000,
  })
}

export function useBalanceSheet(year?: number, asOfDate?: string) {
  return useQuery({
    queryKey: ['balance-sheet', year, asOfDate],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (year) params.append('year', year.toString())
      if (asOfDate) params.append('as_of_date', asOfDate)
      const { data } = await fetch(
        `/api/v1/reports/balance-sheet?${params}`,
        { headers: { 'Authorization': `Bearer dev-key-change-in-production` } }
      ).then(r => r.json())
      return data
    },
    staleTime: 10 * 60 * 1000,
  })
}

export function useTrialBalance(year?: number, period?: number) {
  return useQuery({
    queryKey: ['trial-balance', year, period],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (year) params.append('year', year.toString())
      if (period) params.append('period', period.toString())
      const { data } = await fetch(
        `/api/v1/reports/trial-balance?${params}`,
        { headers: { 'Authorization': `Bearer dev-key-change-in-production` } }
      ).then(r => r.json())
      return data
    },
    staleTime: 10 * 60 * 1000,
  })
}
