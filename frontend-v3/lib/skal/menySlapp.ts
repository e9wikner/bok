/**
 * Menyn som släppyta: medan en fil dras över fönstret byter sidomenyn
 * innehåll mot dropzonens två mappar, och ett släpp lägger filen där
 * (`POST /api/v1/intake/dropzone/files`), som i Underlag-vyn.
 *
 * Mappen svarar bara på en fråga: är det ett utlägg? Vad filen i övrigt är
 * avgör filändelsen på servern (`services/dropzone.py`). `Utlägg/` tar inte
 * kontoutdrag eller SIE4-filer; de går till `Underlag/` i stället för att
 * hamna i `_Problem/`.
 */

/** Mapparna finns alltid (`TYPE_FOLDERS`); servern matchar namnet oavsett NFC/NFD. */
export const UNDERLAG = "Underlag";
export const UTLAGG = "Utlägg";

export type SlappMal = "underlag" | "utlagg";

export const mappFor = (mal: SlappMal): string => (mal === "utlagg" ? UTLAGG : UNDERLAG);

export const harFiler = (dt: DataTransfer | null | undefined): boolean =>
  !!dt && Array.from(dt.types ?? []).includes("Files");

/** Ändelserna `Utlägg/` inte tar (`services/dropzone.py::SIE4_EXTENSIONS` och `.csv`). */
const INTE_UTLAGG = [".csv", ".se", ".si", ".sie", ".sie4"];

export const horInteTillUtlagg = (namn: string): boolean => {
  const n = namn.toLowerCase();
  return INTE_UTLAGG.some((e) => n.endsWith(e));
};

const CSV_TYPER = new Set(["text/csv", "application/csv", "text/comma-separated-values", "application/vnd.ms-excel"]);

/**
 * Kan dragningen släppas på Utlägg? Under dragningen syns bara MIME-typen,
 * inte filnamnet, så en CSV känns igen här men en SIE-fil (ofta utan typ)
 * först vid släppet, av `fordela`.
 */
export function utlaggTarEmot(dt: DataTransfer | null | undefined): boolean {
  if (!dt?.items) return true;
  return !Array.from(dt.items).some((i) => i.kind === "file" && CSV_TYPER.has(i.type));
}

export interface Grupp {
  folder: string;
  filer: File[];
}

/** Filerna per mapp. Släppta på Utlägg går kontoutdrag och SIE4 till Underlag. */
export function fordela(mal: SlappMal, filer: readonly File[]): { grupper: Grupp[]; flyttade: number } {
  if (mal === "underlag") return { grupper: filer.length ? [{ folder: UNDERLAG, filer: [...filer] }] : [], flyttade: 0 };
  const flytt = filer.filter((f) => horInteTillUtlagg(f.name));
  const kvar = filer.filter((f) => !horInteTillUtlagg(f.name));
  const grupper: Grupp[] = [];
  if (kvar.length) grupper.push({ folder: UTLAGG, filer: kvar });
  if (flytt.length) grupper.push({ folder: UNDERLAG, filer: flytt });
  return { grupper, flyttade: flytt.length };
}

export interface Notis {
  laddar: boolean;
  /** Antal filer lagda per mapp, i den ordning de lades. */
  lagda: { folder: string; antal: number }[];
  fel: { namn: string; text: string }[];
  /** Filer släppta på Utlägg som gick till Underlag. */
  flyttade: number;
}

const filer = (n: number) => `${n} ${n === 1 ? "fil" : "filer"}`;

/** Notisens rader, i ordning: vad som lades var, vad som flyttades, vad som avvisades. */
export function notisRader(n: Notis, antalSlappta: number): string[] {
  if (n.laddar) return [`Lägger ${filer(antalSlappta)} i dropzonen…`];
  const rader = n.lagda.map((l) => `${filer(l.antal)} ${l.antal === 1 ? "lagd" : "lagda"} i ${l.folder}`);
  if (n.flyttade > 0) {
    rader.push(`${filer(n.flyttade)} gick till ${UNDERLAG}: ${UTLAGG} tar inte kontoutdrag eller SIE4`);
  }
  for (const f of n.fel) rader.push(`${f.namn}: ${f.text}`);
  return rader;
}
