// Grupperar verifikationer per kalendermånad för verifikationslistan.

export interface MonthGroup<T> {
  key: string; // "2026-03"
  vouchers: T[];
}

function monthKey(date: string): string {
  return date.slice(0, 7);
}

function monthsBetween(startKey: string, endKey: string): string[] {
  const out: string[] = [];
  let [y, m] = startKey.split("-").map(Number);
  const [ey, em] = endKey.split("-").map(Number);
  while (y < ey || (y === ey && m <= em)) {
    out.push(`${y}-${String(m).padStart(2, "0")}`);
    m += 1;
    if (m > 12) {
      m = 1;
      y += 1;
    }
  }
  return out;
}

/**
 * Månadsgrupper, nyast först. Med `range` (räkenskapsårets datum) kommer
 * även månader utan verifikationer med, så att de kan visas som tomma
 * eller döljas. Verifikationer utanför intervallet får sin egen grupp.
 */
export function groupByMonth<T extends { date: string }>(
  vouchers: T[],
  range?: { start: string; end: string },
): MonthGroup<T>[] {
  const byKey = new Map<string, T[]>();
  for (const v of vouchers) {
    if (!v.date) continue;
    const k = monthKey(v.date);
    byKey.set(k, [...(byKey.get(k) ?? []), v]);
  }
  const keys = new Set(byKey.keys());
  if (range) {
    for (const k of monthsBetween(monthKey(range.start), monthKey(range.end))) {
      keys.add(k);
    }
  }
  return [...keys]
    .sort()
    .reverse()
    .map((key) => ({ key, vouchers: byKey.get(key) ?? [] }));
}

const MONTHS = [
  "januari", "februari", "mars", "april", "maj", "juni",
  "juli", "augusti", "september", "oktober", "november", "december",
];

export function formatMonthLabel(key: string): string {
  const [y, m] = key.split("-").map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}
