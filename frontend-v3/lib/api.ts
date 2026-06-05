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

export type CorrectionNoteStatus =
  | "pending"
  | "suggested"
  | "applied"
  | "dismissed"
  | "rejected";

export interface CorrectionNote {
  id: string;
  voucher_id: string;
  note_text: string;
  status: CorrectionNoteStatus;
  suggested_voucher_id?: string | null;
  rejection_reason?: string | null;
  created_at: string;
  created_by: string;
  updated_at?: string | null;
  resolved_at?: string | null;
}

export interface CorrectionRowPayload {
  account: string;
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

export interface PayrollSalarySetting {
  id: string;
  employee_id: string;
  gross_monthly_salary: number;
  preliminary_tax: number;
  employer_fee_rate_bp?: number | null;
  employer_fee_amount?: number | null;
  calculated_employer_fee: number;
  payment_day: number;
  active: boolean;
}

export interface PayrollEmployee {
  id: string;
  name: string;
  personal_number?: string | null;
  email?: string | null;
  bank_account?: string | null;
  active: boolean;
  salary_setting?: PayrollSalarySetting | null;
}

export interface Payslip {
  id: string;
  payroll_run_id: string;
  employee_id: string;
  employee_name?: string | null;
  period_year: number;
  period_month: number;
  payment_date: string;
  gross_salary: number;
  preliminary_tax: number;
  employer_fee: number;
  net_salary: number;
  total_employer_cost: number;
  status: "generated" | "sent" | "booked";
  pdf_sent_at?: string | null;
  bank_transaction_id?: string | null;
  voucher_id?: string | null;
}

export interface PayrollRunValidation {
  valid: boolean;
  errors: { code: string; message: string }[];
  warnings: { code: string; message: string }[];
  employee_count: number;
}

export interface PayrollRun {
  id: string;
  year: number;
  month: number;
  payment_date: string;
  status: "draft" | "generated" | "booked";
  payslip_count: number;
  total_gross_salary: number;
  total_preliminary_tax: number;
  total_employer_fee: number;
  total_net_salary: number;
  total_employer_cost: number;
  payslips: Payslip[];
  validation?: PayrollRunValidation | null;
}

export type IntakeStatus =
  | "pending"
  | "processing"
  | "processed"
  | "skipped"
  | "failed"
  | "needs_attention"
  | "deleted";

export type IntakeKind = "voucher_source" | "bank_input";

export interface IntakeProcessingAttempt {
  id: string;
  intake_source_id?: string;
  status: IntakeStatus;
  summary: string;
  warnings: string[];
  error_detail?: string | null;
  voucher_id?: string | null;
  actor: string;
  created_at: string;
}

export interface IntakeWorkspaceBaseItem {
  kind: IntakeKind;
  id: string;
  status: IntakeStatus;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  uploaded_by: string;
  uploaded_at: string;
  download_url: string;
  linked_voucher_ids: string[];
}

export interface VoucherSourceWorkspaceItem extends IntakeWorkspaceBaseItem {
  kind: "voucher_source";
  source_type?: string | null;
  explanation?: string | null;
  agent_guidance?: string | null;
  latest_processing_summary?: string | null;
  latest_error_detail?: string | null;
}

export interface BankInputWorkspaceItem extends IntakeWorkspaceBaseItem {
  kind: "bank_input";
  bank_connection_id: string;
  imported_count: number;
  skipped_count: number;
  detected_format?: string | null;
  parse_error?: string | null;
  transaction_ids: string[];
  transaction_count: number;
  match_signals: {
    id: string;
    status: string;
    matched_voucher_id?: string | null;
  }[];
}

export type IntakeWorkspaceItem =
  | VoucherSourceWorkspaceItem
  | BankInputWorkspaceItem;

export interface IntakeWorkspaceResponse {
  items: IntakeWorkspaceItem[];
  total: number;
  limit: number;
  offset: number;
  status_counts: Record<string, number>;
}

export type IntakeDetailResponse = IntakeWorkspaceItem & {
  processing_attempts?: IntakeProcessingAttempt[];
  voucher_links?: {
    id: string;
    voucher_id: string;
    intake_source_id?: string;
    bank_input_id?: string;
    linked_by: string;
    linked_at: string;
    link_reason?: string | null;
  }[];
  transactions?: {
    id: string;
    status: string;
    matched_voucher_id?: string | null;
  }[];
  processed_at?: string | null;
  deleted_at?: string | null;
  deleted_by?: string | null;
};

export interface IntakeSourceUploadResponse {
  id: string;
  source_type?: string | null;
  status: IntakeStatus;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  explanation?: string | null;
  agent_guidance?: string | null;
  uploaded_by: string;
  uploaded_at: string;
  deleted_at?: string | null;
  deleted_by?: string | null;
}

export interface BankInputUploadResponse {
  id: string;
  bank_connection_id: string;
  status: "pending" | "processed" | "failed";
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  uploaded_by: string;
  uploaded_at: string;
  detected_format?: string | null;
  imported_count: number;
  skipped_count: number;
  parse_error?: string | null;
  processed_at?: string | null;
}

export interface BankConnectionOption {
  id: string;
  provider: string;
  bank_name: string;
  display_name?: string;
  account_number?: string | null;
  iban?: string | null;
  currency: string;
  status: string;
}

export interface VoucherSourceContext {
  voucher_id: string;
  source_material: (
    | (VoucherSourceWorkspaceItem & {
        linked_at: string;
        linked_by: string;
        link_reason?: string | null;
      })
    | (BankInputWorkspaceItem & {
        linked_at: string;
        linked_by: string;
        link_reason?: string | null;
      })
  )[];
  processing_notes: (IntakeProcessingAttempt & {
    kind: IntakeKind;
    imported_count?: number;
    skipped_count?: number;
    detected_format?: string | null;
    transaction_ids?: string[];
  })[];
  correction_chain: {
    id: string;
    original_voucher_id: string;
    correction_voucher_id?: string | null;
    correction_reason?: string | null;
    actor?: string | null;
    timestamp: string;
    change_type?: string | null;
    original_data?: {
      description: string;
      rows: {
        account_code: string;
        debit: number;
        credit: number;
        description?: string | null;
      }[];
    } | null;
    corrected_data?: {
      description: string;
      rows: {
        account_code: string;
        debit: number;
        credit: number;
        description?: string | null;
      }[];
      correction_voucher_id?: string | null;
    } | null;
  }[];
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
  getVoucherSourceContext: async (
    voucherId: string
  ): Promise<VoucherSourceContext> => {
    const { data } = await apiClient.get(
      `/api/v1/vouchers/${voucherId}/source-context`
    );
    return data;
  },
  getCorrectionNotes: async (voucherId: string): Promise<CorrectionNote[]> => {
    const { data } = await apiClient.get(
      `/api/v1/vouchers/${voucherId}/correction-notes`
    );
    return data;
  },
  createCorrectionNote: async (
    voucherId: string,
    note_text: string
  ): Promise<CorrectionNote> => {
    const { data } = await apiClient.post(
      `/api/v1/vouchers/${voucherId}/correction-notes`,
      { note_text }
    );
    return data;
  },
  approveCorrectionNote: async (
    voucherId: string,
    noteId: string,
    rows?: CorrectionRowPayload[]
  ): Promise<Voucher> => {
    const { data } = await apiClient.post(
      `/api/v1/vouchers/${voucherId}/correction-notes/${noteId}/approve`,
      { rows }
    );
    return data;
  },
  dismissCorrectionNote: async (
    voucherId: string,
    noteId: string,
    reason?: string
  ): Promise<CorrectionNote> => {
    const { data } = await apiClient.post(
      `/api/v1/vouchers/${voucherId}/correction-notes/${noteId}/dismiss`,
      { reason }
    );
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
      revenue_account?: string;
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
  createInvoiceDraft: async (payload: {
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
    const { data } = await apiClient.post("/api/v1/invoice-drafts", payload);
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

  // Payroll
  getPayrollEmployees: async (search?: string) => {
    const { data } = await apiClient.get("/api/v1/payroll/employees", { params: { search } });
    return data;
  },
  createPayrollEmployee: async (payload: {
    name: string;
    personal_number?: string;
    email?: string;
    bank_account?: string;
    active?: boolean;
  }) => {
    const { data } = await apiClient.post("/api/v1/payroll/employees", payload);
    return data;
  },
  setPayrollSalary: async (employeeId: string, payload: {
    gross_monthly_salary: number;
    preliminary_tax: number;
    employer_fee_rate_bp?: number | null;
    employer_fee_amount?: number | null;
    payment_day: number;
    active?: boolean;
  }) => {
    const { data } = await apiClient.put(`/api/v1/payroll/employees/${employeeId}/salary`, payload);
    return data;
  },
  getPayrollRuns: async () => {
    const { data } = await apiClient.get("/api/v1/payroll/runs");
    return data;
  },
  createPayrollRun: async (payload: { year: number; month: number; payment_date?: string }) => {
    const { data } = await apiClient.post("/api/v1/payroll/runs", payload);
    return data;
  },
  generatePayrollRun: async (id: string) => {
    const { data } = await apiClient.post(`/api/v1/payroll/runs/${id}/generate`);
    return data;
  },
  validatePayrollRun: async (id: string) => {
    const { data } = await apiClient.get(`/api/v1/payroll/runs/${id}/validate`);
    return data;
  },
  deletePayrollRun: async (id: string) => {
    const { data } = await apiClient.delete(`/api/v1/payroll/runs/${id}`);
    return data;
  },
  markPayslipSent: async (id: string) => {
    const { data } = await apiClient.post(`/api/v1/payroll/payslips/${id}/mark-sent`);
    return data;
  },
  bookPayslip: async (id: string, bankTransactionId: string) => {
    const { data } = await apiClient.post(`/api/v1/payroll/payslips/${id}/book`, {
      bank_transaction_id: bankTransactionId,
    });
    return data;
  },

  // Reports
  getIncomeStatement: async (year?: number, month?: number, fiscalYearId?: string) => {
    const params: any = {};
    if (fiscalYearId) params.fiscal_year_id = fiscalYearId;
    if (year) params.year = year;
    if (month) params.month = month;
    const { data } = await apiClient.get("/api/v1/reports/income-statement", { params });
    return data;
  },
  getBalanceSheet: async (year?: number, fiscalYearId?: string) => {
    const params: any = {};
    if (fiscalYearId) params.fiscal_year_id = fiscalYearId;
    if (year) params.year = year;
    const { data } = await apiClient.get("/api/v1/reports/balance-sheet", { params });
    return data;
  },
  getReportOptions: async () => {
    const { data } = await apiClient.get("/api/v1/reports/options");
    return data;
  },
  // General ledger (huvudbok per konto)
  getGeneralLedger: async (accountCode: string, year?: number, month?: number, fiscalYearId?: string) => {
    const params: any = {};
    if (fiscalYearId) params.fiscal_year_id = fiscalYearId;
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

  // Intake workspace
  getIntakeWorkspace: async (params?: {
    status?: IntakeStatus;
    kind?: IntakeKind;
    limit?: number;
    offset?: number;
  }): Promise<IntakeWorkspaceResponse> => {
    const { data } = await apiClient.get("/api/v1/intake/workspace", {
      params,
    });
    return data;
  },
  getIntakeDetail: async (
    kind: IntakeKind,
    id: string
  ): Promise<IntakeDetailResponse> => {
    const { data } = await apiClient.get(
      `/api/v1/intake/workspace/${kind}/${id}`
    );
    return data;
  },
  uploadIntakeSource: async (payload: {
    file: File;
    source_type?: string;
    explanation?: string;
    agent_guidance?: string;
  }): Promise<IntakeSourceUploadResponse> => {
    const formData = new FormData();
    formData.append("file", payload.file);
    if (payload.source_type) {
      formData.append("source_type", payload.source_type);
    }
    if (payload.explanation) {
      formData.append("explanation", payload.explanation);
    }
    if (payload.agent_guidance) {
      formData.append("agent_guidance", payload.agent_guidance);
    }
    const { data } = await apiClient.post("/api/v1/intake", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },
  updateIntakeGuidance: async (
    id: string,
    agent_guidance?: string | null
  ): Promise<IntakeSourceUploadResponse> => {
    const { data } = await apiClient.put(`/api/v1/intake/${id}/agent-guidance`, {
      agent_guidance,
    });
    return data;
  },
  getBankInputConnections: async (): Promise<{
    items: BankConnectionOption[];
  }> => {
    const { data } = await apiClient.get("/api/v1/bank-inputs/connections");
    return data;
  },
  uploadBankInput: async (payload: {
    file: File;
    bank_connection_id: string;
  }): Promise<BankInputUploadResponse> => {
    const formData = new FormData();
    formData.append("file", payload.file);
    formData.append("bank_connection_id", payload.bank_connection_id);
    const { data } = await apiClient.post("/api/v1/bank-inputs", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },
  deleteIntakeSource: async (id: string): Promise<void> => {
    await apiClient.delete(`/api/v1/intake/${id}`);
  },
  deleteBankInput: async (id: string): Promise<void> => {
    await apiClient.delete(`/api/v1/bank-inputs/${id}`);
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
    rows: { account: string; debit: number; credit: number; description?: string }[];
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
  getIntakeFile: async (kind: IntakeKind, id: string): Promise<Blob> => {
    const endpoint =
      kind === "bank_input"
        ? `/api/v1/bank-inputs/${id}/file`
        : `/api/v1/intake/${id}/file`;
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
  getIntakeFileUrl: (id: string) => `${API_URL}/api/v1/intake/${id}/file`,
  getBankInputFileUrl: (id: string) =>
    `${API_URL}/api/v1/bank-inputs/${id}/file`,
  getPayslipPdfUrl: (payslipId: string) =>
    `${API_URL}/api/v1/export/pdf/payslip/${payslipId}`,

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
