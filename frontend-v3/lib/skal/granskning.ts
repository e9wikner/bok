/**
 * Granskningen (modul `skal`, vyn `bokslut.granskning`).
 *
 * En extern agent granskar ett räkenskapsår och laddar upp en
 * granskningsrapport (`docs/granskning.md`). Här läses rapporterna, och här
 * räknas det vyn visar: anmärkningarna i allvarlighetsordning, beloppen i
 * kronor och täckningen, alltså vilka verifikationer som fick en anmärkning
 * och av hur många granskare. Bara läsning: en rapport ändras aldrig, en ny
 * ersätter den.
 *
 * API-svaren läses genom `som*`-funktionerna nedan, så att ett fältnamn som
 * servern byter bara behöver rättas på ett ställe.
 */

import apiClient from "@/lib/api";
import { formatBelopp } from "@/lib/skal/format";
import type { VyLage } from "@/lib/skal/vydata";

// ─── Typerna vyn arbetar med ──────────────────────────────────────────────

export type Allvarlighet = "material" | "should_fix" | "observation";

export const ALLVARLIGHETER: readonly Allvarlighet[] = ["material", "should_fix", "observation"];

export const ALLVARLIGHET_TEXT: Record<Allvarlighet, string> = {
  material: "Väsentlig",
  should_fix: "Bör rättas",
  observation: "Iakttagelse",
};

export type Antal = Record<Allvarlighet, number>;

export interface Rapportrad {
  id: string;
  fiscal_year_id: string;
  reviewer_agent: string;
  reviewer_model: string;
  instruction_sha256: string;
  /** Rapporten gjordes mot en annan version av instruktionen än den som gäller nu. */
  instruction_outdated: boolean;
  uploaded_by: string;
  uploaded_at: string;
  counts: Antal;
}

export interface AnmarkningsVerifikation {
  id: string;
  /** Serie och nummer, t.ex. "A12". */
  number: string;
  date: string;
}

export interface Anmarkning {
  id: string;
  position: number;
  severity: Allvarlighet;
  area: string;
  title: string;
  description: string;
  rule: string | null;
  amount_ore: number | null;
  suggested_correction: string | null;
  vouchers: AnmarkningsVerifikation[];
}

export interface Rapport extends Rapportrad {
  summary_markdown: string;
  examined_voucher_count: number;
  findings: Anmarkning[];
}

export interface Anmarkare {
  report_id: string;
  reviewer_agent: string;
  reviewer_model: string;
  severity: Allvarlighet;
}

export interface Tackningsrad {
  voucher_id: string;
  number: string;
  date: string;
  description: string;
  examined_by_count: number;
  flagged_by: Anmarkare[];
}

export interface Tackning {
  vouchers: Tackningsrad[];
  report_count: number;
}

// ─── API-svaren → typerna ─────────────────────────────────────────────────

type Rått = Record<string, unknown>;

const str = (v: unknown, standard = ""): string => (typeof v === "string" ? v : v == null ? standard : String(v));
const tal = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const valfriText = (v: unknown): string | null => (typeof v === "string" && v.trim() !== "" ? v : null);
const lista = (v: unknown): Rått[] => (Array.isArray(v) ? (v as Rått[]) : []);

/** En okänd allvarlighet räknas som den lindrigaste, hellre än att raden försvinner. */
export function somAllvarlighet(v: unknown): Allvarlighet {
  return ALLVARLIGHETER.includes(v as Allvarlighet) ? (v as Allvarlighet) : "observation";
}

function somAntal(v: unknown): Antal {
  const r = (v ?? {}) as Rått;
  return { material: tal(r.material), should_fix: tal(r.should_fix), observation: tal(r.observation) };
}

/** Verifikationens nummer: serverns `voucher_number` ("A-12"), annars serie och nummer. */
function somVerNummer(v: Rått): string {
  const vn = valfriText(v.voucher_number);
  if (vn) return vn;
  return `${str(v.series)}${str(v.number)}`;
}

export function somRapportrad(r: Rått): Rapportrad {
  // Servern skickar granskaren som `reviewer: {agent, model}`.
  const granskare = (r.reviewer ?? {}) as Rått;
  return {
    id: str(r.id),
    fiscal_year_id: str(r.fiscal_year_id),
    reviewer_agent: str(granskare.agent ?? r.reviewer_agent),
    reviewer_model: str(granskare.model ?? r.reviewer_model),
    instruction_sha256: str(r.instruction_sha256),
    instruction_outdated: r.instruction_outdated === true,
    uploaded_by: str(r.uploaded_by),
    uploaded_at: str(r.uploaded_at),
    counts: somAntal(r.counts),
  };
}

export function somAnmarkning(r: Rått): Anmarkning {
  return {
    id: str(r.id),
    position: tal(r.position),
    severity: somAllvarlighet(r.severity),
    area: str(r.area),
    title: str(r.title),
    description: str(r.description),
    rule: valfriText(r.rule),
    amount_ore: typeof r.amount_ore === "number" ? r.amount_ore : null,
    suggested_correction: valfriText(r.suggested_correction),
    vouchers: lista(r.vouchers).map((v) => ({ id: str(v.id), number: somVerNummer(v), date: str(v.date) })),
  };
}

export function somRapport(r: Rått): Rapport {
  return {
    ...somRapportrad(r),
    summary_markdown: str(r.summary_markdown),
    examined_voucher_count: tal(r.examined_voucher_count),
    findings: lista(r.findings).map(somAnmarkning),
  };
}

export function somTackning(r: Rått): Tackning {
  return {
    report_count: tal(r.report_count),
    vouchers: lista(r.vouchers).map((v) => ({
      voucher_id: str(v.id ?? v.voucher_id),
      number: somVerNummer(v),
      date: str(v.date),
      description: str(v.description),
      examined_by_count: tal(v.examined_count ?? v.examined_by_count),
      // En rapport kan ha flera anmärkningar på samma verifikation
      // (`severities`); den allvarligaste gäller.
      flagged_by: lista(v.flagged_by).map((f) => ({
        report_id: str(f.report_id),
        reviewer_agent: str(f.agent ?? f.reviewer_agent),
        reviewer_model: str(f.model ?? f.reviewer_model),
        severity:
          allvarligast((Array.isArray(f.severities) ? f.severities : []).map(somAllvarlighet)) ??
          somAllvarlighet(f.severity),
      })),
    })),
  };
}

// ─── Läsvägarna ───────────────────────────────────────────────────────────

export const GRANSKNING_NYCKEL = ["skal", "granskning"] as const;
export const rapporterNyckel = (arId: string) => [...GRANSKNING_NYCKEL, "rapporter", arId] as const;
export const rapportNyckel = (id: string) => [...GRANSKNING_NYCKEL, "rapport", id] as const;
export const tackningNyckel = (arId: string) => [...GRANSKNING_NYCKEL, "tackning", arId] as const;

export const INGANG_SOKVAG = "/api/v1/review/entrypoint";

/** Nyckeln står bara i `prompt`; den visas en gång och sparas ingenstans. */
export type GranskningsNyckel = { id: string; prompt: string; expires_at: string };

/** "14:05", nyckelns sista minut i lokal tid. */
export function giltigTillText(expiresAt: string): string {
  const t = new Date(expiresAt);
  if (Number.isNaN(t.getTime())) return "";
  return t.toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit" });
}

export const granskningApi = {
  rapporter: async (arId: string): Promise<Rapportrad[]> => {
    const { data } = await apiClient.get(`/api/v1/review/reports?fiscal_year_id=${encodeURIComponent(arId)}`);
    // `{ reports: [...] }`; en ren lista godtas också.
    const rader = Array.isArray(data) ? data : (data as Rått | null)?.reports;
    return lista(rader).map(somRapportrad);
  },
  rapport: async (id: string): Promise<Rapport> => {
    const { data } = await apiClient.get(`/api/v1/review/reports/${encodeURIComponent(id)}`);
    return somRapport((data ?? {}) as Rått);
  },
  /** En tillfällig granskningsnyckel och uppdraget att klistra in hos en agent. Bara en inloggad människa får en. */
  skapaNyckel: async (arId: string, ingang: string): Promise<GranskningsNyckel> => {
    const { data } = await apiClient.post("/api/v1/review/tokens", { fiscal_year_id: arId, entrypoint_url: ingang });
    const d = (data ?? {}) as Rått;
    return { id: String(d.id ?? ""), prompt: String(d.prompt ?? ""), expires_at: String(d.expires_at ?? "") };
  },
  aterkallaNyckel: async (id: string): Promise<void> => {
    await apiClient.post(`/api/v1/review/tokens/${encodeURIComponent(id)}/revoke`);
  },
  tackning: async (arId: string): Promise<Tackning> => {
    const { data } = await apiClient.get(`/api/v1/review/coverage?fiscal_year_id=${encodeURIComponent(arId)}`);
    return somTackning((data ?? {}) as Rått);
  },
};

/**
 * Ingångens fulla adress, som en agent kan pekas på. Samma bas som
 * `apiClient` använder; utan egen bas går anropen genom frontendens egen
 * adress (Next skickar `/api` vidare till servern).
 */
export function ingangUrl(bas: string | undefined, origin: string): string {
  const b = (bas && bas.trim() !== "" ? bas : origin).replace(/\/+$/, "");
  return `${b}${INGANG_SOKVAG}`;
}

// ─── Det vyn räknar ───────────────────────────────────────────────────────

const RANG: Record<Allvarlighet, number> = { material: 0, should_fix: 1, observation: 2 };

/** Anmärkningarna i allvarlighetsordning; inom samma allvarlighet rapportens egen ordning. */
export function sorteraAnmarkningar(findings: readonly Anmarkning[]): Anmarkning[] {
  return [...findings].sort((a, b) => RANG[a.severity] - RANG[b.severity] || a.position - b.position);
}

/** Den allvarligaste av flera, eller `null` för ingen. */
export function allvarligast(lista: readonly Allvarlighet[]): Allvarlighet | null {
  return lista.reduce<Allvarlighet | null>((v, s) => (v === null || RANG[s] < RANG[v] ? s : v), null);
}

/** Belopp i öre → "1 250 kr" eller "1 250,50 kr". */
export function beloppKr(ore: number | null | undefined): string | null {
  if (typeof ore !== "number" || !Number.isFinite(ore)) return null;
  return `${formatBelopp(ore, ore % 100 === 0 ? 0 : 2)} kr`;
}

/**
 * Uppladdningstiden som "2026-11-20 14:32" i lokal tid. Servern skriver
 * SQLites `CURRENT_TIMESTAMP`, som är UTC utan zon.
 */
export function uppladdadText(ts: string): string {
  const s = ts.trim();
  if (!s) return "";
  const utanZon = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s);
  const d = new Date(utanZon ? `${s.replace(" ", "T")}Z` : s);
  if (Number.isNaN(d.getTime())) return s.slice(0, 16);
  const tva = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${tva(d.getMonth() + 1)}-${tva(d.getDate())} ${tva(d.getHours())}:${tva(d.getMinutes())}`;
}

/** "2 väsentliga · 1 bör rättas · 3 iakttagelser", eller "inga anmärkningar". */
export function antalText(c: Antal): string {
  const delar: string[] = [];
  if (c.material) delar.push(`${c.material} ${c.material === 1 ? "väsentlig" : "väsentliga"}`);
  if (c.should_fix) delar.push(`${c.should_fix} bör rättas`);
  if (c.observation) delar.push(`${c.observation} ${c.observation === 1 ? "iakttagelse" : "iakttagelser"}`);
  return delar.length ? delar.join(" · ") : "inga anmärkningar";
}

/** "Claude Code · claude-opus-5-5". */
export function granskareText(agent: string, model: string): string {
  return [agent, model].filter((s) => s.trim() !== "").join(" · ") || "okänd granskare";
}

/** En granskare i täckningen, med sin allvarligaste anmärkning på verifikationen. */
export interface Granskare {
  nyckel: string;
  agent: string;
  model: string;
  severity: Allvarlighet;
}

/**
 * Granskarna som anmärkte på en verifikation, en gång var. En granskare är
 * agent och modell: två rapporter av samma modell är inte två oberoende
 * bedömningar. Allvarligast först.
 */
export function granskarePa(rad: Tackningsrad): Granskare[] {
  const per = new Map<string, Granskare>();
  for (const f of rad.flagged_by) {
    const nyckel = `${f.reviewer_agent}\u0000${f.reviewer_model}`;
    const forra = per.get(nyckel);
    if (!forra || RANG[f.severity] < RANG[forra.severity]) {
      per.set(nyckel, { nyckel, agent: f.reviewer_agent, model: f.reviewer_model, severity: f.severity });
    }
  }
  return [...per.values()].sort((a, b) => RANG[a.severity] - RANG[b.severity] || a.agent.localeCompare(b.agent, "sv"));
}

/**
 * Täckningens rader: bara verifikationer som minst en rapport anmärkte på.
 * Flest olika granskare först, eftersom en anmärkning som flera modeller
 * gjort oberoende av varandra väger tyngre. Sedan den allvarligaste
 * anmärkningen, och sist datum och nummer.
 */
export function tackningsrader(t: Tackning): (Tackningsrad & { granskare: Granskare[] })[] {
  return t.vouchers
    .map((v) => ({ ...v, granskare: granskarePa(v) }))
    .filter((v) => v.granskare.length > 0)
    .sort((a, b) => {
      const antal = b.granskare.length - a.granskare.length;
      if (antal) return antal;
      const rang = RANG[a.granskare[0].severity] - RANG[b.granskare[0].severity];
      if (rang) return rang;
      return a.date.localeCompare(b.date) || a.number.localeCompare(b.number, "sv", { numeric: true });
    });
}

export function granskningStatus(
  rapporter: readonly Rapportrad[] | undefined,
  isError: boolean,
  arId: string | null | undefined
): { text: string; lage: VyLage } {
  if (arId === null) return { text: "inget räkenskapsår", lage: "tomt" };
  if (isError) return { text: "kunde inte läsas", lage: "fel" };
  if (!rapporter) return { text: "hämtar", lage: "pagaende" };
  if (rapporter.length === 0) return { text: "ingen rapport", lage: "tomt" };
  const material = rapporter.reduce((s, r) => s + r.counts.material, 0);
  const text = `${rapporter.length} ${rapporter.length === 1 ? "rapport" : "rapporter"}`;
  if (material > 0) return { text: `${text} · ${material} ${material === 1 ? "väsentlig" : "väsentliga"}`, lage: "vantar" };
  return { text, lage: "normal" };
}

/** Rapporterna, senast uppladdade först. */
export function sorteraRapporter(rapporter: readonly Rapportrad[]): Rapportrad[] {
  return [...rapporter].sort((a, b) => b.uploaded_at.localeCompare(a.uploaded_at));
}

// ─── Var i vyn man står ───────────────────────────────────────────────────

/**
 * Fliken och den öppna rapporten. Vyn monteras ner när en verifikation
 * öppnas i detaljlagret (`Skal`), och "tillbaka" ska landa i samma rapport,
 * så valet står i `sessionStorage` per år. Kan storage inte nås håller en
 * modul-`Map` det så länge sidan lever.
 */
export interface GranskningsVal {
  flik: "rapporter" | "tackning";
  rapport: string | null;
}

const VAL_PREFIX = "bok:granskning:";
const STANDARDVAL: GranskningsVal = { flik: "rapporter", rapport: null };
const valReserv = new Map<string, GranskningsVal>();

export function lasVal(arId: string): GranskningsVal {
  try {
    const s = typeof window === "undefined" ? null : window.sessionStorage;
    const rad = s?.getItem(VAL_PREFIX + arId);
    if (rad) {
      const v = JSON.parse(rad) as Partial<GranskningsVal>;
      return {
        flik: v.flik === "tackning" ? "tackning" : "rapporter",
        rapport: typeof v.rapport === "string" ? v.rapport : null,
      };
    }
    if (s) return STANDARDVAL;
  } catch {
    // Reserven nedan.
  }
  return valReserv.get(arId) ?? STANDARDVAL;
}

export function sparaVal(arId: string, val: GranskningsVal): void {
  valReserv.set(arId, val);
  try {
    window.sessionStorage.setItem(VAL_PREFIX + arId, JSON.stringify(val));
  } catch {
    // Reserven räcker.
  }
}

/** Områdena i rapporten (`area`), på svenska. Ett okänt område visas som det står. */
export const OMRADE_TEXT: Record<string, string> = {
  moms: "Moms",
  periodisering: "Periodisering",
  privat: "Privata kostnader",
  underlag: "Underlag",
  avstamning: "Avstämning",
  bokslut: "Bokslut",
  forvaltning: "Förvaltning",
  ovrigt: "Övrigt",
};

export const omradeText = (area: string): string => OMRADE_TEXT[area] ?? area;
