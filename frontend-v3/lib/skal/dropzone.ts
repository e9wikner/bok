/**
 * Dropzonen i webben (modul `skal`, vyn `bocker.dropzone`).
 *
 * Samma mappar som SMB-utdelningen `Bokforing`: en fil som släpps här skrivs
 * i den mappen (`POST /api/v1/intake/dropzone/files`) och läses in av
 * mappskannern vid nästa varv, precis som en fil som kopierats dit i Finder.
 * Webben läser in ingenting själv. `services/dropzone_upload.py`.
 */

import apiClient from "@/lib/api";
import type { DropzoneStatus } from "@/lib/api";
import type { VyLage } from "@/lib/skal/vydata";

export type MalTyp = "voucher_source" | "bank_input" | "sie4_import";

export interface DropzoneMal {
  /** Sökvägen i dropzonen, t.ex. `Kvitton`. Målets identitet. */
  folder: string;
  label: string;
  kind: MalTyp;
  source_type: string | null;
  account_code: string | null;
  account_name: string | null;
  pending_count: number;
}

export interface DropzoneFil {
  folder: string;
  filename: string;
  size_bytes: number;
  modified_at: string;
}

export interface DropzoneProblem extends DropzoneFil {
  reason: string | null;
}

export interface DropzoneOversikt {
  enabled: boolean;
  quiet_seconds: number;
  scan_interval_seconds: number;
  max_bytes: number;
  targets: DropzoneMal[];
  pending: DropzoneFil[];
  problems: DropzoneProblem[];
  ingested: DropzoneFil[];
  status: DropzoneStatus;
}

/** En fil i ett släpp: lagd i mappen, eller avvisad med serverns skäl. */
export interface SlapptResultat {
  ok: boolean;
  original_filename: string;
  folder?: string;
  filename?: string;
  size_bytes?: number;
  error?: string;
  code?: string;
}

export const DROPZONE_NYCKEL = ["skal", "dropzone"] as const;

export const dropzoneApi = {
  getOversikt: async (): Promise<DropzoneOversikt> => {
    const { data } = await apiClient.get("/api/v1/intake/dropzone");
    // Ett svar utan mapplistan är ett fel, inte en tom dropzone.
    if (!data || !Array.isArray(data.targets) || !Array.isArray(data.pending)) {
      throw new Error("Oväntat svar från /intake/dropzone");
    }
    return data;
  },
  /** Alla filer i ett anrop; varje fil lyckas eller avvisas för sig. */
  slapp: async (folder: string, filer: File[]): Promise<SlapptResultat[]> => {
    const form = new FormData();
    form.append("folder", folder);
    for (const fil of filer) form.append("files", fil);
    const { data } = await apiClient.post("/api/v1/intake/dropzone/files", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data.results;
  },
};

/** Serverns felmeddelande ur ett axios-fel, annars en allmän mening. */
export function felText(fel: unknown): string {
  const detalj = (fel as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (detalj && typeof detalj === "object" && "error" in detalj) {
    return String((detalj as { error: unknown }).error);
  }
  if (typeof detalj === "string") return detalj;
  return "Filen kunde inte läggas i dropzonen.";
}

/**
 * Har skannern stannat? Samma regel som intagssidan: inget varv på tre
 * intervall. En stoppad skanner och en nyss släppt fil ser likadana ut i
 * mappen, så det måste sägas.
 */
export function harStannat(oversikt: DropzoneOversikt, nu: number = Date.now()): boolean {
  if (!oversikt.enabled) return false;
  const senast = oversikt.status.last_scan_at ? Date.parse(oversikt.status.last_scan_at) : NaN;
  if (Number.isNaN(senast)) return true;
  return nu - senast > oversikt.scan_interval_seconds * 3 * 1000;
}

/** Vyns statusrad, i headern och i vyn (samma fält). */
export function dropzoneStatus(
  oversikt: DropzoneOversikt | undefined,
  isError: boolean,
  nu: number = Date.now()
): { text: string; lage: VyLage } {
  if (isError) return { text: "kunde inte läsas", lage: "fel" };
  if (!oversikt) return { text: "hämtar", lage: "pagaende" };
  if (!oversikt.enabled) return { text: "avstängd på servern", lage: "fel" };
  if (harStannat(oversikt, nu)) return { text: "hämtningen har stannat", lage: "fel" };
  if (oversikt.problems.length > 0) {
    return { text: `${oversikt.problems.length} i _Problem`, lage: "vantar" };
  }
  if (oversikt.pending.length > 0) {
    return { text: `${oversikt.pending.length} väntar på hämtning`, lage: "pagaende" };
  }
  return { text: "inget väntar", lage: "normal" };
}

/** Vad mappen gör med en fil, i en mening. */
export function malBeskrivning(mal: DropzoneMal): string {
  if (mal.kind === "bank_input") return "kontoutdrag (CSV), kontokoden först i filnamnet: 1930 oktober.csv";
  if (mal.kind === "sie4_import") return "hel årsexport, bokförs direkt";
  return MAPPTYP[mal.source_type ?? ""] ?? "ingen typ, agenten avgör";
}

const MAPPTYP: Readonly<Record<string, string>> = {
  receipt: "kvitton",
  supplier_invoice: "leverantörsfakturor",
  customer_invoice: "kundfakturor",
  reimbursement: "utlägg",
  other: "övrigt underlag",
};

/** Mapparna som i utdelningen: översta nivån, med undermapparna under sin förälder. */
export interface Mappnod {
  /** Mappens namn på översta nivån, t.ex. `Kontoutdrag`. */
  namn: string;
  /** Själva mappen, när filer kan läggas direkt i den. */
  mal?: DropzoneMal;
  undermappar: { namn: string; mal: DropzoneMal }[];
}

export function mapptrad(mal: readonly DropzoneMal[]): Mappnod[] {
  const noder: Mappnod[] = [];
  for (const m of mal) {
    const [topp, ...rest] = m.folder.split("/");
    let nod = noder.find((n) => n.namn === topp);
    if (!nod) {
      nod = { namn: topp, undermappar: [] };
      noder.push(nod);
    }
    if (rest.length === 0) nod.mal = m;
    else nod.undermappar.push({ namn: rest.join("/"), mal: m });
  }
  return noder;
}

/** Filtyperna filväljaren erbjuder för ett mål. Servern avgör ändå. */
export function malAccept(mal: DropzoneMal | undefined): string | undefined {
  if (!mal) return undefined;
  if (mal.kind === "sie4_import") return ".se,.si,.sie,.sie4";
  if (mal.kind === "bank_input") return ".csv,text/csv";
  return "application/pdf,image/jpeg,image/png,image/gif,image/webp";
}

export function storlek(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} kB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}

export function tidpunkt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("sv-SE", { dateStyle: "short", timeStyle: "short" });
}
