/**
 * Fakturering F0 in the old pages (SPEC-fakturering.md §7): the error codes
 * from `/invoice-drafts` and `/issue` in Swedish, decimal quantities and the
 * download of an invoice's PDF.
 */
import { api } from "@/lib/api";

const COMPANY_INFO_LABELS: Record<string, string> = {
  name: "företagsnamn",
  address: "adress",
  org_number: "organisationsnummer",
  seat: "säte",
  vat_number: "momsregistreringsnummer (SE + orgnr + 01)",
  bankgiro_or_plusgiro: "bankgiro eller plusgiro",
};

type ErrorDetail = {
  code?: string;
  error?: string;
  details?: string;
  missing?: string[];
  invoice_number?: string;
  invoice_id?: string;
  locked_by?: string;
  locked_at?: string;
};

/** The backend's `detail` if it is an object with a `code`, else null. */
export function errorDetail(err: unknown): ErrorDetail | null {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return detail && typeof detail === "object" ? (detail as ErrorDetail) : null;
}

/** A readable message for an error from the draft and issue routes. */
export function describeInvoiceError(err: unknown, fallback: string): string {
  const detail = errorDetail(err);
  switch (detail?.code) {
    case "company_info_incomplete": {
      const missing = (detail.missing || []).map((key) => COMPANY_INFO_LABELS[key] || key);
      return `Företagsuppgifterna räcker inte för en faktura. Saknas: ${missing.join(", ")}. Fyll i dem under Inställningar.`;
    }
    case "number_taken":
      return `Fakturanummer ${detail.invoice_number ?? ""} är redan använt. Välj ett annat nummer.`;
    case "period_locked":
      return `Perioden för fakturadatumet är låst${detail.locked_by ? ` (av ${detail.locked_by})` : ""}. Välj ett datum i en öppen period eller be en människa låsa upp den.`;
    case "period_not_found":
      return "Det finns ingen räkenskapsperiod för fakturadatumet.";
    case "human_only":
      return "Bara en inloggad användare kan utfärda fakturor. Logga in och försök igen.";
    case "draft_already_issued":
      return "Utkastet är redan utfärdat.";
    case "draft_rejected":
      return "Utkastet är avvisat och kan inte utfärdas.";
    case "draft_not_found":
      return "Fakturautkastet hittades inte.";
    case "draft_in_thread":
      // SPEC-fakturering-f1.md §4.3: the draft behind a pending card changes
      // only through the thread.
      return "Förslaget väntar i Fakturerings chatt. Be agenten ändra det där.";
    case "invoice_number_missing":
      return "Ange ett fakturanummer.";
    case "number_is_date":
      return "Fakturanumret ser ut som ett datum. Använd ett löpnummer, t.ex. 2026-1.";
    case "invalid_invoice_number":
      return "Fakturanumret får bara innehålla bokstäver, siffror och bindestreck (högst 32 tecken).";
    case "customer_address_missing":
      return "Ange kundens adress.";
    case "delivery_date_missing":
      return "Ange leveransdatum (från och till) eller leveransmånad.";
    case "missing_rows":
      return "Utkastet saknar fakturarader.";
    case "pdf_not_stored":
      return "Fakturan har ingen sparad PDF.";
    case "pdf_file_missing":
      return "Den sparade PDF-filen saknas på servern.";
  }
  if (detail?.error) return detail.details ? `${detail.error}: ${detail.details}` : detail.error;
  const raw = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof raw === "string") return raw;
  return fallback;
}

/**
 * A quantity as typed, with comma or point, normalised for the backend
 * ("7,5" -> "7.5"). The backend checks it: positive, at most two decimals.
 */
export function normaliseQuantity(value: string | number | null | undefined): string {
  return String(value ?? "").trim().replace(/\s/g, "").replace(",", ".");
}

/** A quantity from the backend shown the Swedish way (7.5 -> "7,5"). */
export function formatQuantity(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "";
  return String(value).replace(".", ",");
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Download an invoice's PDF: the one stored at issue when there is one,
 * else (an invoice from before F0) the rendering export of today's data.
 */
export async function downloadInvoicePdf(invoice: {
  id: string;
  invoice_number?: string | number | null;
  pdf_url?: string | null;
}): Promise<void> {
  const fallbackName = `faktura-${invoice.invoice_number ?? invoice.id}.pdf`;
  if (invoice.pdf_url) {
    const { blob, filename } = await api.getInvoicePdf(invoice.id);
    saveBlob(blob, filename || fallbackName);
    return;
  }
  const blob = await api.getPdfExport(`/api/v1/export/pdf/invoice/${invoice.id}`);
  saveBlob(blob, fallbackName);
}
