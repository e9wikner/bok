"use client";

import { useState } from "react";
import { Lock, LockOpen } from "lucide-react";
import { lasfel, type LasData } from "@/lib/skal/las";

/**
 * Ett lås som visar läget och växlar det vid tryck. Ingen bekräftelsedialog:
 * låset går att öppna igen, och postade verifikationer rörs inte av någotdera.
 * Ett vägrat tryck (t.ex. utkast i perioden) står som en kort rad bredvid.
 */
export function LasKnapp({ last, vad, vaxla }: LasData) {
  const [pagar, setPagar] = useState(false);
  const [fel, setFel] = useState<string | null>(null);
  const etikett = `${last ? "Lås upp" : "Lås"} ${vad}`;
  const Ikon = last ? Lock : LockOpen;

  return (
    <span className="inline-flex items-center gap-[6px]">
      {fel && (
        <span role="alert" className="bok-mono text-[11px] text-bok-fel-meta">
          {fel}
        </span>
      )}
      <button
        type="button"
        aria-label={etikett}
        aria-pressed={last}
        title={etikett}
        disabled={pagar}
        onClick={() => {
          setFel(null);
          setPagar(true);
          vaxla()
            .catch((e) => setFel(lasfel(e)))
            .finally(() => setPagar(false));
        }}
        className={`-m-1 rounded p-1 transition-colors hover:bg-bok-yta-svag disabled:opacity-50 ${
          last ? "text-bok-text" : "text-bok-meta hover:text-bok-text-svag"
        }`}
      >
        <Ikon aria-hidden="true" className="h-[14px] w-[14px]" strokeWidth={1.75} />
      </button>
    </span>
  );
}
