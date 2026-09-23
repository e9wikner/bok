"use client";

import { useCallback, useRef } from "react";
import { ChattFaltFokus, TradRenderare } from "@/components/chattyta/TradRenderare";
import { ChattFalt } from "@/components/skal/ChattFalt";
import { useTrad, type UseTrad } from "@/hooks/useTrad";

/**
 * Chattkolumnen som SKAL.
 *
 * Tråden är padding 26/38, gap 24 och BOTTENANKRAD (justify-content:
 * flex-end) så att det senaste ligger vid inmatningsfältet. Textrader max
 * 54ch, kort max-bredd 560.
 *
 * Skalet äger layouten; innehållet är `chattyta`s. Tråden kommer ur
 * `useTrad` och ritas av `TradRenderare` (SPEC-chattyta.md §5, §6), som bär
 * kortens kontrakt: ingen förvald rekommendation, alltid en väg ut, alltid
 * båda talen. Skalet ritar inga inlägg själv.
 */

/** Det ytan behöver ur tråden. `skicka` går till fältet, inte hit. */
export type TradData = Pick<UseTrad, "inlagg" | "strommande" | "fel">;

/**
 * En tråd som inte läses (en inaktiv vy). Tomt är ett ärligt läge här: vyn
 * ligger utanför skärmen och är `aria-hidden` i svepraden.
 */
export const OLAST_TRAD: TradData = { inlagg: [], strommande: null, fel: null };

/**
 * `fel` ur `useTrad` som en rad: kort, neutral, utan stacktrace. Ett
 * misslyckat POST har redan tagit bort det optimistiska inlägget och lämnat
 * texten i fältet (C3), så raden behöver bara säga att kontakten brast.
 */
function felText(fel: unknown): string {
  const status = (fel as { response?: { status?: unknown } } | null)?.response?.status;
  return typeof status === "number"
    ? `tråden kunde inte nås · servern svarade ${status}`
    : "tråden kunde inte nås · inget svar från servern";
}

/**
 * Trådytan, delad av desktopkolumnen och mobilens `ChattList`. Tar datan som
 * props så att `ChattList` kan läsa tråden EN gång och ge både märket och
 * ytan samma svar — två `useTrad` på samma vy vore två strömmar.
 *
 * Laddning ritas inte: ingen spinner (README.md), och en tom tråd medan GET
 * är i flykt ljuger inte om något.
 */
export function TradYta({
  vyTitel,
  viewKey,
  trad,
  variant = "desktop",
}: {
  vyTitel: string;
  /** Beslutskortens status läses per vy (SPEC-chattyta.md §7). */
  viewKey: string;
  trad: TradData;
  variant?: "desktop" | "mobil";
}) {
  return (
    <div
      // `[&>*]:shrink-0`: ett kort med `overflow-hidden` får annars flexens
      // `min-height: 0`, krymper, och klipper sin sista rad — i
      // AlternativLista vägen ut (hittat vid chattyta C14:s visuella kontroll).
      className={
        variant === "desktop"
          ? "flex flex-1 flex-col justify-end gap-6 overflow-hidden px-[38px] py-[26px] [&>*]:shrink-0"
          : "bok-dold-skroll flex h-[260px] flex-col gap-[18px] overflow-auto border-t border-bok-linje-svagast px-[18px] pb-[18px] pt-4 [&>*]:shrink-0"
      }
      // INTE en live-region: då lästes varje text-delta upp ord för ord.
      // Annonseringen bor i `TradRenderare`s dolda region (SPEC-chattyta
      // §11, testfall 31) — indikatorbyten och färdiga inlägg, inget annat.
      role="region"
      aria-label={`Tråd för ${vyTitel}`}
    >
      <TradRenderare inlagg={trad.inlagg} strommande={trad.strommande} viewKey={viewKey} />
      {trad.fel != null && (
        <p data-testid="trad-fel" className="bok-mono m-0 text-[12px] text-bok-text-svag">
          {felText(trad.fel)}
        </p>
      )}
    </div>
  );
}

/**
 * Desktopkolumnen: tråden och fältet.
 *
 * `aktiv` styr om tråden läses alls. Svepraden renderar sidans alla vyer,
 * men SPEC-chattyta.md §6.2 punkt 5 säger en ström per flik — den aktiva
 * vyns. Hooken kan inte anropas villkorligt, så läsningen bor i en egen
 * komponent som bara monteras för den aktiva vyn.
 */
export function ChattKolumn({
  vyTitel,
  viewKey,
  aktiv = true,
}: {
  vyTitel: string;
  viewKey: string;
  aktiv?: boolean;
}) {
  if (!aktiv) return <KolumnLayout vyTitel={vyTitel} viewKey={viewKey} trad={OLAST_TRAD} />;
  return <AktivKolumn vyTitel={vyTitel} viewKey={viewKey} />;
}

function AktivKolumn({ vyTitel, viewKey }: { vyTitel: string; viewKey: string }) {
  const trad = useTrad(viewKey);
  return <KolumnLayout vyTitel={vyTitel} viewKey={viewKey} trad={trad} onSkicka={trad.skicka} />;
}

function KolumnLayout({
  vyTitel,
  viewKey,
  trad,
  onSkicka,
}: {
  vyTitel: string;
  viewKey: string;
  trad: TradData;
  onSkicka?: UseTrad["skicka"];
}) {
  // Förslagskortets `Ändra` ska till DEN HÄR kolumnens fält (chattyta C12).
  const falt = useRef<HTMLInputElement>(null);
  const fokuseraFalt = useCallback(() => falt.current?.focus(), []);
  return (
    <div className="flex min-h-0 flex-col border-r border-bok-linje">
      <ChattFaltFokus.Provider value={fokuseraFalt}>
        <TradYta vyTitel={vyTitel} viewKey={viewKey} trad={trad} />
      </ChattFaltFokus.Provider>
      <ChattFalt ref={falt} vyTitel={vyTitel} onSkicka={onSkicka} />
    </div>
  );
}
