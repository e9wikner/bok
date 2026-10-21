/**
 * Sökrutan i Verifikationer (modul `skal`): fuzzy-filtrering i klienten,
 * som telescope i neovim.
 *
 * Varje ord i frågan ska finnas som en delsekvens i raden — tecknen i rätt
 * ordning, inte nödvändigtvis intill varandra — så `a12` träffar `A-12` och
 * `1234` träffar `1 234`. Placeringen poängsätts som i fzy: tecken i följd
 * och tecken i början av ett ord väger tyngst, luckor drar av. Bästa träffen
 * står överst. Serverns `search` är bara LIKE, därför sker det här.
 */

import type { VyData, VyRadData } from "@/lib/skal/vydata";

export interface Matchning {
  poang: number;
  /** De matchade tecknens positioner i texten, stigande. */
  index: number[];
}

const I_FOLJD = 1.0;
const ORDSTART = 0.8;
const LUCKA_FORE = -0.005;
const LUCKA_INNE = -0.01;
const LUCKA_EFTER = -0.005;
const INGEN = -Infinity;

/** Tecken efter vilka nästa tecken börjar ett ord. */
const AVGRANSARE = new Set([" ", "-", "·", "/", "_", ".", ",", "(", ":"]);

function bonus(text: string, j: number): number {
  return j === 0 || AVGRANSARE.has(text[j - 1]) ? ORDSTART : 0;
}

/**
 * Bästa placeringen av `fraga` som delsekvens i `text`, eller `null` om den
 * inte finns. Skiftlägesokänslig; `fraga` ska redan vara gemen och utan
 * blanksteg. Positionerna är UTF-16-enheter, som `String.prototype.slice`.
 */
export function matcha(fraga: string, text: string): Matchning | null {
  const m = fraga.length;
  const n = text.length;
  if (m === 0 || m > n) return null;
  const gemen = Array.from({ length: n }, (_, j) => text[j].toLocaleLowerCase("sv"));

  // Snabbt nej innan matriserna byggs.
  let k = 0;
  for (let j = 0; j < n && k < m; j++) if (gemen[j] === fraga[k]) k++;
  if (k < m) return null;

  // D[i][j]: bästa poäng med fraga[i] på text[j]. M[i][j]: bästa poäng för
  // fraga[0..i] inom text[0..j], fraga[i] var som helst till och med j.
  const D: number[][] = [];
  const M: number[][] = [];
  for (let i = 0; i < m; i++) {
    const d = new Array<number>(n).fill(INGEN);
    const mm = new Array<number>(n).fill(INGEN);
    const lucka = i === m - 1 ? LUCKA_EFTER : LUCKA_INNE;
    let forra = INGEN;
    for (let j = 0; j < n; j++) {
      if (gemen[j] === fraga[i]) {
        let s = INGEN;
        if (i === 0) s = j * LUCKA_FORE + bonus(text, j);
        else if (j > 0) s = Math.max(M[i - 1][j - 1] + bonus(text, j), D[i - 1][j - 1] + I_FOLJD);
        d[j] = s;
        mm[j] = Math.max(s, forra + lucka);
      } else {
        mm[j] = forra + lucka;
      }
      forra = mm[j];
    }
    D.push(d);
    M.push(mm);
  }

  const poang = M[m - 1][n - 1];
  if (poang === INGEN) return null;

  // Tillbaka genom matriserna: den placering som gav poängen.
  const index = new Array<number>(m);
  let kravsI = false;
  let j = n - 1;
  for (let i = m - 1; i >= 0; i--) {
    for (; j >= 0; j--) {
      if (D[i][j] !== INGEN && (kravsI || D[i][j] === M[i][j])) {
        kravsI = i > 0 && j > 0 && M[i][j] === D[i - 1][j - 1] + I_FOLJD;
        index[i] = j;
        j--;
        break;
      }
    }
  }
  return { poang, index };
}

type Falt = "titel" | "meta" | "hoger";
const FALT: readonly Falt[] = ["titel", "meta", "hoger"];

/** Frågans ord, gemena. Tom fråga ger inga ord. */
export function ordI(fraga: string): string[] {
  return fraga.trim().toLocaleLowerCase("sv").split(/\s+/).filter(Boolean);
}

/**
 * En rad mot alla frågans ord. Varje ord tar sin bästa träff bland titel,
 * meta och belopp; saknas ett ord helt är raden ingen träff.
 */
export function matchaRad(ord: readonly string[], rad: VyRadData): { poang: number; traff: NonNullable<VyRadData["traff"]> } | null {
  let poang = 0;
  const traff: Partial<Record<Falt, Set<number>>> = {};
  for (const o of ord) {
    let bast: { falt: Falt; m: Matchning } | null = null;
    for (const falt of FALT) {
      const text = rad[falt];
      if (!text) continue;
      const m = matcha(o, text);
      if (m && (!bast || m.poang > bast.m.poang)) bast = { falt, m };
    }
    if (!bast) return null;
    poang += bast.m.poang;
    const s = (traff[bast.falt] ??= new Set());
    for (const i of bast.m.index) s.add(i);
  }
  const ut: NonNullable<VyRadData["traff"]> = {};
  for (const falt of FALT) {
    const s = traff[falt];
    if (s) ut[falt] = [...s].sort((a, b) => a - b);
  }
  return { poang, traff: ut };
}

function antalTraffar(n: number): string {
  return n === 0 ? "inga träffar" : n === 1 ? "1 träff" : `${n} träffar`;
}

/**
 * Vyn filtrerad på `fraga`: alla sektioners rader i en enda lista, bästa
 * träffen först. Lika poäng behåller vyns ordning. En rad som står i två
 * sektioner visas en gång. Utan ord i frågan är vyn oförändrad.
 */
export function sokVy(vy: VyData, fraga: string): VyData {
  const ord = ordI(fraga);
  if (ord.length === 0) return vy;

  const sedda = new Set<string>();
  const traffar: { rad: VyRadData; poang: number }[] = [];
  for (const sektion of vy.sektioner) {
    for (const rad of sektion.rader) {
      if (sedda.has(rad.id)) continue;
      sedda.add(rad.id);
      const t = matchaRad(ord, rad);
      if (t) traffar.push({ rad: { ...rad, traff: t.traff }, poang: t.poang });
    }
  }
  traffar.sort((a, b) => b.poang - a.poang);

  return {
    lage: traffar.length === 0 ? "tomt" : "normal",
    status: antalTraffar(traffar.length),
    period: vy.period,
    sektioner: [{ titel: "Träffar", rader: traffar.map((t) => t.rad), tom: "inga träffar" }],
    fot: vy.fot,
  };
}
