/**
 * `Nyss kopplad` (SPEC-flode-underlag.md §10.4, FU21).
 *
 * När servern kopplat ett underlag till en postad verifikation skickar den
 * `view.changed` med `{voucher_id, source_id, kind: "source_linked"}` (§9.3).
 * `useTrad` lägger händelsen här; vyn Verifikationer (`useVyer`) läser den
 * och flyttar raden från `Saknar underlag` till överst i `Postade`, med
 * `kvitto kopplat HH:MM` och läget `ny` i `NY_KOPPLING_MS`.
 *
 * Som `postningar.ts`: posten är klientens, bor i TanStack-cachen under
 * `KOPPLINGAR_NYCKEL` — utanför `VOUCHERS_NYCKEL`, så att invalideringen som
 * samma händelse gör inte tar den — och finns inte efter en omladdning.
 * Efter markeringen står posten kvar med `ny: false`, så att raden kan säga
 * `kvitto kopplat` i sitt vanliga läge: `VoucherResponse` bär inget fält som
 * säger att en verifikation har ett kopplat kvitto, bara att den inte
 * saknar underlag.
 *
 * Klockslaget är klientens, när händelsen kom: händelsen bär ingen tid, och
 * ett klockslag är inget belopp, nummer eller räknare.
 */

import type { QueryClient } from "@tanstack/react-query";
import { NY_POSTNING_MS } from "@/lib/chattyta/postningar";

/** Utanför `VOUCHERS_NYCKEL`/`DRAFTS_NYCKEL`: ingen invalidering ska röra den. */
export const KOPPLINGAR_NYCKEL = ["kopplingar"] as const;

/** Samma varaktighet som `ny` efter en postning, och som `VyRad`s markering. */
export const NY_KOPPLING_MS = NY_POSTNING_MS;

/** Serverns `VoucherRefResponse`. */
export interface KopplingRef {
  id: string;
  series: string;
  number: number | null;
}

/** Verifikationen som vyn senast såg den, ögonblicksbild när händelsen kom. */
export interface KopplingVerifikation {
  id: string;
  series: string;
  number: number | null;
  date: string;
  description: string;
  total_debit: number;
  referenced_by?: KopplingRef | null;
}

export interface Koppling {
  voucherId: string;
  sourceId: string | null;
  /** `HH:MM`, klientens klocka när `view.changed` kom. */
  klockslag: string;
  /** `true` i `NY_KOPPLING_MS`, sedan `false`. */
  ny: boolean;
  /** `null` om ingen fråga i cachen hade verifikationen. */
  verifikation: KopplingVerifikation | null;
}

const arObjekt = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/**
 * `view.changed`s kropp när den gäller en koppling, annars `null`. Servern
 * lägger det som ändrats under `changed` (`{view_key, changed: {voucher_id,
 * kind}}`, som `voucher_posted` i `services/thread_stream.py`); en kropp med
 * fälten direkt i roten läses också.
 */
export function lasKoppling(data: unknown): { voucherId: string; sourceId: string | null } | null {
  if (!arObjekt(data)) return null;
  const d = arObjekt(data.changed) ? data.changed : data;
  if (d.kind !== "source_linked" || typeof d.voucher_id !== "string" || !d.voucher_id) return null;
  return { voucherId: d.voucher_id, sourceId: typeof d.source_id === "string" ? d.source_id : null };
}

const lista = (qc: QueryClient): Koppling[] => qc.getQueryData<Koppling[]>(KOPPLINGAR_NYCKEL) ?? [];

const skriv = (qc: QueryClient, ut: Koppling[]) => qc.setQueryData<Koppling[]>(KOPPLINGAR_NYCKEL, ut);

const tva = (n: number) => String(n).padStart(2, "0");

/** Verifikationen ur vilken fråga under `["vouchers", …]` som helst som har den. */
function verifikationIVyn(qc: QueryClient, voucherId: string): KopplingVerifikation | null {
  for (const [, data] of qc.getQueriesData<{ vouchers?: unknown }>({ queryKey: ["vouchers"] })) {
    const vouchers = (data as { vouchers?: unknown } | undefined)?.vouchers;
    if (!Array.isArray(vouchers)) continue;
    const v = vouchers.find((x) => (x as { id?: unknown })?.id === voucherId) as
      | KopplingVerifikation
      | undefined;
    if (v) {
      return {
        id: v.id,
        series: v.series,
        number: v.number,
        date: v.date,
        description: v.description,
        total_debit: v.total_debit,
        referenced_by: v.referenced_by ?? null,
      };
    }
  }
  return null;
}

/**
 * Händelsen kom: raden blir `Nyss kopplad`. Ögonblicksbilden tas INNAN
 * invalideringen hunnit hämta om listorna — då står verifikationen
 * fortfarande i `Saknar underlag`s svar.
 */
export function kopplingKlar(
  qc: QueryClient,
  voucherId: string,
  sourceId: string | null,
  nu: Date = new Date()
): void {
  const fore = lista(qc).find((k) => k.voucherId === voucherId);
  const post: Koppling = {
    voucherId,
    sourceId,
    klockslag: `${tva(nu.getHours())}:${tva(nu.getMinutes())}`,
    ny: true,
    verifikation: verifikationIVyn(qc, voucherId) ?? fore?.verifikation ?? null,
  };
  skriv(qc, [post, ...lista(qc).filter((k) => k.voucherId !== voucherId)]);
  setTimeout(() => {
    // Bara om det är samma post: en ny händelse under tiden äger raden.
    const nuvarande = lista(qc);
    if (!nuvarande.includes(post)) return;
    skriv(qc, nuvarande.map((k) => (k === post ? { ...k, ny: false } : k)));
  }, NY_KOPPLING_MS);
}
