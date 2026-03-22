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

export function formatNumber(num: number): string {
  return new Intl.NumberFormat("sv-SE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);
}
