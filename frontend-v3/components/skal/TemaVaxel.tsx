"use client";

/**
 * Växeln mellan ljust och mörkt läge. Läget ägs av `Skal` (useDarkMode) och
 * delas med de gamla sidorna: samma klass på <html>, samma sparade val.
 * Knappen säger vad den gör, inte vilket läge som gäller.
 */
export interface Tema {
  isDark: boolean;
  toggle: () => void;
}

export function TemaVaxel({ tema, className = "" }: { tema: Tema; className?: string }) {
  return (
    <button
      type="button"
      data-testid="tema-vaxel"
      aria-pressed={tema.isDark}
      onClick={tema.toggle}
      className={`flex min-h-[32px] items-center gap-2 rounded-lg px-3 text-left text-[13px] text-bok-text-2 transition-colors hover:bg-bok-yta-svag hover:text-bok-text ${className}`}
    >
      <span aria-hidden="true" className="w-4 text-center">
        {tema.isDark ? "☀" : "☾"}
      </span>
      {tema.isDark ? "Ljust läge" : "Mörkt läge"}
    </button>
  );
}
