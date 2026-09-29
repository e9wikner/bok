"use client";

import { forwardRef, useCallback, useEffect, useId, useRef, useState, type RefObject } from "react";
import { filMeta } from "@/components/chattyta/FilInlagg";
import {
  arInlastKontoutdrag,
  bilagor,
  chipStatus,
  kanSkicka,
  kontoutdragsnotiser,
  laddaUppChip,
  laddarUpp,
  medUtfall,
  nyttChip,
  TILLATNA_TYPER,
  type FilChip,
} from "@/lib/chattyta/uppladdning";

/**
 * `ChattFalt` (komponenter.md): radius 12, streckad kant #c7c7cc,
 * background #fbfbfc, padding 13/16, text 15 #71717a, ↵ mono 12 till höger.
 *
 * REN TEXTINMATNING — INGA FÖRSLAGSCHIPS. README.md och komponenter.md
 * säger det båda ordagrant; v10-prototypen har en påslagen växel som visar
 * två chips, och beställaren avgjorde 2026-09-21 att texten gäller.
 * SPEC-skal.md §2.1. Lägg inte tillbaka dem: ett chip är ett förvalt
 * yttrande, och designens egen regel är att ingenting förväljs. Filchipen
 * nedan är inga förslag — de är filer människan själv släppt.
 *
 * Varianten `drop` (komponenter.md: *"tar emot filer via drag och släpp,
 * kamera och urklipp. Ingen separat uppladdningssida."*,
 * SPEC-flode-underlag.md §10): en knapp i fältet öppnar filväljaren (på
 * mobil kameran), en fil i urklippet klistras in som fil, och en fil som
 * släpps var som helst på `slappYta` (tråden) hamnar här. Varje fil laddas
 * upp direkt (`POST /intake`) och blir ett chip; `↵` skickar texten och de
 * klara chipens id:n (`lib/chattyta/uppladdning.ts`). Ingenting kopplas: en
 * uppladdning gör en källa i intagskön, och vad den hör till avgörs i tråden.
 *
 * `ref` går till textfältet, så att förslagskortets `Ändra` kan lägga fokus
 * här utan att skicka något (SPEC-chattyta.md §8 steg 4, chattyta C12).
 */

/** Filväljarens typer på desktop: serverns, speglade i `uppladdning.ts`, och kontoutdrag som CSV. */
const ACCEPT_DESKTOP = [...TILLATNA_TYPER, ".csv", "text/csv"].join(",");

let chipnummer = 0;

const harFiler = (dt: DataTransfer | null): boolean =>
  !!dt && Array.from(dt.types ?? []).includes("Files");

export const ChattFalt = forwardRef<
  HTMLInputElement,
  {
    vyTitel: string;
    variant?: "desktop" | "mobil";
    /**
     * `useTrad().skicka` (chattyta C5): POST /threads/{view_key}/messages.
     * Fältet töms bara när den svarar `true` — servern har då lagrat texten.
     * `false` (POST misslyckades) eller `void` lämnar texten kvar, så att
     * människan inte behöver skriva om den (tasks/chattyta/todo.md, C3).
     *
     * `attachments` skickas bara när det finns klara chip; ett meddelande
     * utan bilagor anropas med texten ensam, som förut.
     */
    onSkicka?: (text: string, attachments?: string[]) => Promise<boolean> | boolean | void;
    /**
     * Ytan där en släppt fil tas emot — tråden, inte bara fältet
     * (§10.1: *"dra och släpp på hela tråden"*). Utan `onSkicka` tas inga
     * filer emot: en fil som inte kan skickas vore en källa utan samtal.
     */
    slappYta?: RefObject<HTMLElement | null>;
  }
>(function ChattFalt({ vyTitel, variant = "desktop", onSkicka, slappYta }, ref) {
  // Ett id per fält: svepraden har flera kolumner på skärmen samtidigt, och
  // ett delat id gjorde att etiketten pekade på första kolumnens fält.
  const faltId = useId();
  const [text, setText] = useState("");
  // Ett andra Enter medan det första är i flykt skickar inte igen: texten
  // står ju kvar i fältet tills servern svarat, och samma fråga två gånger
  // är två turer för agenten.
  const [skickar, setSkickar] = useState(false);
  const [chips, setChips] = useState<FilChip[]>([]);
  const [drarOver, setDrarOver] = useState(false);
  const filvaljare = useRef<HTMLInputElement>(null);
  const etikett = `Fråga om en post i ${vyTitel.toLowerCase()}`;
  const tarEmot = !!onSkicka;

  /** En väg för alla tre ingångarna: chip direkt, uppladdning direkt. */
  const laggTill = useCallback(
    (filer: FileList | File[] | null | undefined) => {
      if (!tarEmot || !filer) return;
      const nya = Array.from(filer).map((f) => ({ fil: f, chip: nyttChip(f, `chip-${++chipnummer}`) }));
      if (nya.length === 0) return;
      setChips((cs) => [...cs, ...nya.map((n) => n.chip)]);
      for (const { fil, chip } of nya) {
        if (chip.lage !== "laddar") continue;
        void laddaUppChip(fil).then((utfall) =>
          // Ett chip som tagits bort under uppladdningen kommer inte tillbaka.
          setChips((cs) => cs.map((c) => (c.nyckel === chip.nyckel ? medUtfall(c, utfall) : c)))
        );
      }
    },
    [tarEmot]
  );

  useEffect(() => {
    const yta = slappYta?.current;
    if (!yta || !tarEmot) return;
    const over = (e: DragEvent) => {
      if (!harFiler(e.dataTransfer)) return;
      // Utan `preventDefault` på dragover släpper webbläsaren aldrig här,
      // och öppnar filen i fliken i stället.
      e.preventDefault();
      setDrarOver(true);
    };
    const lamnar = (e: DragEvent) => {
      if (e.relatedTarget instanceof Node && yta.contains(e.relatedTarget)) return;
      setDrarOver(false);
    };
    const slapp = (e: DragEvent) => {
      setDrarOver(false);
      if (!e.dataTransfer || e.dataTransfer.files.length === 0) return;
      e.preventDefault();
      laggTill(e.dataTransfer.files);
    };
    yta.addEventListener("dragover", over);
    yta.addEventListener("dragleave", lamnar);
    yta.addEventListener("drop", slapp);
    return () => {
      yta.removeEventListener("dragover", over);
      yta.removeEventListener("dragleave", lamnar);
      yta.removeEventListener("drop", slapp);
    };
  }, [slappYta, tarEmot, laggTill]);

  const avstangd = laddarUpp(chips);

  return (
    <>
      <form
        className={
          variant === "desktop"
            ? "shrink-0 border-t border-bok-linje px-[38px] pb-5 pt-4"
            : "shrink-0 px-[18px] pb-[18px] pt-3"
        }
        onSubmit={async (e) => {
          e.preventDefault();
          const skickad = text.trim();
          if (skickar || !onSkicka || !kanSkicka(text, chips)) return;
          const bifogade = bilagor(chips);
          // Kontoutdragen är redan inlästa; meddelandet säger vad de gav.
          const notiser = kontoutdragsnotiser(chips);
          const sand = [skickad, ...notiser].filter((t) => t !== "").join("\n");
          setSkickar(true);
          try {
            const ok = bifogade.length > 0 ? await onSkicka(sand, bifogade) : await onSkicka(sand);
            if (ok) {
              // Har människan hunnit skriva något nytt medan anropet var i
              // flykt är det hennes nästa fråga, inte den som skickades.
              setText((nu) => (nu.trim() === skickad ? "" : nu));
              // De skickade chipen går; ett felchip står kvar tills det tas bort.
              setChips((cs) =>
                cs.filter(
                  (c) => !arInlastKontoutdrag(c) && !(c.lage === "klar" && c.id !== null && bifogade.includes(c.id))
                )
              );
            }
          } finally {
            setSkickar(false);
          }
        }}
      >
        <div
          data-drar-over={drarOver ? "true" : undefined}
          className={`flex flex-col gap-[10px] rounded-[12px] border bg-bok-yta-falt px-4 py-[13px] ${
            drarOver ? "border-solid border-bok-text-svag" : "border-dashed border-bok-kant-streckad"
          }`}
        >
          {chips.length > 0 && (
            <ul aria-label="Bifogade filer" className="m-0 flex list-none flex-wrap gap-2 p-0">
              {chips.map((c) => (
                <li
                  key={c.nyckel}
                  data-testid="filchip"
                  data-lage={c.lage}
                  className={`bok-mono flex max-w-full items-center gap-2 rounded-full border px-[10px] py-1 text-[12px] ${
                    c.lage === "fel"
                      ? "border-bok-fel-kant bg-bok-fel-yta text-bok-fel-meta"
                      : "border-bok-linje bg-bok-linje-svagast text-bok-text-dampad"
                  }`}
                >
                  <span className="min-w-0 truncate">
                    {c.namn} · {filMeta(c.storlek, null)} · {chipStatus(c)}
                  </span>
                  <button
                    type="button"
                    aria-label={`Ta bort ${c.namn}`}
                    onClick={() => setChips((cs) => cs.filter((x) => x.nyckel !== c.nyckel))}
                    className="shrink-0 text-bok-text-svag hover:text-bok-text"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex items-center gap-3">
            <label htmlFor={faltId} className="sr-only">
              {etikett}
            </label>
            <input
              ref={ref}
              id={faltId}
              name="skal-chattfalt"
              type="text"
              autoComplete="off"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onPaste={(e) => {
                // Bara filer tas om hand; text klistras in som vanligt.
                const filer = e.clipboardData?.files;
                if (!tarEmot || !filer || filer.length === 0) return;
                e.preventDefault();
                laggTill(filer);
              }}
              placeholder={etikett}
              className="min-w-0 flex-1 bg-transparent text-[15px] text-bok-text outline-none placeholder:text-[#71717a]"
            />
            <button
              type="button"
              aria-label="Bifoga underlag"
              disabled={!tarEmot}
              onClick={() => filvaljare.current?.click()}
              className="bok-mono shrink-0 text-[12px] text-bok-meta hover:text-bok-text disabled:cursor-default disabled:hover:text-bok-meta"
            >
              <PappersklammerIkon />
            </button>
            <span
              aria-hidden="true"
              data-testid="chattfalt-enter"
              data-avstangd={avstangd ? "true" : "false"}
              className={`bok-mono text-[12px] ${avstangd ? "text-bok-kant-streckad" : "text-bok-meta"}`}
            >
              ↵
            </span>
          </div>
        </div>
      </form>
      {/* Utanför formuläret: ett andra `input` i det stänger av Enter som
          implicit sändning, och filväljaren skickar ändå ingenting själv. */}
      <input
        ref={filvaljare}
        type="file"
        tabIndex={-1}
        aria-hidden="true"
        className="hidden"
        multiple={variant === "desktop"}
        accept={variant === "mobil" ? "image/*" : ACCEPT_DESKTOP}
        {...(variant === "mobil" ? { capture: "environment" as const } : {})}
        onChange={(e) => {
          laggTill(e.target.files);
          // Samma fil två gånger i rad ska också ge ett `change`.
          e.target.value = "";
        }}
      />
    </>
  );
});

function PappersklammerIkon() {
  return (
    <svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  );
}
