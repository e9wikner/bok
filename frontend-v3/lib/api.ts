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

export interface Customer {
  id: string;
  name: string;
  org_number?: string | null;
  email?: string | null;
  address?: string | null;
  payment_terms_days: number;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Article {
  id: string;
  article_number: string;
  name: string;
  description?: string | null;
  unit: string;
  unit_price: number;
  vat_code: string;
  revenue_account: string;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ComplianceIssue {
  id: string;
  issue_type: string;
  severity: string;
  description: string;
  created_at: string;
}

export interface CompanyInfo {
  name: string;
  org_number: string;
  contact_name?: string | null;
  address?: string | null;
  postnr?: string | null;
  postort?: string | null;
  email?: string | null;
  phone?: string | null;
}

export const api = {
  // Health
  getHealth: async () => {
    const { data } = await apiClient.get("/api/v1/health");
    return data;
  },

  // Vouchers
  getVouchers: async (status?: string, limit = 15, offset = 0, search?: string, sortBy?: string, sortOrder?: string, fiscalYearId?: string, excludeSeries?: string) => {
    const { data } = await apiClient.get("/api/v1/vouchers", {
      params: { status, limit, offset, search: search || undefined, sort_by: sortBy || undefined, sort_order: sortOrder || undefined, fiscal_year_id: fiscalYearId || undefined, exclude_series: excludeSeries || undefined },
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
  getInvoices: async (status?: string, limit?: number, offset?: number, search?: string) => {
    const { data } = await apiClient.get("/api/v1/invoices", {
      params: {
        status_filter: status,
        limit,
        offset,
        search: search || undefined,
      },
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
      revenue_account?: string;
    }[];
  }) => {
    const { data } = await apiClient.post("/api/v1/invoices", payload);
    return data;
  },
  previewInvoice: async (payload: {
    rows: {
      description: string;
      quantity: number;
      unit_price: number;
      vat_code: string;
    }[];
  }) => {
    const { data } = await apiClient.post("/api/v1/invoices/preview", payload);
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
  getInvoiceDrafts: async (status?: string) => {
    const { data } = await apiClient.get("/api/v1/invoice-drafts", {
      params: { status_filter: status },
    });
    return data;
  },
  getInvoiceDraft: async (id: string) => {
    const { data } = await apiClient.get(`/api/v1/invoice-drafts/${id}`);
    return data;
  },
  updateInvoiceDraft: async (id: string, payload: {
    customer_id?: string | null;
    customer_name?: string | null;
    customer_org_number?: string | null;
    customer_email?: string | null;
    invoice_date: string;
    due_date?: string | null;
    reference?: string | null;
    description?: string | null;
    status?: "draft" | "needs_review";
    rows: {
      article_id?: string | null;
      description?: string | null;
      quantity: number;
      unit_price?: number | null;
      vat_code?: string | null;
      revenue_account?: string | null;
      source_note?: string | null;
    }[];
    agent_notes?: {
      summary?: string | null;
      confidence?: number | null;
      warnings?: string[];
    };
  }) => {
    const { data } = await apiClient.put(`/api/v1/invoice-drafts/${id}`, payload);
    return data;
  },
  sendInvoiceDraft: async (id: string, periodId?: string) => {
    const { data } = await apiClient.post(`/api/v1/invoice-drafts/${id}/send`, {
      period_id: periodId || undefined,
    });
    return data;
  },
  rejectInvoiceDraft: async (id: string) => {
    const { data } = await apiClient.post(`/api/v1/invoice-drafts/${id}/reject`);
    return data;
  },
  getCustomers: async (search?: string) => {
    const { data } = await apiClient.get("/api/v1/customers", { params: { search } });
    return data;
  },
  createCustomer: async (payload: {
    name: string;
    org_number?: string;
    email?: string;
    address?: string;
    payment_terms_days: number;
  }) => {
    const { data } = await apiClient.post("/api/v1/customers", payload);
    return data;
  },
  getArticles: async (search?: string) => {
    const { data } = await apiClient.get("/api/v1/articles", { params: { search } });
    return data;
  },
  createArticle: async (payload: {
    article_number: string;
    name: string;
    description?: string;
    unit: string;
    unit_price: number;
    vat_code: string;
    revenue_account: string;
  }) => {
    const { data } = await apiClient.post("/api/v1/articles", payload);
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
  getReportOptions: async () => {
    const { data } = await apiClient.get("/api/v1/reports/options");
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
  getYearlyVatDeclaration: async (year: number) => {
    const { data } = await apiClient.get(`/api/v1/vat/declarations/yearly/${year}`);
    return data;
  },
  exportVatEskd: async (year: number) => {
    const response = await apiClient.get(`/api/v1/vat/export/eskd/${year}`, {
      responseType: "blob",
    });
    return response;
  },
  exportVatPdf: async (year: number): Promise<Blob> => {
    const { data } = await apiClient.get(`/api/v1/vat/export/pdf/${year}`, {
      responseType: "blob",
    });
    return data as Blob;
  },

  // Company info
  getCompanyInfo: async (): Promise<CompanyInfo> => {
    const { data } = await apiClient.get("/api/v1/company-info");
    return data;
  },
  updateCompanyInfo: async (payload: CompanyInfo): Promise<CompanyInfo> => {
    const { data } = await apiClient.put("/api/v1/company-info", payload);
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
  }) => {
    const { data } = await apiClient.put(`/api/v1/vouchers/${id}`, payload);
    return data;
  },
  correctVoucher: async (id: string, payload: {
    corrected_rows: { account: string; debit: number; credit: number; description?: string }[];
    reason?: string;
  }) => {
    const { data } = await apiClient.post(`/api/v1/vouchers/${id}/correct`, payload);
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

  // Agent instructions and correction history
  getAgentInstructions: async (scope = "accounting") => {
    const { data } = await apiClient.get(`/api/v1/agent-instructions/${scope}`);
    return data;
  },
  updateAgentInstructions: async (payload: { content_markdown: string; change_summary?: string }, scope = "accounting") => {
    const { data } = await apiClient.put(`/api/v1/agent-instructions/${scope}`, payload);
    return data;
  },
  getAgentInstructionVersions: async (scope = "accounting") => {
    const { data } = await apiClient.get(`/api/v1/agent-instructions/${scope}/versions`);
    return data;
  },
  getAccountingCorrections: async (limit = 100) => {
    const { data } = await apiClient.get("/api/v1/accounting-corrections", { params: { limit } });
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
  getReportPdfExport: async (report: "income" | "balance", fiscalYearId: string, month?: number): Promise<Blob> => {
    const endpoint = report === "income" ? "/api/v1/export/pdf/income-statement" : "/api/v1/export/pdf/balance-sheet";
    const { data } = await apiClient.get(endpoint, {
      params: { fiscal_year_id: fiscalYearId, month: month || undefined },
      responseType: "blob",
    });
    return data as Blob;
  },

  // Attachment URL helper (for <img> src and links)
  getAttachmentUrl: (voucherId: string, attachmentId: string) =>
    `${API_URL}/api/v1/vouchers/${voucherId}/attachments/${attachmentId}`,

  // Audit Log
  getAuditLog: async (limit = 100, entityType?: string, action?: string) => {
    const { data } = await apiClient.get("/api/v1/audit/log", {
      params: { limit, entity_type: entityType, action },
    });
    return data;
  },

  // SRU Mappings
  getSRUMappings: async (fiscalYearId: string) => {
    const { data } = await apiClient.get(`/api/v1/fiscal-years/${fiscalYearId}/sru-mappings`);
    return data;
  },

  getDefaultSRUMappings: async (fiscalYearId: string) => {
    const { data } = await apiClient.get(`/api/v1/fiscal-years/${fiscalYearId}/sru-mappings/default`);
    return data;
  },

  updateSRUMapping: async (fiscalYearId: string, accountId: string, sruField: string) => {
    const { data } = await apiClient.post(`/api/v1/fiscal-years/${fiscalYearId}/sru-mappings`, {
      account_id: accountId,
      sru_field: sruField,
    });
    return data;
  },

  bulkUpdateSRUMappings: async (fiscalYearId: string, mappings: { account_id: string; sru_field: string }[]) => {
    const { data } = await apiClient.post(`/api/v1/fiscal-years/${fiscalYearId}/sru-mappings/bulk`, mappings);
    return data;
  },

  deleteSRUMapping: async (fiscalYearId: string, mappingId: string) => {
    const { data } = await apiClient.delete(`/api/v1/fiscal-years/${fiscalYearId}/sru-mappings/${mappingId}`);
    return data;
  },

  inheritPreviousSRUMappings: async (fiscalYearId: string) => {
    const { data } = await apiClient.post(`/api/v1/fiscal-years/${fiscalYearId}/sru-mappings/inherit-previous`);
    return data;
  },

  resetDefaultSRUMappings: async (fiscalYearId: string) => {
    const { data } = await apiClient.post(`/api/v1/fiscal-years/${fiscalYearId}/sru-mappings/reset-default`);
    return data;
  },

  // SRU Export
  exportSRU: async (fiscalYearId: string) => {
    const response = await apiClient.get(`/api/v1/export/sru/${fiscalYearId}`, {
      responseType: "blob",
    });
    return response;
  },
  exportSRUByYear: async (year: number) => {
    const response = await apiClient.get(`/api/v1/export/sru/by-year/${year}`, {
      responseType: "blob",
    });
    return response;
  },

  previewSRU: async (fiscalYearId: string) => {
    const { data } = await apiClient.get(`/api/v1/export/sru/${fiscalYearId}/preview`);
    return data;
  },

  getINK2Declaration: async (fiscalYearId: string) => {
    const { data } = await apiClient.get(`/api/v1/tax/ink2/${fiscalYearId}`);
    return data;
  },

};

export default apiClient;
