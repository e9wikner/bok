import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Amounts from API are in öre (1/100 SEK)
export function formatCurrency(amountInOre: number): string {
  return new Intl.NumberFormat("sv-SE", {
    style: "currency",
    currency: "SEK",
    minimumFractionDigits: 2,
  }).format(amountInOre / 100);
}

export function formatDate(dateStr: string): string {
  if (!dateStr) return "-";
  // Handle ISO date strings like "2026-03-20" directly
  const parts = dateStr.split("T")[0].split("-");
  if (parts.length === 3) {
    return `${parts[0]}-${parts[1]}-${parts[2]}`;
  }
  return dateStr;
}

/**
 * Verifikationsnummer för visning: `A12`, eller `A-12` med `avgransare`.
 * Ett utkast har inget nummer — det sätts vid postning (SPEC-flode-verifikationer
 * §4.3) — och visas då som `Utkast`. Aldrig `A-null`, `NaN` eller tomt.
 */
export function formatVerifikationsnummer(
  nummer: number | null | undefined,
  serie?: string | null,
  avgransare = ""
): string {
  if (typeof nummer !== "number" || !Number.isInteger(nummer)) return "Utkast";
  return `${serie ?? ""}${serie ? avgransare : ""}${nummer}`;
}

export function formatNumber(num: number): string {
  return new Intl.NumberFormat("sv-SE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);
}

export function formatFiscalYearLabel(
  fiscalYear?: { start_date?: string | null; end_date?: string | null } | null
): string {
  const start = fiscalYear?.start_date;
  const end = fiscalYear?.end_date;
  if (!start || !end) return "";

  const startYear = start.slice(0, 4);
  const endYear = end.slice(0, 4);
  return startYear === endYear ? startYear : `${startYear}-${endYear}`;
}
