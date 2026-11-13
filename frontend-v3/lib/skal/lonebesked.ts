/**
 * Lönebesked (modul `skal`, vyn `betala.lonebesked`).
 *
 * Årets lönekörningar med sina lönebesked: PDF:en att skicka, en markering
 * när den är skickad, och en körning som ännu inte har bokförts kan tas
 * bort. Under varje månad står arbetsgivardeklarationens fält, att skriva
 * in i Skatteverkets e-tjänst. Bokföringen sker i Löner (kortet) och AGI:n
 * bokförs av agenten ur kvittensen. Samma endpoints som den gamla
 * /payroll-sidan (`api/routes/payroll.py`).
 */

import apiClient from "@/lib/api";
import type { AgiDeclaration } from "@/lib/api";
import type { Lonebesked, Lonekorning } from "@/lib/skal/betala";
import type { VyLage } from "@/lib/skal/vydata";

export const agiNyckel = (ar: number, manad: number) => ["payroll", "agi", ar, manad] as const;

export const lonebeskedApi = {
  taBortKorning: async (id: string): Promise<void> => {
    await apiClient.delete(`/api/v1/payroll/runs/${id}`);
  },
  markeraSkickat: async (id: string): Promise<void> => {
    await apiClient.post(`/api/v1/payroll/payslips/${id}/mark-sent`);
  },
  agi: async (ar: number, manad: number): Promise<AgiDeclaration> => {
    const { data } = await apiClient.get<AgiDeclaration>(`/api/v1/payroll/agi/${ar}/${manad}`);
    return data;
  },
};

/** PDF:en som sparades när lönebeskedet skapades, annars en nyss renderad. */
export function pdfVag(b: Lonebesked): string {
  return b.pdf_stored === false ? `/api/v1/export/pdf/payslip/${b.id}` : `/api/v1/payroll/payslips/${b.id}/pdf`;
}

const MANADER = [
  "januari", "februari", "mars", "april", "maj", "juni",
  "juli", "augusti", "september", "oktober", "november", "december",
];

export function manadText(ar: number, manad: number): string {
  return `${MANADER[manad - 1] ?? manad} ${ar}`;
}

/** En körning kan tas bort så länge inget av dess lönebesked är bokfört. */
export function kanTasBort(k: Lonekorning): boolean {
  return !(k.payslips ?? []).some((b) => b.voucher_id);
}

/** Lönebeskedets läge, i ord. */
export function beskedLage(b: Lonebesked): string {
  if (b.voucher_id) return b.pdf_sent_at || b.status === "sent" ? "skickat och bokfört" : "bokfört";
  if (b.status === "sent" || b.pdf_sent_at) return "skickat";
  return "inte skickat";
}

export function lonebeskedStatus(
  korningar: Lonekorning[] | undefined,
  isError: boolean,
  arId: string | null | undefined
): { text: string; lage: VyLage } {
  if (arId === null) return { text: "inget räkenskapsår", lage: "tomt" };
  if (isError) return { text: "kunde inte läsas", lage: "fel" };
  if (!korningar) return { text: "hämtar…", lage: "normal" };
  const besked = korningar.flatMap((k) => k.payslips ?? []);
  if (besked.length === 0) return { text: "inga lönebesked", lage: "tomt" };
  const oskickade = besked.filter((b) => beskedLage(b) === "inte skickat").length;
  if (oskickade > 0) return { text: `${oskickade} inte skickat`, lage: "vantar" };
  return { text: `${besked.length} lönebesked`, lage: "normal" };
}
