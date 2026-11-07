"use client";

import { useState } from "react";
import { oppnaUnderlag } from "@/lib/chattyta/api";
import type { UserFileInlagg } from "@/lib/chattyta/typer";

/**
 * `FilInlagg` (komponenter.md §Chatten, SPEC-chattyta.md §5): en bilaga
 * människan skickat. Läsbar — filnamn och filmeta — men ingen
 * förhandsvisning: filen är ett underlag, och att visa den är
 * `flode-underlag`s sak, inte tråden.
 *
 * komponenter.md: högerställd, gap 8. Filkort #eef0f3, radius 14, padding
 * 12/16; sidikon 30×38 (kant 1px #c7c7cc, radius 4, vit yta); filnamn 14;
 * filmeta mono 11 #6b7280 (`218 kB · 1 sida`).
 *
 * `user_file` har ingen text i kroppen (`typer.ts::UserFileKropp`), så
 * designens "valfria textbubbla under" ritas inte — en fil med en fråga
 * skickas som två inlägg och blir två inlägg.
 *
 * Kortet har en länk som öppnar filen (SPEC-flode-underlag.md §10.4). Inte
 * en vanlig `href`: `GET /intake/{id}/file` kräver bearer, så filen hämtas
 * som blob genom `apiClient` (`oppnaUnderlag`, `lib/chattyta/api.ts`).
 */

const siffror = (n: number, decimaler: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: decimaler }).format(n);

/**
 * `218 kB · 1 sida`. Decimala enheter (1 kB = 1000 B), som designens exempel
 * — 218000 byte är 218 kB, inte 213. Sidor bara när servern vet dem
 * (`pages` är `null` för allt som inte är PDF).
 */
export function filMeta(sizeBytes: number, pages: number | null): string {
  let storlek: string;
  if (sizeBytes < 1000) {
    storlek = `${sizeBytes} B`;
  } else if (Math.round(sizeBytes / 1000) < 1000) {
    storlek = `${Math.round(sizeBytes / 1000)} kB`;
  } else {
    // 999 600 byte avrundas till 1000 kB — skriv det som 1 MB i stället.
    storlek = `${siffror(sizeBytes / 1_000_000, 1)} MB`;
  }
  if (pages === null) return storlek;
  return `${storlek} · ${pages} ${pages === 1 ? "sida" : "sidor"}`;
}

export function FilInlagg({ inlagg }: { inlagg: UserFileInlagg }) {
  const { filename, size_bytes, pages, intake_source_id } = inlagg.body;
  const [fel, setFel] = useState(false);
  return (
    <div className="flex flex-col items-end gap-2">
      <div data-testid="filkort" className="flex items-center gap-3 rounded-[14px] bg-bok-bubbla px-4 py-3">
        <span
          data-testid="sidikon"
          aria-hidden="true"
          className="block h-[38px] w-[30px] shrink-0 rounded border border-bok-kant-streckad bg-bok-yta"
        />
        <span className="flex min-w-0 flex-col gap-[2px]">
          {/* Långa filnamn bryts i stället för att spräcka bubblan. */}
          <span className="break-all text-[14px]">{filename}</span>
          <span className="bok-mono text-[11px] text-bok-text-svag">{filMeta(size_bytes, pages)}</span>
          <button
            type="button"
            aria-label={`Öppna ${filename}`}
            onClick={() => {
              setFel(false);
              oppnaUnderlag(intake_source_id).catch(() => setFel(true));
            }}
            className="bok-mono self-start text-[11px] text-bok-lank underline-offset-2 hover:text-bok-lank-hover hover:underline"
          >
            {fel ? "filen kunde inte öppnas" : "öppna"}
          </button>
        </span>
      </div>
    </div>
  );
}
