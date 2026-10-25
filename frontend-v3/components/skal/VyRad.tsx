"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { LasKnapp } from "@/components/skal/LasKnapp";
import { useBeslutFokus } from "@/components/skal/BeslutFokus";
import { useDetalj } from "@/components/skal/DetaljKontext";
import { aldersTon } from "@/lib/chattyta/alder";
import { BESLUT_NYCKEL, forsokIgenMedUnderlag, type BeslutSvar } from "@/lib/chattyta/api";
import { oppnaKvitto } from "@/lib/skal/bocker";
import type { RadMal } from "@/lib/skal/detalj";
import type { LasData } from "@/lib/skal/las";
import type { RadVariant, VyRadData } from "@/lib/skal/vydata";

/**
 * `VyRad` (komponenter.md): padding 9/8, margin 0 -8, radius 6,
 * border-bottom 1px #f4f4f5. Vänster titel 14 + metarad mono 11.
 * Höger mono 14 tabular.
 *
 * OBS namnkrock: det här är EN RAD I VYN. Raden AV VYER heter `VySvep`.
 * Mappningen står i SPEC-skal.md §6.
 */

/**
 * `ny`-markeringen är kortvarig. Annars färgas listan grön över tiden och
 * grönt slutar betyda "postat och låst" — en av de två toner som bär
 * betydelse. Varaktigheten står på ETT ställe.
 *
 * Talet självt är inte taget: designen säger "kortvarig" och inget mer
 * (SPEC-skal.md öppen fråga 3).
 */
export const NY_MARKERING_MS = 6000;

const MAL_TITEL: Record<RadMal["typ"], string> = {
  konto: "Öppna huvudboken",
  ver: "Öppna verifikationen",
  vy: "Gå till vyn",
};

const META_FARG: Record<RadVariant, string> = {
  normal: "var(--bok-meta)",
  saknar: "var(--bok-vantar-meta)",
  vantar: "var(--bok-vantar-meta)",
  pagaende: "var(--bok-meta)",
  ny: "var(--bok-klart-meta)",
  fel: "var(--bok-fel-meta)",
  paverkad: "var(--bok-vantar-meta)",
};

/**
 * `saknar` och `vantar` är de två raderna som väntar på människan; bara de
 * blir röda med åldern (SPEC-chattyta.md §10). Utan `ageDays` gäller
 * tabellen ovan, så en rad som inte vet sin ålder aldrig gissas röd.
 */
const ALDRANDE = new Set<RadVariant>(["saknar", "vantar"]);
const TON_FARG = { vantar: "var(--bok-vantar-meta)", forfallen: "var(--bok-fel-meta)" } as const;

function metaFarg(variant: RadVariant, ageDays: number | undefined): string {
  if (ageDays === undefined || !ALDRANDE.has(variant)) return META_FARG[variant];
  return TON_FARG[aldersTon(ageDays)];
}

export function VyRad({
  titel,
  meta,
  hoger,
  variant = "normal",
  summa = false,
  storlek = "desktop",
  ageDays,
  kvitto,
  forsokIgen,
  beslut,
  fraga,
  lankar,
  las,
  mal,
  traff,
}: {
  titel: string;
  meta?: string;
  hoger: string;
  variant?: RadVariant;
  summa?: boolean;
  storlek?: "desktop" | "mobil";
  /** Serverns `age_days`; färgar metaraden för `saknar`/`vantar` (§10). */
  ageDays?: number;
  /** Länken till verifikationens kvitto (SPEC-flode-underlag.md §10.4, FU23). */
  kvitto?: { voucherId: string; nummer: string };
  /** Ett underlag agenten avstod från: länken `försök igen` i metaraden. */
  forsokIgen?: { sourceId: string };
  /** Ett öppet beslut: titeln tar upp det i chatten. */
  beslut?: BeslutSvar;
  /** Ingen kort ännu: `be agenten` i metaraden fyller vyns chattfält. */
  fraga?: VyRadData["fraga"];
  /** Kedjans andra steg, som länkar i metaraden. */
  lankar?: VyRadData["lankar"];
  /** Ett lås sist på raden, efter högerkolumnen. */
  las?: LasData;
  /**
   * Vart titeln leder: huvudboken, verifikationen eller en annan vy. Bara
   * titeln är knappen, så att `kvitto` och `försök igen` i metaraden förblir
   * egna tryck.
   */
  mal?: RadMal;
  /** Sökrutans träff: de matchade tecknen markeras. */
  traff?: VyRadData["traff"];
}) {
  // Markeringen tas bort av sig själv; raden ligger kvar.
  const [nyAktiv, setNyAktiv] = useState(variant === "ny");
  useEffect(() => {
    if (variant !== "ny") return;
    setNyAktiv(true);
    const t = setTimeout(() => setNyAktiv(false), NY_MARKERING_MS);
    return () => clearTimeout(t);
  }, [variant]);

  const { valt, valj, fyll } = useBeslutFokus();
  const detalj = useDetalj();
  const pagaende = variant === "pagaende";
  const yta = nyAktiv ? "var(--bok-klart-yta)" : pagaende ? "var(--bok-yta-svag)" : undefined;
  const textFarg = pagaende ? "var(--bok-meta)" : undefined;

  return (
    <div
      data-variant={variant}
      data-ny={nyAktiv ? "true" : undefined}
      className={`flex items-baseline justify-between gap-[14px] border-b border-bok-linje-svagast ${
        storlek === "desktop" ? "-mx-2 rounded-md px-2 py-[9px]" : "py-[11px]"
      }`}
      style={{ background: yta }}
    >
      <span className="flex min-w-0 flex-col gap-[2px]">
        {beslut ? (
          <button
            type="button"
            data-testid="vyrad-beslut"
            aria-pressed={valt?.id === beslut.id}
            onClick={() => valj(beslut)}
            title="Ta upp i chatten"
            className={`min-w-0 cursor-pointer break-words text-left underline-offset-[3px] hover:underline ${
              storlek === "desktop" ? "text-[14px]" : "text-[15px]"
            } ${valt?.id === beslut.id ? "underline" : ""}`}
          >
            <Markerad text={titel} index={traff?.titel} />
          </button>
        ) : mal && detalj ? (
          <button
            type="button"
            data-testid="vyrad-oppna"
            onClick={() => detalj.oppna(mal)}
            title={MAL_TITEL[mal.typ]}
            className={`min-w-0 cursor-pointer break-words text-left underline-offset-[3px] hover:underline ${
              storlek === "desktop" ? "text-[14px]" : "text-[15px]"
            }`}
            style={{ color: textFarg, fontWeight: summa ? 500 : undefined }}
          >
            <Markerad text={titel} index={traff?.titel} />
          </button>
        ) : (
          <span
            className={storlek === "desktop" ? "text-[14px]" : "text-[15px]"}
            style={{ color: textFarg, fontWeight: summa ? 500 : undefined }}
          >
            <Markerad text={titel} index={traff?.titel} />
          </span>
        )}
        {(meta || kvitto || forsokIgen || fraga || (lankar && detalj)) && (
          <span
            className={`bok-mono ${storlek === "desktop" ? "text-[11px]" : "text-[12px]"}`}
            style={{ color: metaFarg(variant, ageDays) }}
          >
            {meta && <Markerad text={meta} index={traff?.meta} />}
            {kvitto && <KvittoLank {...kvitto} forsta={!meta} />}
            {forsokIgen && <ForsokIgenLank {...forsokIgen} forsta={!meta && !kvitto} />}
            {fraga && (
              <MetaLank
                text="be agenten"
                titel="Fyll i chattfältet"
                forsta={!meta && !kvitto && !forsokIgen}
                onTryck={() => fyll(fraga.viewKey, fraga.text)}
              />
            )}
            {detalj &&
              lankar?.map((l, i) => (
                <MetaLank
                  key={`${l.text}-${i}`}
                  text={l.text}
                  titel={MAL_TITEL[l.mal.typ]}
                  forsta={!meta && !kvitto && !forsokIgen && !fraga && i === 0}
                  onTryck={() => detalj.oppna(l.mal)}
                />
              ))}
          </span>
        )}
      </span>
      <span
        className={`bok-mono bok-tal whitespace-nowrap ${
          storlek === "desktop" ? "text-[14px]" : "text-[15px]"
        }`}
        style={{ color: textFarg, fontWeight: summa ? 500 : undefined }}
      >
        <Markerad text={hoger} index={traff?.hoger} />
        {las && (
          <span className={hoger ? "ml-[10px]" : undefined}>
            <LasKnapp {...las} />
          </span>
        )}
      </span>
    </div>
  );
}

/**
 * Texten med sökträffens tecken markerade, som telescope gör. Utan index
 * är det bara texten.
 */
function Markerad({ text, index }: { text: string; index?: number[] }) {
  if (!index || index.length === 0) return <>{text}</>;
  const traff = new Set(index);
  const delar: { text: string; traff: boolean }[] = [];
  for (let i = 0; i < text.length; i++) {
    const t = traff.has(i);
    const sista = delar[delar.length - 1];
    if (sista && sista.traff === t) sista.text += text[i];
    else delar.push({ text: text[i], traff: t });
  }
  return (
    <>
      {delar.map((d, i) =>
        d.traff ? (
          <mark key={i} className="bg-transparent font-semibold text-bok-lank">
            {d.text}
          </mark>
        ) : (
          <span key={i}>{d.text}</span>
        )
      )}
    </>
  );
}

/** En länk i metaraden, som `kvitto`: `be agenten`, `betalning`. */
function MetaLank({
  text,
  titel,
  forsta,
  onTryck,
}: {
  text: string;
  titel: string;
  forsta: boolean;
  onTryck: () => void;
}) {
  return (
    <>
      {!forsta && " · "}
      <button
        type="button"
        title={titel}
        onClick={onTryck}
        className="text-bok-lank underline-offset-2 hover:text-bok-lank-hover hover:underline"
      >
        {text}
      </button>
    </>
  );
}

/**
 * `kvitto`, som en länk i metaraden. Källan slås upp i `source-context` när
 * den trycks (`oppnaKvitto`), inte när raden ritas. Utan kvitto, eller vid
 * ett fel, säger länken det i stället för att öppna ett tomt fönster.
 */
function KvittoLank({ voucherId, nummer, forsta }: { voucherId: string; nummer: string; forsta: boolean }) {
  const [lage, setLage] = useState<"redo" | "saknas" | "fel">("redo");
  return (
    <>
      {!forsta && " · "}
      <button
        type="button"
        aria-label={`Öppna kvittot till ${nummer}`}
        onClick={() => {
          setLage("redo");
          oppnaKvitto(voucherId)
            .then((fanns) => setLage(fanns ? "redo" : "saknas"))
            .catch(() => setLage("fel"));
        }}
        className="text-bok-lank underline-offset-2 hover:text-bok-lank-hover hover:underline"
      >
        {lage === "saknas" ? "inget kvitto" : lage === "fel" ? "kunde inte öppnas" : "kvitto"}
      </button>
    </>
  );
}

/**
 * `försök igen`: underlaget läggs tillbaka i intagskön (`POST /intake/{id}/retry`)
 * och agenten läser om det med instruktionerna som de är nu. Beslutslistan
 * hämtas om, så raden försvinner när servern inte längre har den öppen.
 * Länken säger vad som hände i stället för att låtsas att något bokförts.
 */
function ForsokIgenLank({ sourceId, forsta }: { sourceId: string; forsta: boolean }) {
  const queryClient = useQueryClient();
  const [lage, setLage] = useState<"redo" | "skickar" | "skickat" | "vantar" | "fel">("redo");
  const text = {
    redo: "försök igen",
    skickar: "skickar…",
    skickat: "agenten läser om",
    vantar: "i kön till nästa pass",
    fel: "gick inte, försök igen",
  }[lage];
  return (
    <>
      {!forsta && " · "}
      <button
        type="button"
        disabled={lage === "skickar" || lage === "skickat" || lage === "vantar"}
        onClick={() => {
          setLage("skickar");
          forsokIgenMedUnderlag(sourceId)
            .then((svar) => {
              setLage(svar.pass_started ? "skickat" : "vantar");
              return queryClient.invalidateQueries({ queryKey: BESLUT_NYCKEL });
            })
            .catch(() => setLage("fel"));
        }}
        className="text-bok-lank underline-offset-2 hover:text-bok-lank-hover hover:underline disabled:no-underline disabled:opacity-70"
      >
        {text}
      </button>
    </>
  );
}

/**
 * Laddning är skelettrader med SAMMA radhöjd, aldrig en spinner över hela
 * ytan (README.md §Tillstånd). Samma höjd gör att listan inte hoppar när
 * data landar.
 */
export function VyRadSkelett({ antal = 4 }: { antal?: number }) {
  return (
    <div aria-hidden="true" data-testid="vyrad-skelett">
      {Array.from({ length: antal }).map((_, i) => (
        <div
          key={i}
          className="-mx-2 flex items-baseline justify-between gap-[14px] border-b border-bok-linje-svagast px-2 py-[9px]"
        >
          <span className="flex min-w-0 flex-col gap-[2px]">
            <span className="block h-[14px] w-[160px] rounded bg-bok-linje-svagast" />
            <span className="block h-[11px] w-[90px] rounded bg-bok-linje-svagast" />
          </span>
          <span className="block h-[14px] w-[70px] rounded bg-bok-linje-svagast" />
        </div>
      ))}
    </div>
  );
}
