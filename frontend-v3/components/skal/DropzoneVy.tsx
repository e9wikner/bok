"use client";

import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useBeslutFokus } from "@/components/skal/BeslutFokus";
import { useDetalj } from "@/components/skal/DetaljKontext";
import { useBeslut } from "@/hooks/useBeslut";
import { useDropzoneOversikt } from "@/hooks/useDropzone";
import { VyBanner } from "@/components/skal/VyBanner";
import { VyHeaderStatus } from "@/components/skal/VyHeaderStatus";
import { VySektion } from "@/components/skal/VySektion";
import {
  DROPZONE_NYCKEL,
  type DropzoneInlast,
  type DropzoneVantande,
  type DropzoneMal,
  type DropzoneOversikt,
  type Mappnod,
  dropzoneApi,
  dropzoneStatus,
  felText,
  harStannat,
  malAccept,
  malBeskrivning,
  mapptrad,
  storlek,
  tidpunkt,
  utfallText,
  vantarText,
} from "@/lib/skal/dropzone";
import { lageFarg } from "@/lib/skal/lage";
import type { Vynyckel } from "@/lib/skal/vyer";

/** Tråden bredvid dropzonen (`vyer.ts`): ett beslut där tas upp utan vybyte. */
const DROPZONENS_TRAD = "bocker.verifikationer";

/**
 * Dropzonen (`bocker.dropzone`): SMB-utdelningens mappar i webben.
 *
 * Mapparna visas som i utdelningen, och mappen är hela klassningen: en fil
 * som läggs i `Kvitton/` blir ett kvitto, en i `Kontoutdrag/` ett kontoutdrag
 * för kontot filnamnet börjar med (`1930 oktober.csv`). Släpp en eller flera filer på en mapp, eller tryck på
 * den för filväljaren (flera filer går att välja). Filerna skrivs i mappen på
 * servern i ett anrop och läses in av mappskannern vid nästa varv — samma
 * `_Inläst/` och `_Problem/` som en fil som kopierats dit i Finder. Därför
 * står det "lagd i", inte "inläst": inläsningen är skannerns.
 */

interface Slappt {
  id: number;
  namn: string;
  mapp: string;
  tillstand: "laddar" | "klar" | "fel";
  text?: string;
}

let slappnummer = 0;

export function DropzoneVy({ titel, variant }: { titel: string; variant: "desktop" | "mobil" }) {
  const { data, isError, dataUpdatedAt } = useDropzoneOversikt();
  const queryClient = useQueryClient();
  const [slappta, setSlappta] = useState<Slappt[]>([]);
  const status = dropzoneStatus(data, isError, dataUpdatedAt);
  const pad = variant === "desktop" ? "px-6" : "px-[18px]";

  const slapp = useCallback(
    async (mal: DropzoneMal, filer: File[]) => {
      if (filer.length === 0) return;
      const ider = filer.map(() => ++slappnummer);
      setSlappta((s) => [
        ...filer.map((fil, i) => ({ id: ider[i], namn: fil.name, mapp: mal.folder, tillstand: "laddar" as const })),
        ...s,
      ]);
      try {
        const resultat = await dropzoneApi.slapp(mal.folder, filer);
        setSlappta((s) =>
          s.map((x): Slappt => {
            const i = ider.indexOf(x.id);
            if (i === -1) return x;
            const r = resultat[i];
            if (!r) return { ...x, tillstand: "fel", text: "servern svarade inte för filen" };
            return r.ok
              ? { ...x, namn: r.filename ?? x.namn, tillstand: "klar" }
              : { ...x, tillstand: "fel", text: r.error ?? "kunde inte läggas i mappen" };
          })
        );
      } catch (fel) {
        const text = felText(fel);
        setSlappta((s) => s.map((x): Slappt => (ider.includes(x.id) ? { ...x, tillstand: "fel", text } : x)));
      }
      void queryClient.invalidateQueries({ queryKey: DROPZONE_NYCKEL });
    },
    [queryClient]
  );

  return (
    <div
      className={
        variant === "desktop"
          ? "flex min-h-0 flex-col bg-bok-yta"
          : "bok-dold-skroll flex min-h-0 flex-1 flex-col overflow-auto"
      }
    >
      <VyHeaderStatus titel={titel} status={status.text} fg={lageFarg(status.lage)} variant={variant} />

      <div
        className={
          variant === "desktop"
            ? `bok-dold-skroll flex min-h-0 flex-1 flex-col overflow-auto pb-[136px] pt-1 ${pad}`
            : `flex flex-col bok-mobil-botten ${pad}`
        }
      >
        <div className="bok-mono pt-[14px] text-[12px] text-bok-meta">
          Samma mappar som den delade mappen (SMB). Mappen avgör vad filen blir.
        </div>

        {isError ? (
          <div className="mt-[14px]">
            <VyBanner ton="fel" text="Dropzonen kunde inte läsas. Ladda om sidan." />
          </div>
        ) : !data ? (
          <div className="bok-mono pt-5 text-[12px] text-bok-meta">Hämtar…</div>
        ) : (
          <Innehall data={data} nu={dataUpdatedAt} slappta={slappta} onSlapp={slapp} variant={variant} />
        )}
      </div>
    </div>
  );
}

function Innehall({
  data,
  nu,
  slappta,
  onSlapp,
  variant,
}: {
  data: DropzoneOversikt;
  nu: number;
  slappta: Slappt[];
  onSlapp: (mal: DropzoneMal, filer: File[]) => void;
  variant: "desktop" | "mobil";
}) {
  const banner = !data.enabled
    ? {
        ton: "fel" as const,
        text: "Mapphämtningen är avstängd på servern (DROPZONE_ENABLED). Filer kan inte läggas här förrän den är på.",
      }
    : harStannat(data, nu)
      ? {
          ton: "fel" as const,
          text: `Hämtningen från mappen verkar ha stannat${
            data.status.last_scan_at ? ` — senast ${tidpunkt(data.status.last_scan_at)}` : ""
          }. Filer som läggs här läses inte in förrän den går igång igen.`,
        }
      : null;
  const avstangd = !data.enabled;
  const noder = mapptrad(data.targets);

  return (
    <>
      {banner && (
        <div className="mt-[14px]">
          <VyBanner ton={banner.ton} text={banner.text} />
        </div>
      )}

      <VySektion titel="Mappar · släpp en eller flera filer" antalRader={noder.length} variant={variant}>
        <ul aria-label="Mappar i dropzonen" className="flex flex-col pt-1">
          {noder.map((nod) => (
            <Mapp
              key={nod.namn}
              nod={nod}
              avstangd={avstangd}
              onSlapp={onSlapp}
              vantande={(mal) => data.pending.filter((f) => f.folder === mal.folder)}
              vantarMeta={(f) => vantarText(f, data, nu)}
            />
          ))}
        </ul>
      </VySektion>

      <VySektion titel="Skickat härifrån" antalRader={slappta.length} variant={variant}>
        {slappta.map((s) => (
          <Rad
            key={s.id}
            titel={s.namn}
            meta={slapptMeta(s, data, nu)}
            ton={
              s.tillstand === "fel" || data.problems.some((p) => p.filename === s.namn)
                ? "fel"
                : s.tillstand === "klar"
                  ? "klar"
                  : "normal"
            }
          />
        ))}
      </VySektion>

      <VySektion titel="Väntar på hämtning" antalRader={data.pending.length} variant={variant}>
        {data.pending.map((f) => {
          const v = vantarText(f, data, nu);
          return (
            <Rad
              key={`${f.folder}/${f.filename}`}
              titel={f.filename}
              meta={`${f.folder}/ · ${v.text}`}
              hoger={storlek(f.size_bytes)}
              ton={v.sen ? "fel" : "normal"}
            />
          );
        })}
      </VySektion>

      <VySektion
        titel="Problem vid inläsning"
        antalRader={data.problems.filter((f) => !f.resolved).length}
        variant={variant}
      >
        {data.problems
          .filter((f) => !f.resolved)
          .map((f) => (
            <Rad
              key={`${f.folder}/${f.filename}`}
              titel={f.filename}
              meta={`${f.reason ?? "Avvisad, se .problem.txt bredvid filen."} · ${tidpunkt(f.modified_at)}`}
              ton="fel"
            />
          ))}
      </VySektion>

      <VySektion
        titel="Tidigare problem, lösta"
        antalRader={data.problems.filter((f) => f.resolved).length}
        variant={variant}
      >
        {data.problems
          .filter((f) => f.resolved)
          .map((f) => (
            <Rad
              key={`${f.folder}/${f.filename}`}
              titel={f.filename}
              meta={`löst: ${utfallText(f.outcome).text} · ${tidpunkt(f.modified_at)}`}
              ton="klar"
            />
          ))}
      </VySektion>

      <VySektion titel="Senast inlästa" antalRader={data.ingested.length} variant={variant}>
        {data.ingested.map((f) => (
          <InlastRad key={`${f.folder}/${f.filename}`} fil={f} />
        ))}
      </VySektion>

      <div className="pt-5 text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">
        En fil som läggs här hamnar i samma mapp som om den kopierats in via utdelningen. Skannern läser in
        den när den legat orörd i {data.quiet_seconds} s, flyttar den till _Inläst/ och agenten bokför den i
        Verifikationer. En fil som inte går att läsa hamnar under Problem med en förklaring. Ett kontoutdrag
        bokförs på kontot filnamnet börjar med, till exempel 1930 oktober.csv.
      </div>
    </>
  );
}

/**
 * Var en fil som skickats härifrån är nu. Filen följs i mappen: väntar den
 * fortfarande, har skannern läst in den, eller avvisat den. Namnet räcker —
 * servern ger aldrig två filer samma namn i en mapp.
 */
function slapptMeta(s: Slappt, data: DropzoneOversikt, nu: number): string {
  if (s.tillstand === "laddar") return `laddar upp till ${s.mapp}/`;
  if (s.tillstand === "fel") return s.text ?? "kunde inte läggas i mappen";
  const problem = data.problems.find((p) => p.filename === s.namn);
  if (problem) return `avvisad${problem.resolved ? " (löst)" : ""}${problem.reason ? ` · ${problem.reason}` : ""}`;
  const vantar = data.pending.find((p) => p.folder === s.mapp && p.filename === s.namn);
  if (vantar) return `i ${s.mapp}/ · ${vantarText(vantar, data, nu).text}`;
  const inlast = data.ingested.find((p) => p.filename === s.namn);
  if (inlast) return `inläst från ${s.mapp}/ · ${utfallText(inlast.outcome).text}`;
  return `lagd i ${s.mapp}/`;
}

/** En mapp på översta nivån, med sina undermappar indragna under sig. */
function Mapp({
  nod,
  avstangd,
  onSlapp,
  vantande,
  vantarMeta,
}: {
  nod: Mappnod;
  avstangd: boolean;
  onSlapp: (mal: DropzoneMal, filer: File[]) => void;
  vantande: (mal: DropzoneMal) => DropzoneVantande[];
  vantarMeta: (fil: DropzoneVantande) => { text: string; sen: boolean };
}) {
  return (
    <li className="flex flex-col">
      {nod.mal ? (
        <>
          <MappRad mal={nod.mal} namn={`${nod.namn}/`} avstangd={avstangd} onSlapp={onSlapp} />
          <VantandeFiler filer={vantande(nod.mal)} meta={vantarMeta} />
        </>
      ) : (
        <div className="flex items-center gap-[10px] border-b border-bok-linje-svagast py-[9px]">
          <MappIkon />
          <span className="bok-mono text-[14px] text-bok-text">{nod.namn}/</span>
          <span className="bok-mono text-[11px] text-bok-meta">lägg filen i en undermapp</span>
        </div>
      )}
      {nod.undermappar.length > 0 && (
        <ul className="flex flex-col pl-6">
          {nod.undermappar.map((u) => (
            <li key={u.mal.folder}>
              <MappRad mal={u.mal} namn={`${u.namn}/`} avstangd={avstangd} onSlapp={onSlapp} />
              <VantandeFiler filer={vantande(u.mal)} meta={vantarMeta} />
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** Filerna som väntar på skannern, direkt under mappen — "1 väntar" säger inte vilken fil. */
function VantandeFiler({
  filer,
  meta,
}: {
  filer: DropzoneVantande[];
  meta: (fil: DropzoneVantande) => { text: string; sen: boolean };
}) {
  if (filer.length === 0) return null;
  return (
    <ul aria-label="Väntar i mappen" className="flex flex-col gap-[2px] pb-[6px] pl-[38px] pr-2">
      {filer.map((f) => {
        const v = meta(f);
        return (
          <li key={f.filename} className="flex items-baseline justify-between gap-[14px]">
            <span className="flex min-w-0 items-baseline gap-2">
              <span className="truncate text-[13px] text-bok-text-2">{f.filename}</span>
              <span
                className="bok-mono shrink-0 text-[11px]"
                style={{ color: v.sen ? "var(--bok-fel-meta)" : "var(--bok-meta)" }}
              >
                {v.text}
              </span>
            </span>
            <span className="bok-mono shrink-0 text-[11px] tabular-nums text-bok-meta">{storlek(f.size_bytes)}</span>
          </li>
        );
      })}
    </ul>
  );
}

const harFiler = (dt: DataTransfer | null): boolean =>
  !!dt && Array.from(dt.types ?? []).includes("Files");

function MappRad({
  mal,
  namn,
  avstangd,
  onSlapp,
}: {
  mal: DropzoneMal;
  namn: string;
  avstangd: boolean;
  onSlapp: (mal: DropzoneMal, filer: File[]) => void;
}) {
  const [over, setOver] = useState(false);
  const valjare = useRef<HTMLInputElement>(null);

  return (
    <div
      onDragOver={(e) => {
        if (avstangd || !harFiler(e.dataTransfer)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        setOver(false);
        if (avstangd) return;
        e.preventDefault();
        onSlapp(mal, Array.from(e.dataTransfer.files ?? []));
      }}
      data-testid={`dropzone-mal-${mal.folder}`}
    >
      <button
        type="button"
        disabled={avstangd}
        onClick={() => valjare.current?.click()}
        aria-label={`Lägg filer i ${mal.folder}`}
        className={`flex w-full items-center gap-[10px] rounded-md border border-dashed px-2 py-[9px] text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
          over
            ? "border-bok-lank bg-bok-yta-svag"
            : "border-transparent hover:border-bok-linje hover:bg-bok-yta-svag"
        }`}
      >
        <MappIkon />
        <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
          <span className="bok-mono truncate text-[14px] text-bok-text">{namn}</span>
          <span className="bok-mono text-[11px] text-bok-meta">{malBeskrivning(mal)}</span>
        </span>
        {mal.pending_count > 0 && (
          <span className="bok-mono shrink-0 text-[11px] text-bok-meta">{mal.pending_count} väntar</span>
        )}
        <span className="bok-mono shrink-0 text-[11px] text-bok-lank">{over ? "släpp här" : "välj filer"}</span>
      </button>
      <input
        ref={valjare}
        type="file"
        multiple
        hidden
        accept={malAccept(mal)}
        onChange={(e) => {
          const filer = Array.from(e.target.files ?? []);
          e.target.value = "";
          onSlapp(mal, filer);
        }}
      />
    </div>
  );
}

function MappIkon() {
  return (
    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" className="shrink-0 text-bok-meta">
      <path
        d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4.38a1.5 1.5 0 0 1 1.06.44L11.5 7h8A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const TON = {
  normal: "var(--bok-meta)",
  klar: "var(--bok-klart-meta)",
  vantar: "var(--bok-vantar-meta)",
  fel: "var(--bok-fel-meta)",
} as const;

/**
 * En inläst fil, med vad som blev av den: verifikationerna den står bakom,
 * eller beslutet den väntar på. Ett tryck på beslutet tar upp kortet i
 * chatten, ett tryck på verifikationen öppnar den.
 */
function InlastRad({ fil }: { fil: DropzoneInlast }) {
  const utfall = fil.outcome;
  const { text, ton } = utfallText(utfall);
  const beslutRef = utfall?.kind === "underlag" ? utfall.decision : null;
  const uppslag = useBeslut(beslutRef?.view_key);
  const beslut = beslutRef ? uppslag?.get(beslutRef.id) : undefined;
  const { valj } = useBeslutFokus();
  const detalj = useDetalj();

  const lankar: { text: string; titel: string; onTryck: () => void }[] = [];
  if (beslut && beslut.status === "open") {
    lankar.push({
      text: "visa beslutet",
      titel: "Ta upp i chatten",
      onTryck: () => {
        valj(beslut);
        if (beslut.view_key !== DROPZONENS_TRAD) detalj?.oppna({ typ: "vy", key: beslut.view_key as Vynyckel });
      },
    });
  }
  if (utfall?.kind === "underlag" && detalj) {
    for (const v of utfall.vouchers) {
      if (v.number === null) continue;
      lankar.push({
        text: `öppna ${v.series}${v.number}`,
        titel: "Öppna verifikationen",
        onTryck: () => detalj.oppna({ typ: "ver", id: v.id }),
      });
    }
  }

  return (
    <Rad
      titel={fil.filename}
      meta={`${text} · ${fil.folder}/ · ${tidpunkt(fil.modified_at)}`}
      hoger={storlek(fil.size_bytes)}
      ton={ton}
      lankar={lankar}
    />
  );
}

function Rad({
  titel,
  meta,
  hoger,
  ton = "normal",
  lankar = [],
}: {
  titel: string;
  meta: string;
  hoger?: string;
  ton?: keyof typeof TON;
  lankar?: { text: string; titel: string; onTryck: () => void }[];
}) {
  return (
    <div className="-mx-2 flex items-baseline justify-between gap-[14px] rounded-md border-b border-bok-linje-svagast px-2 py-[9px]">
      <div className="flex min-w-0 flex-col gap-[2px]">
        <span className="truncate text-[14px] text-bok-text">{titel}</span>
        <span className="bok-mono text-[11px] [text-wrap:pretty]" style={{ color: TON[ton] }}>
          {meta}
          {lankar.map((l) => (
            <span key={l.text}>
              {" · "}
              <button
                type="button"
                title={l.titel}
                onClick={l.onTryck}
                className="text-bok-lank underline-offset-2 hover:text-bok-lank-hover hover:underline"
              >
                {l.text}
              </button>
            </span>
          ))}
        </span>
      </div>
      {hoger && <span className="bok-mono shrink-0 text-[13px] tabular-nums text-bok-text-2">{hoger}</span>}
    </div>
  );
}
