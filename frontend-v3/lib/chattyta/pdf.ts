/**
 * Den sparade faktura-PDF:en (SPEC-fakturering-f1.md §8.2). Routen kräver
 * auth, så en vanlig länk fungerar inte: filen hämtas som blob med
 * `apiClient` och öppnas i en ny flik. Byte för byte den sparade filen —
 * klienten renderar ingenting.
 */

import apiClient from "@/lib/api";

export async function oppnaPdf(pdfUrl: string): Promise<void> {
  // Fliken öppnas i klicket, innan svaret: en popup efter en `await` stoppas
  // av webbläsaren.
  const flik = typeof window !== "undefined" ? window.open("", "_blank") : null;
  const { data } = await apiClient.get<Blob>(pdfUrl, { responseType: "blob" });
  const url = URL.createObjectURL(data);
  if (flik) flik.location.href = url;
  else if (typeof window !== "undefined") window.open(url, "_blank");
}
