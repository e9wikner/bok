"use client";

import type { BannerTon } from "@/lib/skal/vydata";

/**
 * `VyBanner` (komponenter.md): radius 10, padding 12/14, text 13/1.5.
 *
 * Fyra toner, EN banner åt gången, "och bara när den säger något som
 * raderna inte redan säger". Komponenten renderar en banner; regeln att det
 * bara får finnas en bor i `VyData`, som bara har plats för en.
 */

const TONER: Record<BannerTon, { yta: string; kant: string; fg: string }> = {
  varning: { yta: "var(--bok-vantar-yta)", kant: "var(--bok-vantar-kant)", fg: "var(--bok-vantar-text)" },
  neutral: { yta: "var(--bok-yta-svag)", kant: "var(--bok-linje)", fg: "var(--bok-text-2)" },
  fel: { yta: "var(--bok-fel-yta)", kant: "var(--bok-fel-kant)", fg: "var(--bok-fel-text)" },
  klart: { yta: "var(--bok-klart-yta)", kant: "var(--bok-klart-kant)", fg: "var(--bok-klart-text)" },
};

export function VyBanner({ ton, text }: { ton: BannerTon; text: string }) {
  const t = TONER[ton];
  return (
    <div
      role="status"
      className="rounded-[10px] border px-[14px] py-3 text-[13px] leading-[1.5] [text-wrap:pretty]"
      style={{ background: t.yta, borderColor: t.kant, color: t.fg }}
    >
      {text}
    </div>
  );
}
