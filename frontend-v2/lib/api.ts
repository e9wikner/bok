import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || 'dev-key-change-in-production'

const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Authorization': `Bearer ${API_KEY}`,
    'Content-Type': 'application/json',
  },
})

export interface Voucher {
  id: string
  voucher_number: number
  voucher_date: string
  description: string
  rows: VoucherRow[]
  status: 'draft' | 'posted' | 'booked'
  created_at: string
  ai_generated?: boolean
}

export interface VoucherRow {
  account_code: string
  account_name?: string
  debit?: number
  credit?: number
  vat_code?: string
  vat_rate?: number
  vat_amount?: number
}

export interface Account {
  code: string
  name: string
  type: string
  balance?: number
}

export interface LearningRule {
  id: string
  pattern_type: string
  pattern_value: string
  corrected_account: string
  confidence: number
  usage_count: number
  is_golden: boolean
  created_at: string
}

export const api = {
  // Verifikationer
  getVouchers: async (status?: string, limit = 15, offset = 0) => {
    const { data } = await apiClient.get('/api/v1/vouchers', {
      params: { status, limit, offset }
    })
    return data
  },

  getVoucher: async (id: string) => {
    const { data } = await apiClient.get(`/api/v1/vouchers/${id}`)
    return data
  },

  updateVoucher: async (id: string, voucher: Partial<Voucher>) => {
    const { data } = await apiClient.put(`/api/v1/vouchers/${id}`, voucher)
    return data
  },

  // AI-lärande
  recordCorrection: async (originalVoucherId: string, correctedData: any, reason?: string) => {
    const { data } = await apiClient.post('/api/v1/learning/corrections', {
      original_voucher_id: originalVoucherId,
      corrected_data: correctedData,
      reason,
      teach_ai: true,
    })
    return data
  },

  getLearningRules: async () => {
    const { data } = await apiClient.get('/api/v1/learning/rules')
    return data
  },

  // Konton
  getAccounts: async () => {
    const { data } = await apiClient.get('/api/v1/accounts')
    return data
  },

  // Health
  getHealth: async () => {
    const { data } = await apiClient.get('/health')
    return data
  },
}

export default apiClient
