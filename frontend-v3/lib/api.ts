import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY =
  process.env.NEXT_PUBLIC_API_KEY || "dev-key-change-in-production";

const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    Authorization: `Bearer ${API_KEY}`,
    "Content-Type": "application/json",
  },
});

// Types
export interface Voucher {
  id: string;
  number: number;
  series: string;
  date: string;
  period_id: string;
  description: string;
  rows: VoucherRow[];
  status: "draft" | "posted";
  created_at: string;
  created_by: string;
  posted_at?: string;
  correction_of?: string;
}

export interface VoucherRow {
  id: string;
  voucher_id: string;
  account_code: string;
  debit: number;
  credit: number;
  description?: string;
}

export interface Account {
  code: string;
  name: string;
  account_type: string;
  vat_code?: string;
  active: boolean;
}

export interface LearningRule {
  id: string;
  pattern_type: string;
  pattern_value: string;
  corrected_account: string;
  confidence: number;
  usage_count: number;
  is_golden: boolean;
  created_at: string;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  customer_name: string;
  customer_org_number?: string;
  invoice_date: string;
  due_date: string;
  status: "draft" | "sent" | "paid" | "overdue" | "cancelled";
  amount_inc_vat: number;
  amount_ex_vat: number;
  vat_amount: number;
  rows: InvoiceRow[];
  created_at: string;
}

export interface InvoiceRow {
  description: string;
  quantity: number;
  unit_price: number;
  vat_code: string;
  vat_rate: number;
  total: number;
}

export interface AnomalySummary {
  total_anomalies: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
  by_severity: Record<string, number>;
  by_type: Record<string, number>;
  avg_score: number;
  top_anomalies: any[];
}

export interface ComplianceIssue {
  id: string;
  issue_type: string;
  severity: string;
  description: string;
  created_at: string;
}

export const api = {
  // Health
  getHealth: async () => {
    const { data } = await apiClient.get("/health");
    return data;
  },

  // Vouchers
  getVouchers: async (status?: string, limit = 15, offset = 0) => {
    const { data } = await apiClient.get("/api/v1/vouchers", {
      params: { status, limit, offset },
    });
    return data;
  },
  getVoucher: async (id: string) => {
    const { data } = await apiClient.get(`/api/v1/vouchers/${id}`);
    return data;
  },

  // Accounts
  getAccounts: async () => {
    const { data } = await apiClient.get("/api/v1/accounts");
    return data;
  },

  // Invoices
  getInvoices: async () => {
    const { data } = await apiClient.get("/api/v1/invoices");
    return data;
  },
  getInvoice: async (id: string) => {
    const { data } = await apiClient.get(`/api/v1/invoices/${id}`);
    return data;
  },

  // Reports
  getIncomeStatement: async (year?: number, month?: number) => {
    const params: any = {};
    if (year) params.year = year;
    if (month) params.month = month;
    const { data } = await apiClient.get("/api/v1/reports/income-statement", { params });
    return data;
  },
  getBalanceSheet: async (year?: number) => {
    const params: any = {};
    if (year) params.year = year;
    const { data } = await apiClient.get("/api/v1/reports/balance-sheet", { params });
    return data;
  },
  getTrialBalance: async (year?: number, period?: number) => {
    const params: any = {};
    if (year) params.year = year;
    if (period) params.period = period;
    const { data } = await apiClient.get("/api/v1/reports/trial-balance", { params });
    return data;
  },

  // General ledger (huvudbok per konto)
  getGeneralLedger: async (accountCode: string, year?: number, month?: number) => {
    const params: any = {};
    if (year) params.year = year;
    if (month) params.month = month;
    const { data } = await apiClient.get(`/api/v1/reports/general-ledger/${accountCode}`, { params });
    return data;
  },

  // Learning
  getLearningRules: async () => {
    const { data } = await apiClient.get("/api/v1/learning/rules");
    return data;
  },
  getLearningStats: async () => {
    const { data } = await apiClient.get("/api/v1/learning/stats");
    return data;
  },
  recordCorrection: async (
    originalVoucherId: string,
    correctedData: any,
    reason?: string
  ) => {
    const { data } = await apiClient.post("/api/v1/learning/corrections", {
      original_voucher_id: originalVoucherId,
      corrected_data: correctedData,
      reason,
      teach_ai: true,
    });
    return data;
  },

  // Anomalies
  getAnomalySummary: async () => {
    const { data } = await apiClient.get("/api/v1/anomalies/summary");
    return data;
  },
  getAnomalies: async () => {
    const { data } = await apiClient.get("/api/v1/anomalies");
    return data;
  },

  // Compliance
  getComplianceIssues: async () => {
    const { data } = await apiClient.get("/api/v1/compliance/issues");
    return data;
  },
  runComplianceCheck: async () => {
    const { data } = await apiClient.post("/api/v1/compliance/check");
    return data;
  },

  // VAT
  getVatDeclarations: async () => {
    const { data } = await apiClient.get("/api/v1/vat/declarations");
    return data;
  },

  // Import/Export
  importSie4: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const { data } = await apiClient.post("/api/v1/import/sie4", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },
  importCsv: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const { data } = await apiClient.post("/api/v1/import/csv", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },
  exportSie4: async () => {
    const { data } = await apiClient.get("/api/v1/export/sie4");
    return data;
  },

  // Fiscal years
  getFiscalYears: async () => {
    const { data } = await apiClient.get("/api/v1/fiscal-years");
    return data;
  },
};

export default apiClient;
