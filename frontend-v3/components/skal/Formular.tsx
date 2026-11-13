"use client";

/**
 * Formulärets byggstenar i skalets vyer med egen komponent (Anställda,
 * Företaget): fält, etikett, rubrik och knapp, så att formulären ser lika ut.
 */

export const FALT =
  "bok-mono w-full rounded-md border border-bok-linje bg-bok-yta px-3 py-[7px] text-[13px] text-bok-text placeholder:text-bok-meta focus:border-bok-lank focus:outline-none";

export function Rubrik({ children }: { children: React.ReactNode }) {
  return <div className="bok-etikett pb-[6px] pt-5 text-[10px] text-bok-meta">{children}</div>;
}

export function Falt({
  etikett,
  hjalp,
  children,
}: {
  etikett: string;
  hjalp?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="text-[13px] text-bok-text-2">{etikett}</span>
      {children}
      {hjalp && <span className="text-[12px] text-bok-meta">{hjalp}</span>}
    </label>
  );
}

export function Knapp({
  children,
  disabled,
  type = "submit",
  onClick,
  sekundar,
}: {
  children: React.ReactNode;
  disabled?: boolean;
  type?: "submit" | "button";
  onClick?: () => void;
  sekundar?: boolean;
}) {
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={
        sekundar
          ? "rounded-md border border-bok-linje px-4 py-[8px] text-[14px] text-bok-text hover:bg-bok-yta-svag disabled:opacity-60"
          : "rounded-md bg-bok-black px-4 py-[8px] text-[14px] text-bok-yta hover:bg-bok-black-hover disabled:opacity-60"
      }
    >
      {children}
    </button>
  );
}
