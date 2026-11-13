"use client";

import { useEffect, useState } from "react";
import { harFiler } from "@/lib/skal/menySlapp";

/**
 * Dras en fil över fönstret just nu?
 *
 * `dragenter`/`dragleave` kommer för varje element pekaren passerar, så
 * räknaren håller reda på när pekaren lämnat fönstret helt. Ett släpp eller
 * en avbruten dragning nollställer.
 *
 * Ett släpp som ingen yta tog emot gör ingenting, i stället för att
 * webbläsaren öppnar filen i fliken och lämnar appen.
 */
export function useFilDrag(aktiv = true): boolean {
  const [drar, setDrar] = useState(false);

  useEffect(() => {
    if (!aktiv) return;
    let djup = 0;
    const in_ = (e: DragEvent) => {
      if (!harFiler(e.dataTransfer)) return;
      djup += 1;
      setDrar(true);
    };
    const ut = (e: DragEvent) => {
      if (!harFiler(e.dataTransfer)) return;
      djup = Math.max(0, djup - 1);
      if (djup === 0) setDrar(false);
    };
    const over = (e: DragEvent) => {
      if (!harFiler(e.dataTransfer) || e.defaultPrevented) return;
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "none";
    };
    const slut = (e: DragEvent) => {
      djup = 0;
      setDrar(false);
      if (e.type === "drop" && !e.defaultPrevented) e.preventDefault();
    };
    window.addEventListener("dragenter", in_);
    window.addEventListener("dragleave", ut);
    window.addEventListener("dragover", over);
    window.addEventListener("drop", slut);
    window.addEventListener("dragend", slut);
    return () => {
      window.removeEventListener("dragenter", in_);
      window.removeEventListener("dragleave", ut);
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", slut);
      window.removeEventListener("dragend", slut);
    };
  }, [aktiv]);

  return aktiv && drar;
}
