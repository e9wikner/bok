"use client";

/**
 * `VyHeaderStatus` (komponenter.md): vytitel 17/500 + status mono 12 i
 * lägets färg, border-bottom, padding 20/24/14.
 *
 * "Samma sträng visas i headern, från samma fält" — därför tar både den här
 * och `Header` sin status ur `lageFarg()`, aldrig ur två strängar.
 */
export function VyHeaderStatus({
  titel,
  status,
  fg,
  variant = "desktop",
}: {
  titel: string;
  status: string;
  fg: string;
  variant?: "desktop" | "mobil";
}) {
  return (
    <div
      className={
        variant === "desktop"
          ? "flex shrink-0 items-baseline justify-between gap-[14px] border-b border-bok-linje-svag px-6 pb-[14px] pt-5"
          : "flex items-baseline justify-between gap-3 border-b border-bok-linje-svagast px-[18px] pb-3 pt-4"
      }
    >
      <span
        className={`font-medium tracking-[-0.01em] ${variant === "desktop" ? "text-[17px]" : "text-[18px]"}`}
      >
        {titel}
      </span>
      <span
        className={`bok-mono text-right ${variant === "desktop" ? "text-[12px]" : "text-[11px]"}`}
        style={{ color: fg }}
      >
        {status}
      </span>
    </div>
  );
}
