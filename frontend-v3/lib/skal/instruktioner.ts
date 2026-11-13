/**
 * Agentens instruktioner (modul `skal`, vyerna `bocker.instruktioner` och
 * `betala.instruktioner`).
 *
 * Företagets egna regler, som agenten läser före systeminstruktionerna i
 * varje pass: för bokföringen i Böcker, för faktureringen i Betala. Varje
 * sparning är en ny version; de gamla står kvar. Systeminstruktionerna
 * (`docs/to_agent/`) visas men kan inte ändras här. Samma endpoints som den
 * gamla /learning-sidan (`api/routes/agent_instructions.py`).
 */

import apiClient from "@/lib/api";
import type { VyLage } from "@/lib/skal/vydata";

export type Omfang = "accounting" | "invoicing";

export const instruktionNyckel = (omfang: Omfang) => ["skal", "instruktioner", omfang] as const;
export const KORRIGERINGAR_NYCKEL = ["skal", "korrigeringar"] as const;

export interface Version {
  version_id: string;
  version: number;
  content_markdown: string;
  change_summary: string | null;
  created_by: string;
  created_at: string;
}

export interface Instruktioner {
  /** Företagets aktiva version, eller null innan någon har sparats. */
  foretaget: Version | null;
  system: string;
  versioner: Version[];
}

export interface Korrigering {
  id: string;
  correction_reason: string | null;
  corrected_by: string;
  created_at: string;
  original: string | null;
  rattelse: string | null;
}

interface Ver {
  series?: string;
  number?: number | null;
}

const nummer = (v: Ver | null | undefined): string | null =>
  v && v.series && typeof v.number === "number" ? `${v.series}-${v.number}` : null;

export const instruktionerApi = {
  hamta: async (omfang: Omfang): Promise<Instruktioner> => {
    const [aktiv, versioner] = await Promise.all([
      apiClient.get<{ company?: Version | null; system?: { content_markdown?: string } }>(
        `/api/v1/agent-instructions/${omfang}`
      ),
      apiClient.get<{ versions?: Version[] }>(`/api/v1/agent-instructions/${omfang}/versions`),
    ]);
    const foretaget = aktiv.data?.company;
    return {
      foretaget: foretaget && foretaget.version_id ? foretaget : null,
      system: aktiv.data?.system?.content_markdown ?? "",
      versioner: versioner.data?.versions ?? [],
    };
  },

  spara: async (omfang: Omfang, text: string, sammanfattning: string): Promise<Version> => {
    const { data } = await apiClient.put<Version>(`/api/v1/agent-instructions/${omfang}`, {
      content_markdown: text,
      change_summary: sammanfattning.trim() || null,
    });
    return data;
  },

  korrigeringar: async (): Promise<Korrigering[]> => {
    const { data } = await apiClient.get<{
      corrections?: (Omit<Korrigering, "original" | "rattelse"> & { original_voucher?: Ver; correction_voucher?: Ver })[];
    }>("/api/v1/accounting-corrections", { params: { limit: 25 } });
    return (data?.corrections ?? []).map((k) => ({
      id: k.id,
      correction_reason: k.correction_reason,
      corrected_by: k.corrected_by,
      created_at: k.created_at,
      original: nummer(k.original_voucher),
      rattelse: nummer(k.correction_voucher),
    }));
  },
};

export function instruktionStatus(data: Instruktioner | undefined, isError: boolean): { text: string; lage: VyLage } {
  if (isError) return { text: "kunde inte läsas", lage: "fel" };
  if (!data) return { text: "hämtar…", lage: "normal" };
  if (!data.foretaget || !data.foretaget.content_markdown.trim()) return { text: "inga egna regler", lage: "tomt" };
  return { text: `version ${data.foretaget.version}`, lage: "normal" };
}

/** "A-12 rättad med B-3". */
export function korrigeringText(k: Korrigering): string {
  if (k.original && k.rattelse) return `${k.original} rättad med ${k.rattelse}`;
  if (k.original) return `${k.original} rättad`;
  return "Rättelse";
}
