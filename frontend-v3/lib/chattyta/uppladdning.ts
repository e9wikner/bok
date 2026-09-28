/**
 * Filchipets logik för `ChattFalt/drop` (modul `flode-underlag`, FU19,
 * SPEC-flode-underlag.md §10.1–§10.3).
 *
 * Ren logik: ett chip per släppt fil, i tre lägen — `laddar` (`laddar
 * upp…`), `klar` och `fel` med orsak. Komponenten (`ChattFalt`) håller
 * listan; här bor bara vad ett chip ÄR och vad som följer med vid `↵`.
 *
 * Klienten läser inga filer och räknar inget (§10.3): ingen förhandsvisning,
 * ingen OCR, inget base64. Den kopplar heller ingenting — en uppladdning
 * gör en källa i intagskön, och vad källan hör till avgörs i tråden.
 */

import axios from "axios";
import { laddaUppUnderlag } from "@/lib/chattyta/api";

/**
 * Spegling av `IntakeService.ALLOWED_MIME_TYPES` (`services/intake.py`).
 * Den finns bara för att kunna säga nej INNAN uppladdningen; servern avgör
 * ändå, och ett `400 unsupported_mime_type` blir samma orsak här. Ändras
 * listan där ska den ändras här — `uppladdning.test.ts` håller dem lika.
 */
export const TILLATNA_TYPER: ReadonlySet<string> = new Set([
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
  "application/pdf",
]);

/** Spegling av `IntakeService.MAX_FILE_SIZE` (`services/intake.py`), 10 MiB. */
export const MAX_STORLEK_BYTE = 10 * 1024 * 1024;

export const ORSAK_TYP = "filtypen stöds inte · pdf, jpg, png, gif eller webp";
export const ORSAK_STORLEK = "filen är för stor · högst 10 MB";

export type ChipLage = "laddar" | "klar" | "fel";

export interface FilChip {
  /** Klientens nyckel för chipet. Inte källans id: det finns först efter svaret. */
  nyckel: string;
  namn: string;
  /** Byte, ur `File.size`. Visas med `filMeta`, räknas inte på. */
  storlek: number;
  lage: ChipLage;
  /** `intake_sources.id` när chipet är `klar`, annars `null`. */
  id: string | null;
  /** `409 duplicate_intake_source`: samma underlag fanns redan (§10.2 punkt 2). */
  dubblett: boolean;
  /** Varför, när chipet är `fel`. */
  orsak: string | null;
}

export type Uppladdningsutfall =
  | { lage: "klar"; id: string; dubblett: boolean }
  | { lage: "fel"; orsak: string };

/** `null` om filen får laddas upp, annars orsaken. Samma regler som servern. */
export function kontrolleraFil(fil: { type: string; size: number }): string | null {
  if (!TILLATNA_TYPER.has(fil.type)) return ORSAK_TYP;
  if (fil.size > MAX_STORLEK_BYTE) return ORSAK_STORLEK;
  return null;
}

/** Chipet i det ögonblick filen släpps: `laddar`, eller `fel` direkt. */
export function nyttChip(fil: File, nyckel: string): FilChip {
  const orsak = kontrolleraFil(fil);
  return {
    nyckel,
    namn: fil.name,
    storlek: fil.size,
    lage: orsak === null ? "laddar" : "fel",
    id: null,
    dubblett: false,
    orsak,
  };
}

/** Vad chipet säger om sig självt. */
export function chipStatus(chip: FilChip): string {
  if (chip.lage === "laddar") return "laddar upp…";
  if (chip.lage === "fel") return `fel · ${chip.orsak ?? "okänt fel"}`;
  return chip.dubblett ? "klar · fanns redan" : "klar";
}

/** FastAPIs `HTTPException(detail={...})` → `{"detail": {...}}`; annars `null`. */
function feldetalj(fel: unknown): Record<string, unknown> | null {
  if (!axios.isAxiosError(fel)) return null;
  const detalj = (fel.response?.data as { detail?: unknown } | undefined)?.detail;
  return typeof detalj === "object" && detalj !== null ? (detalj as Record<string, unknown>) : null;
}

/**
 * Ladda upp EN fil och säg hur det gick. Kastar aldrig: varje utfall är ett
 * läge för chipet.
 *
 * `409 duplicate_intake_source` är inget fel (§10.2 punkt 2): samma kvitto
 * två gånger är samma underlag, och chipet får den befintliga källans id ur
 * `existing_id` (§7). Utan `existing_id` vet klienten inte vilken källa det
 * är — id:t läses inte ur `details`-strängen, som är text för människor.
 */
export async function laddaUppChip(fil: File): Promise<Uppladdningsutfall> {
  const nej = kontrolleraFil(fil);
  if (nej !== null) return { lage: "fel", orsak: nej };
  try {
    const kalla = await laddaUppUnderlag(fil);
    return { lage: "klar", id: kalla.id, dubblett: false };
  } catch (fel) {
    if (!axios.isAxiosError(fel)) return { lage: "fel", orsak: "uppladdningen misslyckades" };
    const status = fel.response?.status;
    if (status === undefined) return { lage: "fel", orsak: "uppladdningen misslyckades · inget svar från servern" };
    const detalj = feldetalj(fel);
    const kod = detalj?.code;
    if (status === 409 && kod === "duplicate_intake_source") {
      const befintlig = detalj?.existing_id;
      if (typeof befintlig === "string" && befintlig) {
        return { lage: "klar", id: befintlig, dubblett: true };
      }
      return { lage: "fel", orsak: "filen finns redan i intagskön" };
    }
    if (kod === "unsupported_mime_type") return { lage: "fel", orsak: ORSAK_TYP };
    if (kod === "file_too_large") return { lage: "fel", orsak: ORSAK_STORLEK };
    return { lage: "fel", orsak: `uppladdningen misslyckades · servern svarade ${status}` };
  }
}

/** Chipet efter svaret. */
export function medUtfall(chip: FilChip, utfall: Uppladdningsutfall): FilChip {
  return utfall.lage === "klar"
    ? { ...chip, lage: "klar", id: utfall.id, dubblett: utfall.dubblett, orsak: null }
    : { ...chip, lage: "fel", id: null, dubblett: false, orsak: utfall.orsak };
}

/**
 * `attachments` vid `↵`: de klara chipens id:n, i chipens ordning, en gång
 * var. Ett chip med fel följer inte med (§10.2 punkt 4).
 */
export function bilagor(chips: readonly FilChip[]): string[] {
  const ids: string[] = [];
  for (const c of chips) if (c.lage === "klar" && c.id !== null && !ids.includes(c.id)) ids.push(c.id);
  return ids;
}

export const laddarUpp = (chips: readonly FilChip[]): boolean => chips.some((c) => c.lage === "laddar");

/**
 * `↵` går när inget chip laddar upp (§10.2 punkt 3) och det finns något att
 * skicka: text, eller minst ett klart chip — utan text skickas meddelandet
 * ändå (D8).
 */
export function kanSkicka(text: string, chips: readonly FilChip[]): boolean {
  if (laddarUpp(chips)) return false;
  return text.trim() !== "" || bilagor(chips).length > 0;
}
