"use client";

import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { VyBanner } from "@/components/skal/VyBanner";
import { VyHeaderStatus } from "@/components/skal/VyHeaderStatus";
import { VyRad, VyRadSkelett } from "@/components/skal/VyRad";
import { VyGrupp, VySektion } from "@/components/skal/VySektion";
import type { Sortering } from "@/lib/skal/bocker";
import { lageFarg } from "@/lib/skal/lage";
import type { VyData, VyRadData } from "@/lib/skal/vydata";

/**
 * Läskolumnen: rubrikrad, period, eventuell banner, sektioner med rader och
 * en fottext som säger vad agenten gör härnäst.
 *
 * En läsvy (`lasvy`) får ingen primärknapp i foten — och ingen avstängd
 * knapp och ingen "kommer snart"-text heller. En yta som lovar en funktion
 * som inte finns är sämre än en yta som inte lovar den.
 */
export function VyInnehall({
  vy,
  data,
  laddar = false,
  variant = "desktop",
  tillbaka,
  sok,
  atgard,
}: {
  /** En vy, eller detaljlagret (`Detalj.tsx`) som bara har en titel. */
  vy: { titel: string };
  data: VyData;
  laddar?: boolean;
  variant?: "desktop" | "mobil";
  /** Detaljlagrets länk tillbaka till det under, ovanför rubriken. */
  tillbaka?: { text: string; onClick: () => void };
  /**
   * Sökrutan under perioden (Verifikationer), med sorteringen bredvid när
   * den ges. Filtreringen och sorteringen sker i `useVyer`.
   */
  sok?: {
    varde: string;
    onAndra: (s: string) => void;
    sortering?: Sortering;
    onSortera?: (s: Sortering) => void;
  };
  /** En åtgärd under fottexten, t.ex. `Kasta utkast` i detaljlagret. */
  atgard?: ReactNode;
}) {
  const fg = lageFarg(data.lage);
  // En månad utan verifikationer står kvar för låsets skull; den går att dölja.
  const [doljTomma, setDoljTomma] = useState(false);
  const tommaManader = data.sektioner.filter((s) => s.tom && s.rader.length === 0).length;
  const sektioner = doljTomma
    ? data.sektioner.filter((s) => !(s.tom && s.rader.length === 0))
    : data.sektioner;

  return (
    <div
      className={
        variant === "desktop"
          ? "flex min-h-0 flex-col bg-bok-yta"
          : "bok-dold-skroll flex min-h-0 flex-1 flex-col overflow-auto"
      }
    >
      {tillbaka && (
        <button
          type="button"
          onClick={tillbaka.onClick}
          className={`bok-mono self-start pt-3 text-left text-[12px] text-bok-lank underline-offset-2 hover:text-bok-lank-hover hover:underline ${
            variant === "desktop" ? "px-6" : "px-[18px]"
          }`}
        >
          ← {tillbaka.text}
        </button>
      )}
      <VyHeaderStatus titel={vy.titel} status={data.status} fg={fg} variant={variant} />

      <div
        // pb: plats under sista raden för chattbubblan (`ChattBubbla`), som
        // på desktop når 120 px upp från nederkanten.
        className={
          variant === "desktop"
            ? "bok-dold-skroll flex min-h-0 flex-1 flex-col overflow-auto px-6 pb-[136px] pt-1"
            : "flex flex-col px-[18px] bok-mobil-botten"
        }
      >
        <div className="bok-mono pt-[14px] text-[12px] text-bok-meta">{data.period}</div>

        {sok && (
          <div className="mt-[14px] flex gap-2">
            <input
              type="search"
              value={sok.varde}
              onChange={(e) => sok.onAndra(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") sok.onAndra("");
              }}
              placeholder="Sök verifikation…"
              aria-label="Sök bland verifikationerna"
              autoComplete="off"
              spellCheck={false}
              className="bok-mono min-w-0 flex-1 rounded-md border border-bok-linje bg-bok-yta px-3 py-[7px] text-[13px] text-bok-text placeholder:text-bok-meta focus:border-bok-lank focus:outline-none"
            />
            {sok.sortering && sok.onSortera && (
              <SorteringsVal sortering={sok.sortering} onSortera={sok.onSortera} />
            )}
          </div>
        )}

        {tommaManader > 0 && (
          <button
            type="button"
            onClick={() => setDoljTomma((d) => !d)}
            aria-pressed={doljTomma}
            className="bok-mono mt-[10px] self-start text-left text-[12px] text-bok-lank underline-offset-2 hover:text-bok-lank-hover hover:underline"
          >
            {doljTomma ? `Visa tomma månader (${tommaManader})` : "Dölj tomma månader"}
          </button>
        )}

        {data.banner && (
          <div className="mt-[14px]">
            <VyBanner ton={data.banner.ton} text={data.banner.text} />
          </div>
        )}

        {laddar ? (
          <div className="pt-5">
            <VyRadSkelett />
          </div>
        ) : (
          sektioner.map((sektion) => (
            <VySektion
              key={sektion.titel}
              titel={sektion.titel}
              antalRader={sektion.rader.length}
              variant={variant}
              las={sektion.las}
              tom={sektion.tom}
              kolumner={sektion.kolumner}
            >
              {medGrupper(sektion.rader).map(({ rad, grupp }) => (
                <Fragment key={rad.id}>
                  {grupp && <VyGrupp titel={grupp} variant={variant} />}
                  <VyRad
                  titel={rad.titel}
                  meta={rad.meta}
                  // Summorna får en tom nummerkolumn, så att titlarna står i linje.
                  nummer={rad.nummer ?? (sektion.rader.some((r) => r.nummer) ? "" : undefined)}
                  hoger={rad.hoger}
                  variant={rad.variant}
                  summa={rad.summa}
                  struken={rad.struken}
                  hogerFore={rad.hogerFore}
                  kolumner={rad.kolumner}
                  kolumnRubriker={sektion.kortRubriker ?? sektion.kolumner}
                  ageDays={rad.ageDays}
                  kvitto={rad.kvitto}
                  forsokIgen={rad.forsokIgen}
                  kopplaLonebesked={rad.kopplaLonebesked}
                  bokforLon={rad.bokforLon}
                  betalning={rad.betalning}
                  beslut={rad.beslut}
                  fraga={rad.fraga}
                  underlagsval={rad.underlagsval}
                  lankar={rad.lankar}
                  inlagg={rad.inlagg}
                  las={rad.las}
                  mal={rad.mal}
                  traff={rad.traff}
                  storlek={variant}
                  />
                </Fragment>
              ))}
            </VySektion>
          ))
        )}

        {!laddar && data.harFler && data.hamtaFler && <LaddarFler hamtaFler={data.hamtaFler} />}

        <div className="pt-5 text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">
          {data.fot}
        </div>
        {atgard}
      </div>
    </div>
  );
}

const KONTROLL =
  "bok-mono rounded-md border border-bok-linje bg-bok-yta px-2 py-[7px] text-[13px] text-bok-text hover:border-bok-lank focus:border-bok-lank focus:outline-none";

/** Sortera Postade på datum eller verifikationsnummer, stigande eller fallande. */
function SorteringsVal({
  sortering,
  onSortera,
}: {
  sortering: Sortering;
  onSortera: (s: Sortering) => void;
}) {
  const stigande = sortering.ordning === "stigande";
  return (
    <>
      <select
        value={sortering.falt}
        onChange={(e) => onSortera({ ...sortering, falt: e.target.value as Sortering["falt"] })}
        aria-label="Sortera på"
        className={KONTROLL}
      >
        <option value="datum">Datum</option>
        <option value="nummer">Ver.nr</option>
      </select>
      <button
        type="button"
        onClick={() => onSortera({ ...sortering, ordning: stigande ? "fallande" : "stigande" })}
        aria-label={stigande ? "Stigande ordning, byt till fallande" : "Fallande ordning, byt till stigande"}
        title={stigande ? "Stigande" : "Fallande"}
        className={`${KONTROLL} w-[34px] text-center`}
      >
        {stigande ? "↑" : "↓"}
      </button>
    </>
  );
}

/**
 * Varje rad med den mellanrubrik som ska stå före den: där raderna byter
 * grupp. En sektion med bara en grupp får ingen — rubriken skulle bara
 * upprepa sektionens. Rader utan grupp (summor) bryter inte gruppen.
 */
export function medGrupper(rader: VyRadData[]): { rad: VyRadData; grupp?: string }[] {
  const grupper = new Set(rader.map((r) => r.grupp).filter(Boolean));
  let forra: string | undefined;
  return rader.map((rad) => {
    if (grupper.size < 2 || !rad.grupp || rad.grupp === forra) return { rad };
    forra = rad.grupp;
    return { rad, grupp: rad.grupp };
  });
}

/**
 * Vakten sist i listan: när raden syns hämtas
 * nästa sida. Observatören görs om när `hamtaFler` byts — efter varje
 * hämtad sida — så att en vakt som fortfarande syns ber om nästa.
 */
function LaddarFler({ hamtaFler }: { hamtaFler: () => void }) {
  const vakt = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = vakt.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const observator = new IntersectionObserver(
      (poster) => {
        if (poster.some((p) => p.isIntersecting)) hamtaFler();
      },
      { rootMargin: "200px 0px" }
    );
    observator.observe(el);
    return () => observator.disconnect();
  }, [hamtaFler]);

  return (
    <div ref={vakt} className="bok-mono pt-4 text-[12px] text-bok-meta" aria-live="polite">
      Laddar fler…
    </div>
  );
}
