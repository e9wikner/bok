"use client";

import { type ReactNode, useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useFilDrag } from "@/hooks/useFilDrag";
import { DROPZONE_NYCKEL, dropzoneApi, felText } from "@/lib/skal/dropzone";
import {
  type Notis,
  type SlappMal,
  UNDERLAG,
  UTLAGG,
  fordela,
  harFiler,
  notisRader,
  utlaggTarEmot,
} from "@/lib/skal/menySlapp";

/** En notis utan fel går av sig själv; en med fel står kvar tills den stängs. */
const NOTIS_MS = 8000;

/**
 * Sidomenyn som släppyta (`lib/skal/menySlapp.ts`). Medan en fil dras över
 * fönstret ligger två zoner över menyn — Underlag och Utlägg — och ett släpp
 * på en av dem lägger filen i den mappen. Efteråt säger en notis längst ner
 * i menyn vad som hände, med en väg till Underlag-vyn.
 *
 * Tråden tar fortfarande emot sina egna släpp: där bifogas filen till
 * meddelandet. Den här ytan gäller bara menyn.
 */
export function MenySlapp({ children, onVisaDropzone }: { children: ReactNode; onVisaDropzone: () => void }) {
  const drar = useFilDrag();
  const queryClient = useQueryClient();
  const [over, setOver] = useState<SlappMal | null>(null);
  const [notis, setNotis] = useState<{ n: Notis; antal: number } | null>(null);

  useEffect(() => {
    if (!drar) setOver(null);
  }, [drar]);

  useEffect(() => {
    if (!notis || notis.n.laddar || notis.n.fel.length > 0) return;
    const t = setTimeout(() => setNotis(null), NOTIS_MS);
    return () => clearTimeout(t);
  }, [notis]);

  const slapp = useCallback(
    async (mal: SlappMal, filer: File[]) => {
      if (filer.length === 0) return;
      const { grupper, flyttade } = fordela(mal, filer);
      const n: Notis = { laddar: false, lagda: [], fel: [], flyttade };
      setNotis({ n: { ...n, laddar: true }, antal: filer.length });
      for (const g of grupper) {
        try {
          const resultat = await dropzoneApi.slapp(g.folder, g.filer);
          let lagda = 0;
          g.filer.forEach((fil, i) => {
            const r = resultat[i];
            if (r?.ok) lagda += 1;
            else n.fel.push({ namn: fil.name, text: r?.error ?? "servern svarade inte för filen" });
          });
          if (lagda > 0) n.lagda.push({ folder: g.folder, antal: lagda });
        } catch (fel) {
          const text = felText(fel);
          for (const fil of g.filer) n.fel.push({ namn: fil.name, text });
        }
      }
      setNotis({ n, antal: filer.length });
      void queryClient.invalidateQueries({ queryKey: DROPZONE_NYCKEL });
    },
    [queryClient]
  );

  return (
    <div className="relative flex shrink-0">
      {children}
      {drar && (
        <div
          data-testid="meny-slapp"
          className="absolute inset-0 z-20 flex flex-col gap-3 border-r border-bok-linje bg-bok-yta px-3 py-5"
        >
          <span className="bok-etikett px-3 text-[10px] text-bok-meta">Lägg till underlag</span>
          <Zon
            mal="underlag"
            titel={UNDERLAG}
            text="Kvitto, faktura, kontoutdrag (CSV) eller SIE4. Filändelsen avgör vad filen blir."
            over={over === "underlag"}
            setOver={setOver}
            onSlapp={slapp}
            className="flex-1"
          />
          <Zon
            mal="utlagg"
            titel={UTLAGG}
            text="Köp du betalat privat och företaget ersätter. PDF eller bild."
            over={over === "utlagg"}
            setOver={setOver}
            onSlapp={slapp}
            className="h-[140px] shrink-0"
          />
        </div>
      )}
      {notis && !drar && (
        <NotisRuta
          rader={notisRader(notis.n, notis.antal)}
          laddar={notis.n.laddar}
          fel={notis.n.fel.length > 0}
          onVisa={() => {
            setNotis(null);
            onVisaDropzone();
          }}
          onStang={() => setNotis(null)}
        />
      )}
    </div>
  );
}

function Zon({
  mal,
  titel,
  text,
  over,
  setOver,
  onSlapp,
  className,
}: {
  mal: SlappMal;
  titel: string;
  text: string;
  over: boolean;
  setOver: (m: SlappMal | null) => void;
  onSlapp: (mal: SlappMal, filer: File[]) => void;
  className: string;
}) {
  const [stangd, setStangd] = useState(false);
  return (
    <div
      data-testid={`meny-slapp-${mal}`}
      data-over={over ? "true" : undefined}
      data-stangd={stangd ? "true" : undefined}
      onDragOver={(e) => {
        if (!harFiler(e.dataTransfer)) return;
        // Alltid hanterad här, så att fönstrets fallback inte rör den.
        e.preventDefault();
        const tar = mal === "underlag" || utlaggTarEmot(e.dataTransfer);
        e.dataTransfer.dropEffect = tar ? "copy" : "none";
        setStangd(!tar);
        setOver(tar ? mal : null);
      }}
      onDragLeave={(e) => {
        if (e.relatedTarget instanceof Node && e.currentTarget.contains(e.relatedTarget)) return;
        setOver(null);
        setStangd(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setOver(null);
        setStangd(false);
        onSlapp(mal, Array.from(e.dataTransfer.files ?? []));
      }}
      className={`flex flex-col justify-center gap-1 rounded-lg border border-dashed px-4 py-4 transition-colors ${
        stangd
          ? "border-bok-linje opacity-50"
          : over
            ? "border-bok-lank bg-bok-yta-svag"
            : "border-bok-kant-streckad"
      } ${className}`}
    >
      <span className="text-[15px] font-medium text-bok-text">{titel}</span>
      <span className="bok-mono text-[11px] leading-[1.5] text-bok-meta">
        {stangd ? `${UTLAGG} tar inte kontoutdrag eller SIE4` : text}
      </span>
      <span className="bok-mono pt-1 text-[11px] text-bok-lank">{over ? "släpp här" : " "}</span>
    </div>
  );
}

function NotisRuta({
  rader,
  laddar,
  fel,
  onVisa,
  onStang,
}: {
  rader: string[];
  laddar: boolean;
  fel: boolean;
  onVisa: () => void;
  onStang: () => void;
}) {
  return (
    <div
      role="status"
      data-testid="meny-slapp-notis"
      className={`absolute inset-x-3 bottom-3 z-10 flex flex-col gap-1 rounded-lg border px-3 py-[10px] shadow-sm ${
        fel ? "border-bok-fel-kant bg-bok-fel-yta" : "border-bok-linje bg-bok-yta"
      }`}
    >
      {rader.map((r, i) => (
        <span
          key={i}
          className={`bok-mono break-words text-[11px] leading-[1.5] ${fel ? "text-bok-fel-meta" : "text-bok-text-2"}`}
        >
          {r}
        </span>
      ))}
      {!laddar && (
        <span className="flex items-center justify-between gap-2 pt-1">
          <button type="button" onClick={onVisa} className="bok-mono text-[11px] text-bok-lank hover:underline">
            visa i Underlag →
          </button>
          <button
            type="button"
            onClick={onStang}
            aria-label="Stäng"
            className="bok-mono text-[13px] leading-none text-bok-meta hover:text-bok-text"
          >
            ×
          </button>
        </span>
      )}
    </div>
  );
}
