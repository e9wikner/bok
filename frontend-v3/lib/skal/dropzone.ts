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

/**
 * Vad som blev av en inläst fil (`_ingested_outcome` i
 * `services/dropzone_upload.py`). Filen hittas i böckerna på sin sha256;
 * `null` när den inte finns där (en SIE-fil, eller inläst före en
 * nollställning av databasen).
 */
export type DropzoneUtfall =
  | {
      kind: "underlag";
      source_id: string;
      status: string;
      vouchers: { id: string; series: string; number: number | null; date: string }[];
      decision: { id: string; view_key: string; title: string } | null;
      warning: string | null;
    }
  | {
      kind: "statement";
      status: string;
      imported_count: number;
      skipped_count: number;
      parse_error: string | null;
    };

export interface DropzoneInlast extends DropzoneFil {
  /** Saknas från en server från före fältet. */
  outcome?: DropzoneUtfall | null;
}

/** En fil som väntar på skannern. */
export interface DropzoneVantande extends DropzoneFil {
  /** Felet skannerns senaste försök med filen gav; filen ligger kvar och prövas igen. */
  error?: string | null;
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
  pending: DropzoneVantande[];
  problems: DropzoneProblem[];
  ingested: DropzoneInlast[];
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

/**
 * När en väntande fil läses in. Skannern tar en fil som legat orörd i
 * `quiet_seconds`, vid nästa varv; har det gått längre än så plus två varv
 * säger raden det, i stället för att lova en tid som redan passerat.
 */
export function vantarText(
  fil: DropzoneVantande,
  oversikt: Pick<DropzoneOversikt, "quiet_seconds" | "scan_interval_seconds">,
  nu: number = Date.now()
): { text: string; sen: boolean } {
  if (fil.error) return { text: `kunde inte läsas in, prövas igen · ${fil.error}`, sen: true };
  const lagd = Date.parse(fil.modified_at);
  if (Number.isNaN(lagd)) return { text: "väntar på hämtning", sen: false };
  const vantat = Math.max(0, Math.round((nu - lagd) / 1000));
  const klar = oversikt.quiet_seconds + oversikt.scan_interval_seconds;
  if (vantat > klar + oversikt.scan_interval_seconds * 2) {
    return { text: `har väntat ${langd(vantat)}, längre än väntat`, sen: true };
  }
  const kvar = klar - vantat;
  return {
    text: `lagd för ${langd(vantat)} sedan · ${kvar > 0 ? `läses in inom ~${langd(kvar)}` : "läses in vid nästa varv"}`,
    sen: false,
  };
}

function langd(sekunder: number): string {
  if (sekunder < 60) return `${sekunder} s`;
  const min = Math.round(sekunder / 60);
  if (min < 60) return `${min} min`;
  const tim = Math.round(min / 60);
  return tim < 48 ? `${tim} h` : `${Math.round(tim / 24)} dagar`;
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

/**
 * En inläst fils läge, i en mening: bokförd, väntar på ett beslut, eller
 * hos agenten. `ton` färgar raden som de andra listorna: grönt bara när det
 * står i böckerna, gult när det väntar på människan.
 */
export function utfallText(utfall: DropzoneUtfall | null | undefined): {
  text: string;
  ton: "normal" | "klar" | "vantar" | "fel";
} {
  if (!utfall) return { text: "inläst", ton: "normal" };
  if (utfall.kind === "statement") {
    if (utfall.parse_error) return { text: `kontoutdraget kunde inte läsas: ${utfall.parse_error}`, ton: "fel" };
    const hoppade = utfall.skipped_count > 0 ? `, ${utfall.skipped_count} fanns redan` : "";
    return { text: `kontoutdrag · ${utfall.imported_count} transaktioner inlästa${hoppade}`, ton: "klar" };
  }
  if (utfall.vouchers.length > 0) {
    const nummer = utfall.vouchers.map((v) => (v.number === null ? "utkast" : `${v.series}${v.number}`));
    return { text: `bokförd som ${nummer.join(", ")}`, ton: "klar" };
  }
  if (utfall.decision) return { text: `väntar på ditt beslut: ${utfall.decision.title}`, ton: "vantar" };
  if (utfall.warning) return { text: utfall.warning, ton: "vantar" };
  switch (utfall.status) {
    case "pending":
    case "processing":
      return { text: "agenten bokför den", ton: "normal" };
    case "skipped":
      return { text: "avfärdad, inte bokförd", ton: "normal" };
    case "processed":
      return { text: "behandlad, ingen verifikation", ton: "normal" };
    default:
      return { text: utfall.status, ton: "normal" };
  }
}
