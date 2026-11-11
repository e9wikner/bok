"use client";

import { useState, useEffect } from "react";

/**
 * Mörkt eller ljust läge: klassen `.dark` på <html>, sparad i localStorage
 * under `darkMode`. Utan sparat val följer läget systemets.
 *
 * Skriptet i app/layout.tsx sätter klassen före första målningen. Därför
 * börjar läget som `null` och rör inte klassen förrän det är läst — annars
 * tog den första effekten bort klassen och sidan blinkade ljus.
 */
export function useDarkMode() {
  const [isDark, setIsDark] = useState<boolean | null>(null);

  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem("darkMode");
    } catch {
      // Blockerad lagring: följ systemet.
    }
    setIsDark(
      stored !== null ? stored === "true" : window.matchMedia("(prefers-color-scheme: dark)").matches
    );
  }, []);

  useEffect(() => {
    if (isDark === null) return;
    document.documentElement.classList.toggle("dark", isDark);
    try {
      localStorage.setItem("darkMode", String(isDark));
    } catch {
      // Valet gäller då bara den här sidvisningen.
    }
  }, [isDark]);

  return { isDark: isDark ?? false, toggle: () => setIsDark((v) => !v) };
}
