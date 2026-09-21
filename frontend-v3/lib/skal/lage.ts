/**
 * De sex lägena och deras statusfärg (README.md §Tillstånd).
 *
 * Färgen bor på ETT ställe därför att komponenter.md säger om
 * `VyHeaderStatus`: "Samma sträng visas i headern, från samma fält."
 * Två uppslagstabeller hade glidit isär vid första ändringen.
 */

import type { VyLage } from "@/lib/skal/mock";

const STATUS_FARG: Record<VyLage, string> = {
  normal: "var(--bok-text-svag)",
  vantar: "var(--bok-vantar-meta)",
  pagaende: "var(--bok-text-svag)",
  klart: "var(--bok-klart-meta)",
  fel: "var(--bok-fel-meta)",
  tomt: "var(--bok-text-svag)",
};

export function lageFarg(lage: VyLage): string {
  return STATUS_FARG[lage];
}
