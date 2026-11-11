"use client";

import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useDropzoneOversikt } from "@/hooks/useDropzone";
import { VyBanner } from "@/components/skal/VyBanner";
import { VyHeaderStatus } from "@/components/skal/VyHeaderStatus";
import { VySektion } from "@/components/skal/VySektion";
import {
  DROPZONE_NYCKEL,
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
} from "@/lib/skal/dropzone";
import { lageFarg } from "@/lib/skal/lage";

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
            ? `bok-dold-skroll flex min-h-0 flex-1 flex-col overflow-auto pb-[18px] pt-1 ${pad}`
            : `flex flex-col pb-24 ${pad}`
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
  const vantetid = Math.max(data.quiet_seconds, 0) + data.scan_interval_seconds;

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
            <Mapp key={nod.namn} nod={nod} avstangd={avstangd} onSlapp={onSlapp} />
          ))}
        </ul>
      </VySektion>

      <VySektion titel="Skickat härifrån" antalRader={slappta.length} variant={variant}>
        {slappta.map((s) => (
          <Rad
            key={s.id}
            titel={s.namn}
            meta={slapptMeta(s, data, vantetid)}
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
        {data.pending.map((f) => (
          <Rad
            key={`${f.folder}/${f.filename}`}
            titel={f.filename}
            meta={`${f.folder}/ · ${tidpunkt(f.modified_at)}`}
            hoger={storlek(f.size_bytes)}
          />
        ))}
      </VySektion>

      <VySektion titel="_Problem" antalRader={data.problems.length} variant={variant}>
        {data.problems.map((f) => (
          <Rad
            key={`${f.folder}/${f.filename}`}
            titel={f.filename}
            meta={`${f.reason ?? "Avvisad, se .problem.txt bredvid filen."} · ${tidpunkt(f.modified_at)}`}
            ton="fel"
          />
        ))}
      </VySektion>

      <VySektion titel="Senast inlästa" antalRader={data.ingested.length} variant={variant}>
        {data.ingested.map((f) => (
          <Rad
            key={`${f.folder}/${f.filename}`}
            titel={f.filename}
            meta={`${f.folder}/ · ${tidpunkt(f.modified_at)}`}
            hoger={storlek(f.size_bytes)}
          />
        ))}
      </VySektion>

      <div className="pt-5 text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">
        En fil som läggs här hamnar i samma mapp som om den kopierats in via utdelningen. Skannern läser in
        den när den legat orörd i {data.quiet_seconds} s, flyttar den till _Inläst/ och agenten bokför den i
        Verifikationer. En fil som inte går att läsa hamnar i _Problem/ med en förklaring. Ett kontoutdrag
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
function slapptMeta(s: Slappt, data: DropzoneOversikt, vantetid: number): string {
  if (s.tillstand === "laddar") return `laddar upp till ${s.mapp}/`;
  if (s.tillstand === "fel") return s.text ?? "kunde inte läggas i mappen";
  const problem = data.problems.find((p) => p.filename === s.namn);
  if (problem) return `avvisad, ligger i _Problem/${problem.reason ? ` · ${problem.reason}` : ""}`;
  if (data.pending.some((p) => p.folder === s.mapp && p.filename === s.namn)) {
    return `lagd i ${s.mapp}/ · läses in inom ~${vantetid} s`;
  }
  if (data.ingested.some((p) => p.filename === s.namn)) return `inläst från ${s.mapp}/ · agenten bokför den`;
  return `lagd i ${s.mapp}/`;
}

/** En mapp på översta nivån, med sina undermappar indragna under sig. */
function Mapp({
  nod,
  avstangd,
  onSlapp,
}: {
  nod: Mappnod;
  avstangd: boolean;
  onSlapp: (mal: DropzoneMal, filer: File[]) => void;
}) {
  return (
    <li className="flex flex-col">
      {nod.mal ? (
        <MappRad mal={nod.mal} namn={`${nod.namn}/`} avstangd={avstangd} onSlapp={onSlapp} />
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
            </li>
          ))}
        </ul>
      )}
    </li>
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
  fel: "var(--bok-fel-meta)",
} as const;

function Rad({
  titel,
  meta,
  hoger,
  ton = "normal",
}: {
  titel: string;
  meta: string;
  hoger?: string;
  ton?: keyof typeof TON;
}) {
  return (
    <div className="-mx-2 flex items-baseline justify-between gap-[14px] rounded-md border-b border-bok-linje-svagast px-2 py-[9px]">
      <div className="flex min-w-0 flex-col gap-[2px]">
        <span className="truncate text-[14px] text-bok-text">{titel}</span>
        <span className="bok-mono text-[11px] [text-wrap:pretty]" style={{ color: TON[ton] }}>
          {meta}
        </span>
      </div>
      {hoger && <span className="bok-mono shrink-0 text-[13px] tabular-nums text-bok-text-2">{hoger}</span>}
    </div>
  );
}
