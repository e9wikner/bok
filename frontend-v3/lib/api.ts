import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Attach JWT token from localStorage to every request
apiClient.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("auth_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
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
    const { data } = await apiClient.get("/api/v1/health");
    return data;
  },

  // Vouchers
  getVouchers: async (status?: string, limit = 15, offset = 0, search?: string, sortBy?: string, sortOrder?: string, fiscalYearId?: string) => {
    const { data } = await apiClient.get("/api/v1/vouchers", {
      params: { status, limit, offset, search: search || undefined, sort_by: sortBy || undefined, sort_order: sortOrder || undefined, fiscal_year_id: fiscalYearId || undefined },
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
  getInvoices: async (status?: string) => {
    const { data } = await apiClient.get("/api/v1/invoices", {
      params: { status_filter: status },
    });
    return data;
  },
  getInvoice: async (id: string) => {
    const { data } = await apiClient.get(`/api/v1/invoices/${id}`);
    return data;
  },
  createInvoice: async (payload: {
    customer_name: string;
    customer_org_number?: string;
    customer_email?: string;
    invoice_date: string;
    due_date: string;
    description?: string;
    rows: {
      description: string;
      quantity: number;
      unit_price: number;
      vat_code: string;
    }[];
  }) => {
    const { data } = await apiClient.post("/api/v1/invoices", payload);
    return data;
  },
  sendInvoice: async (id: string) => {
    const { data } = await apiClient.post(`/api/v1/invoices/${id}/send`);
    return data;
  },
  bookInvoice: async (id: string, periodId: string) => {
    const { data } = await apiClient.post(`/api/v1/invoices/${id}/book`, { period_id: periodId });
    return data;
  },
  registerPayment: async (id: string, payload: { amount: number; payment_date: string; payment_method: string; reference?: string }) => {
    const { data } = await apiClient.post(`/api/v1/invoices/${id}/payment`, payload);
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
    correctedRows: any[],
    reason?: string
  ) => {
    const { data } = await apiClient.post("/api/v1/learning/corrections", {
      original_voucher_id: originalVoucherId,
      corrected_rows: correctedRows.map((r: any) => ({
        account: r.account_code || r.account,
        debit: r.debit || 0,
        credit: r.credit || 0,
        description: r.description,
      })),
      reason,
      teach_ai: true,
    });
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

  // Voucher audit trail
  getVoucherAudit: async (id: string) => {
    const { data } = await apiClient.get(`/api/v1/vouchers/${id}/audit`);
    return data;
  },

  // Voucher attachments
  getVoucherAttachments: async (id: string) => {
    const { data } = await apiClient.get(`/api/v1/vouchers/${id}/attachments`);
    return data;
  },
  uploadVoucherAttachment: async (id: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const { data } = await apiClient.post(
      `/api/v1/vouchers/${id}/attachments`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
    return data;
  },
  deleteVoucherAttachment: async (id: string, attachmentId: string) => {
    const { data } = await apiClient.delete(
      `/api/v1/vouchers/${id}/attachments/${attachmentId}`
    );
    return data;
  },

  // Update voucher
  updateVoucher: async (id: string, payload: {
    rows: { account: string; debit: number; credit: number }[];
    reason?: string;
    teach_ai?: boolean;
  }) => {
    const { data } = await apiClient.put(`/api/v1/vouchers/${id}`, payload);
    return data;
  },

  // Create voucher
  createVoucher: async (payload: {
    series?: string;
    date: string;
    period_id: string;
    description: string;
    rows: { account: string; debit: number; credit: number; description?: string }[];
    auto_post?: boolean;
  }) => {
    const { data } = await apiClient.post("/api/v1/vouchers", payload);
    return data;
  },

  // Periods
  getPeriods: async (fiscalYearId?: string) => {
    const params = fiscalYearId ? { fiscal_year_id: fiscalYearId } : undefined;
    const { data } = await apiClient.get("/api/v1/periods", { params });
    return data;
  },

  // PDF export — returns a Blob
  getPdfExport: async (endpoint: string): Promise<Blob> => {
    const { data } = await apiClient.get(endpoint, {
      responseType: "blob",
    });
    return data as Blob;
  },

  // Attachment URL helper (for <img> src and links)
  getAttachmentUrl: (voucherId: string, attachmentId: string) =>
    `${API_URL}/api/v1/vouchers/${voucherId}/attachments/${attachmentId}`,

};

export default apiClient;
