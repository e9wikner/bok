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

/**
 * Vad ett `401` gör. Ett objekt, inte fria funktioner, så att testerna kan
 * byta ut navigeringen — jsdom kan inte navigera.
 */
export const obehorig = {
  sokvag: (): string => (typeof window !== "undefined" ? window.location.pathname : ""),
  ga: (url: string): void => {
    if (typeof window !== "undefined") window.location.href = url;
  },
};

// En utgången eller återkallad token loggar ut — samma sak som
// `useAuth().logout` gör: token bort, till /login. Utan det gav en utgången
// session tysta fel på varje sida. Inte på /login självt: där vore det en
// loop. Felet kastas vidare, så anroparens egen felhantering körs ändå.
apiClient.interceptors.response.use(undefined, (error) => {
  if (error?.response?.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("auth_token");
    if (obehorig.sokvag() !== "/login") obehorig.ga("/login");
  }
  return Promise.reject(error);
});

// Types
export interface Voucher {
  id: string;
  /** `null` för ett utkast; numret sätts vid postning. */
  number: number | null;
  series: string;
  date: string;
  period_id: string;
  description: string;
  /** Kommentaren som skrevs när verifikationen skapades, t.ex. växlingskursen. */
  comment?: string | null;
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
  voucher_id?: string | null;
  // Empty on invoices from before fakturering F0.
  issued_at?: string | null;
  issued_by?: string | null;
  /** The stored PDF; null for an invoice not issued in Bok. */
  pdf_url?: string | null;
  customer_address?: string | null;
  customer_reference?: string | null;
  payment_terms_days?: number | null;
  source_draft_id?: string | null;
}

export interface InvoiceRow {
  description: string;
  /** Decimal, at most two decimals (7.5 h). */
  quantity: number;
  quantity_centi?: number;
  unit?: string | null;
  unit_price: number;
  vat_code: string;
  revenue_account?: string | null;
  article_number?: string | null;
  delivery_from?: string | null;
  delivery_to?: string | null;
  delivery_month?: string | null;
  amount_ex_vat?: number;
  vat_amount?: number;
  amount_inc_vat?: number;
}

/** A row as `POST/PUT /invoice-drafts` takes it. */
export interface InvoiceDraftRowPayload {
  article_id?: string | null;
  description?: string | null;
  /** Positive, at most two decimals; 7.5 or "7,5". */
  quantity: number | string;
  unit?: string | null;
  unit_price?: number | null;
  vat_code?: string | null;
  revenue_account?: string | null;
  source_note?: string | null;
  article_number?: string | null;
  delivery_from?: string | null;
  delivery_to?: string | null;
  delivery_month?: string | null;
}

/**
 * The whole draft as `POST/PUT /invoice-drafts` takes it. PUT replaces the
 * draft: a field left out is cleared.
 */
export interface InvoiceDraftPayload {
  customer_id?: string | null;
  customer_name?: string | null;
  customer_org_number?: string | null;
  customer_email?: string | null;
  invoice_date: string;
  due_date?: string | null;
  /** Er referens. */
  reference?: string | null;
  description?: string | null;
  invoice_number?: string | null;
  customer_address?: string | null;
  delivery_from?: string | null;
  delivery_to?: string | null;
  /** YYYY-MM, when the exact date is not known. */
  delivery_month?: string | null;
  status?: "draft" | "needs_review";
  rows: InvoiceDraftRowPayload[];
  agent_notes?: {
    summary?: string | null;
    confidence?: number | null;
    warnings?: string[];
  };
}

export interface IssuedInvoice {
  invoice_id: string;
  invoice_number: string;
  voucher_id: string;
  pdf_url: string;
}

export interface InvoicePdf {
  blob: Blob;
  filename: string | null;
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
  website?: string | null;
  /** Säte; krävs för att utfärda en faktura. */
  seat?: string | null;
  /** SE + organisationsnumrets tio siffror + 01; krävs för en faktura. */
  vat_number?: string | null;
  bankgiro?: string | null;
  plusgiro?: string | null;
  /** Godkänd för F-skatt; står på fakturan. */
  f_skatt?: boolean;
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
  /** The PDF stored when the payslip was generated (migration 050). */
  pdf_stored?: boolean;
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

export interface AgiIndividual {
  employee_id: string;
  name: string;
  personal_number?: string | null;
  gross_salary: number;
  preliminary_tax: number;
  employer_fee: number;
}

export interface AgiDeclaration {
  year: number;
  month: number;
  due_date: string;
  individuals: AgiIndividual[];
  total_gross_salary: number;
  total_preliminary_tax: number;
  total_employer_fee: number;
  total_to_pay: number;
  unbooked_payslips: number;
  voucher_ids: Partial<Record<"tax" | "employer_fee", string>>;
  booked: boolean;
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
  /** Dated outside every fiscal year, or waiting on a proposed one. */
  date_warning?: IntakeDateWarning | null;
}

export interface IntakeDateWarning {
  code: "waiting_for_fiscal_year" | "outside_fiscal_years";
  message: string;
  decision_id?: string;
  document_date?: string;
  fiscal_year?: { start_date: string; end_date: string };
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
  /** Transactions no fiscal year holds: not bookable, shown in no year. */
  transactions_outside_fiscal_years?: number;
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

export interface DropzoneStatus {
  enabled: boolean;
  dropzone_dir: string;
  scan_interval_seconds: number;
  last_scan_at: string | null;
  last_scan_duration_ms: number | null;
  pending_file_count: number;
  ingested_total: number;
  problem_file_count: number;
  /** Underlag and statement transactions dated outside every fiscal year. */
  date_warnings?: {
    underlag: (IntakeDateWarning & {
      source_id: string;
      original_filename: string;
      status: string;
    })[];
    bank_transactions_outside_fiscal_years: number | null;
  };
  last_error: string | null;
}

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
  /**
   * The PDF stored when the invoice was issued, byte for byte. An invoice
   * from before F0 has none (404 `pdf_not_stored`); `getPdfExport` renders
   * one from `/api/v1/export/pdf/invoice/{id}` instead.
   */
  getInvoicePdf: async (id: string): Promise<InvoicePdf> => {
    const response = await apiClient.get(`/api/v1/invoices/${id}/pdf`, {
      responseType: "blob",
    });
    const disposition: string | undefined = response.headers?.["content-disposition"];
    const match = disposition?.match(/filename="?([^";]+)"?/);
    return { blob: response.data as Blob, filename: match ? match[1] : null };
  },
  getInvoiceDrafts: async (status?: string) => {
    const { data } = await apiClient.get("/api/v1/invoice-drafts", {
      params: { status_filter: status },
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

  // Compliance
  getComplianceIssues: async () => {
    const { data } = await apiClient.get("/api/v1/compliance/issues");
    return data;
  },

  // Fiscal years
  getFiscalYears: async () => {
    const { data } = await apiClient.get("/api/v1/fiscal-years");
    return data;
  },

  getAccountingCorrections: async (limit = 100) => {
    const { data } = await apiClient.get("/api/v1/accounting-corrections", { params: { limit } });
    return data;
  },

  // PDF export — returns a Blob
  getPdfExport: async (endpoint: string): Promise<Blob> => {
    const { data } = await apiClient.get(endpoint, {
      responseType: "blob",
    });
    return data as Blob;
  },

};

export default apiClient;
