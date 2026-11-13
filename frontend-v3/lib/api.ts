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

export interface IntakeDateWarning {
  code: "waiting_for_fiscal_year" | "outside_fiscal_years";
  message: string;
  decision_id?: string;
  document_date?: string;
  fiscal_year?: { start_date: string; end_date: string };
}

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

export default apiClient;
