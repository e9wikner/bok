"use client";

/**
 * `VySektion` (komponenter.md): rubrik mono 10 versalt, padding 20/0/6.
 *
 * "Tom sektion visas inte alls." Det är en regel, inte en stil: en rubrik
 * utan rader är en lögn om att något saknas. Tomt läge i README.md
 * §Tillstånd säger samma sak — "sektionen utgår helt, inte tom rubrik".
 */
export function VySektion({
  titel,
  children,
  antalRader,
  variant = "desktop",
}: {
  titel: string;
  children: React.ReactNode;
  antalRader: number;
  variant?: "desktop" | "mobil";
}) {
  if (antalRader === 0) return null;

  return (
    <div className="flex flex-col">
      <div
        className={`bok-etikett text-[10px] text-bok-meta ${
          variant === "desktop" ? "pb-[6px] pt-5" : "pb-[6px] pt-[18px]"
        }`}
      >
        {titel}
      </div>
      {children}
    </div>
  );
}
