"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { LasKnapp } from "@/components/skal/LasKnapp";
import { VyBanner } from "@/components/skal/VyBanner";
import { VyHeaderStatus } from "@/components/skal/VyHeaderStatus";
import { VyRadSkelett } from "@/components/skal/VyRad";
import {
  type ArRad,
  type Bokslut,
  type Kontroll,
  type Nedladdning,
  type Par,
  type Uppgifter,
  attAtgarda,
  bokslutApi,
  bokslutNyckel,
  bokslutStatus,
  bokslutTitel,
  justeringsText,
  kronor,
} from "@/lib/skal/bokslut";
import type { LasData } from "@/lib/skal/las";
import { lageFarg } from "@/lib/skal/lage";
import { type BokslutDel, sidan } from "@/lib/skal/vyer";

/**
 * En del av ett räkenskapsårs bokslut, i läskolumnen: Översikt (kontrollerna
 * och filerna), INK2, Moms, Årsredovisning eller Uppgifter. Delarna är egna
 * vyer i navigeringen och gäller året i årsväljaren. Allt räknas på servern
 * (`services/bokslut.py`); här visas det och laddas ner. Uppgifterna är det
 * enda som skrivs, och de bokför ingenting.
 */

export function BokslutVy({
  del,
  titel,
  arId,
  las,
  onGaTill,
  variant,
}: {
  del: BokslutDel | "bokslut.rapporter";
  titel: string;
  /** Året i årsväljaren; `null` när det inte finns något räkenskapsår. */
  arId: string | null | undefined;
  /** Årets lås, på Översikten. */
  las?: LasData;
  onGaTill: (del: BokslutDel) => void;
  variant: "desktop" | "mobil";
}) {
  const { data, isError } = useQuery({
    queryKey: bokslutNyckel(arId ?? ""),
    queryFn: () => bokslutApi.getBokslut(arId ?? ""),
    enabled: !!arId,
    staleTime: 30 * 1000,
  });
  const pad = variant === "desktop" ? "px-6" : "px-[18px]";

  const status =
    arId === null
      ? { text: "inget räkenskapsår", lage: "tomt" as const }
      : data
        ? bokslutStatus(data)
        : isError
          ? { text: "kunde inte läsas", lage: "fel" as const }
          : { text: "hämtar", lage: "pagaende" as const };

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
            : // pb: plats under sista raden för chattbubblan (`ChattBubbla`).
              `flex flex-col pb-24 ${pad}`
        }
      >
        {arId === null ? (
          <div className="pt-5 text-[13px] text-bok-text-svag">
            Det finns inget räkenskapsår att göra bokslut för.
          </div>
        ) : isError ? (
          <div className="mt-[14px]">
            <VyBanner ton="fel" text="Bokslutet kunde inte räknas fram. Ladda om sidan." />
          </div>
        ) : !data ? (
          <div className="pt-5">
            <VyRadSkelett />
          </div>
        ) : (
          <>
            <div className="bok-mono flex items-center justify-between gap-3 pt-[14px] text-[12px] text-bok-meta">
              <span>
                {bokslutTitel(data)} · {data.fiscal_year.start} – {data.fiscal_year.end}
              </span>
              {del === "bokslut.rapporter" && las && <LasKnapp {...las} />}
            </div>
            {del !== "bokslut.rapporter" && <AttAtgardaHar b={data} del={del} />}
            {del === "bokslut.rapporter" && <Oversikt b={data} onGaTill={onGaTill} />}
            {del === "bokslut.ink2" && <Ink2Flik b={data} />}
            {del === "bokslut.moms" && <MomsFlik b={data} />}
            {del === "bokslut.arsredovisning" && <ArFlik b={data} />}
            {/* Nyckeln: ett annat år ger formuläret det årets startvärden. */}
            {del === "bokslut.uppgifter" && <UppgifterFlik key={data.fiscal_year.id} b={data} />}
          </>
        )}
      </div>
    </div>
  );
}

// ─── Byggstenar ───────────────────────────────────────────────────────────

function Rubrik({ children }: { children: React.ReactNode }) {
  return <div className="bok-etikett pb-[6px] pt-5 text-[10px] text-bok-meta">{children}</div>;
}

function Rad({
  titel,
  meta,
  hoger,
  summa,
  ton,
}: {
  titel: React.ReactNode;
  meta?: React.ReactNode;
  hoger?: React.ReactNode;
  summa?: boolean;
  ton?: "fel" | "vantar" | "klart";
}) {
  const metaFarg =
    ton === "fel" ? "text-bok-fel-meta" : ton === "vantar" ? "text-bok-vantar-meta" : ton === "klart" ? "text-bok-klart-meta" : "text-bok-meta";
  return (
    <div className="-mx-2 flex items-start justify-between gap-3 border-b border-bok-linje-svagast px-2 py-[8px]">
      <div className="min-w-0">
        <div className={`text-[14px] leading-[1.35] text-bok-text ${summa ? "font-medium" : ""}`}>{titel}</div>
        {meta && <div className={`bok-mono pt-[2px] text-[11px] leading-[1.45] ${metaFarg}`}>{meta}</div>}
      </div>
      {hoger !== undefined && (
        <div className={`bok-mono bok-tal shrink-0 text-right text-[14px] ${summa ? "font-medium" : ""}`}>{hoger}</div>
      )}
    </div>
  );
}

function ParKolumner({ par, summa }: { par: Par; summa?: boolean }) {
  return (
    <span className={`flex gap-4 ${summa ? "font-medium" : ""}`}>
      <span className="w-[86px] text-right">{kronor(par[0])}</span>
      <span className="w-[86px] text-right text-bok-meta">{kronor(par[1])}</span>
    </span>
  );
}

const NIVA_TON: Record<Kontroll["niva"], "fel" | "vantar" | "klart" | undefined> = {
  fel: "fel",
  varning: "vantar",
  info: undefined,
  ok: "klart",
};
const NIVA_TEXT: Record<Kontroll["niva"], string> = { fel: "fel", varning: "åtgärda", info: "info", ok: "ok" };

function Filer({ filer }: { filer: Nedladdning[] }) {
  const [hamtar, setHamtar] = useState<string | null>(null);
  const [fel, setFel] = useState<string | null>(null);
  const ladda = async (f: Nedladdning) => {
    setHamtar(f.id);
    setFel(null);
    try {
      const { blob, filnamn } = await bokslutApi.hamtaFil(f.url);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filnamn;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch {
      setFel(`${f.label} kunde inte hämtas.`);
    } finally {
      setHamtar(null);
    }
  };
  return (
    <>
      {fel && <VyBanner ton="fel" text={fel} />}
      {filer.map((f) => (
        <Rad
          key={f.id}
          titel={
            <button
              type="button"
              onClick={() => ladda(f)}
              disabled={hamtar !== null}
              className="text-left text-bok-lank underline-offset-2 hover:text-bok-lank-hover hover:underline disabled:opacity-60"
            >
              {f.label}
            </button>
          }
          meta={f.beskrivning}
          hoger={<span className="text-[12px] text-bok-meta">{hamtar === f.id ? "hämtar…" : "ladda ner"}</span>}
        />
      ))}
    </>
  );
}

/** Vytiteln för en bokslutsdel: "INK2", "Uppgifter". */
function delTitel(del: BokslutDel): string {
  return sidan("bokslut").vyer.find((v) => v.key === del)?.titel ?? del;
}

/** Kontrollerna som ska åtgärdas i just den här delen, överst i den. */
function AttAtgardaHar({ b, del }: { b: Bokslut; del: BokslutDel }) {
  const kvar = attAtgarda(b.kontroller).filter((k) => k.del === del);
  if (kvar.length === 0) return null;
  return (
    <>
      <Rubrik>Att åtgärda</Rubrik>
      {kvar.map((k, i) => (
        <Rad
          key={`${k.id}-${i}`}
          titel={k.titel}
          meta={k.text}
          hoger={<span className="text-[12px]">{NIVA_TEXT[k.niva]}</span>}
          ton={NIVA_TON[k.niva]}
        />
      ))}
    </>
  );
}

// ─── Översikt ─────────────────────────────────────────────────────────────

function Oversikt({ b, onGaTill }: { b: Bokslut; onGaTill: (del: BokslutDel) => void }) {
  const kvar = attAtgarda(b.kontroller);
  const ovriga = b.kontroller.filter((k) => !kvar.includes(k));
  const ar = b.arsredovisning;
  const grupper = Array.from(new Set(b.nedladdningar.map((n) => n.grupp)));
  return (
    <>
      <div className="bok-mono pt-[2px] text-[12px] text-bok-meta">
        {b.company.name} · {b.company.org_number}
      </div>

      <Rubrik>Nyckeltal</Rubrik>
      <Rad titel="Nettoomsättning" hoger={kronor(ar.forvaltningsberattelse.flerarsoversikt[0]?.nettoomsattning)} />
      <Rad titel="Årets resultat" hoger={kronor(ar.resultatrakning.arets_resultat[0])} />
      <Rad
        titel="Överskott av näringsverksamhet"
        meta="INK2 1.1 · INK2S 4.15"
        hoger={kronor(b.skatt.overskott - b.skatt.underskott)}
      />
      <Rad
        titel="Bolagsskatt"
        meta={`beräknad ${kronor(b.skatt.beraknad_skatt)} · bokförd ${kronor(b.skatt.bokford_skatt)}`}
        hoger={kronor(b.skatt.beraknad_skatt)}
      />
      <Rad
        titel={b.moms.summary.net_vat_sek >= 0 ? "Moms att betala" : "Moms att få tillbaka"}
        meta={`ruta 49 · period ${b.moms.period}`}
        hoger={kronor(Math.abs(b.moms.summary.net_vat_sek))}
      />

      {kvar.length > 0 && (
        <>
          <Rubrik>Att åtgärda</Rubrik>
          {kvar.map((k, i) => {
            const dit = k.del && k.del !== "bokslut.rapporter" ? k.del : null;
            return (
              <Rad
                key={`${k.id}-${i}`}
                titel={k.titel}
                meta={k.text}
                hoger={
                  dit ? (
                    <button
                      type="button"
                      onClick={() => onGaTill(dit)}
                      className="text-[12px] text-bok-lank underline-offset-2 hover:underline"
                    >
                      {delTitel(dit)} →
                    </button>
                  ) : (
                    <span className="text-[12px]">{NIVA_TEXT[k.niva]}</span>
                  )
                }
                ton={NIVA_TON[k.niva]}
              />
            );
          })}
        </>
      )}

      {grupper.map((g) => (
        <div key={g}>
          <Rubrik>Filer till {g}</Rubrik>
          <Filer filer={b.nedladdningar.filter((n) => n.grupp === g)} />
        </div>
      ))}

      <Rubrik>Kontroller</Rubrik>
      {ovriga.map((k, i) => (
        <Rad key={`${k.id}-${i}`} titel={k.titel} meta={k.text || undefined} ton={NIVA_TON[k.niva]} hoger={<span className="text-[12px]">{NIVA_TEXT[k.niva]}</span>} />
      ))}

      <div className="pt-5 text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">
        SRU-filerna laddas upp i Skatteverkets filöverföring för Inkomstdeklaration 2, eSKD-filen i
        filöverföringen för moms. Årsredovisningen skrivs ut, undertecknas och skickas till Bolagsverket
        tillsammans med fastställelseintyget.
      </div>
    </>
  );
}

// ─── INK2 ─────────────────────────────────────────────────────────────────

function Ink2Flik({ b }: { b: Bokslut }) {
  const [blankett, setBlankett] = useState<"ink2" | "ink2r" | "ink2s">("ink2s");
  const s = b.skatt;
  return (
    <>
      <Rubrik>Skatteberäkning</Rubrik>
      {s.justeringar.map((j) => (
        <Rad
          key={j.code}
          titel={`${j.row} ${j.label}`}
          meta={justeringsText(j)}
          hoger={kronor(j.value)}
          ton={j.override !== null && j.override !== j.calculated ? "vantar" : undefined}
        />
      ))}
      <Rad titel="Överskott (4.15)" hoger={kronor(s.overskott)} summa />
      {s.underskott > 0 && <Rad titel="Underskott (4.16)" hoger={kronor(s.underskott)} summa />}
      <Rad
        titel="Skatt 20,6 %"
        meta={`på ${kronor(s.underlag)} (avrundat nedåt till hundratal)`}
        hoger={kronor(s.beraknad_skatt)}
      />

      {s.periodiseringsfonder.length > 0 && (
        <>
          <Rubrik>Periodiseringsfonder</Rubrik>
          {s.periodiseringsfonder.map((f) => (
            <Rad
              key={f.account}
              titel={`${f.account} ${f.name}`}
              meta={`IB ${kronor(f.opening)}${f.reversed ? ` · återförd ${kronor(f.reversed)}` : ""}${f.allocated ? ` · avsatt ${kronor(f.allocated)}` : ""}`}
              hoger={kronor(f.closing)}
            />
          ))}
          <Rad
            titel="Möjlig avsättning i år"
            meta="25 % av överskottet före avsättning"
            hoger={kronor(s.max_avsattning_periodiseringsfond)}
          />
        </>
      )}

      <div className="flex gap-1 pt-5">
        {b.ink2.tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setBlankett(t.id as typeof blankett)}
            className={`rounded-md px-[10px] py-[4px] text-[12px] ${
              blankett === t.id ? "bg-bok-yta-svag font-medium text-bok-text" : "text-bok-text-2 hover:bg-bok-yta-svag"
            }`}
            title={t.description}
          >
            {t.label}
          </button>
        ))}
      </div>
      {(b.ink2.sections[blankett] ?? []).map((sek) => {
        const rader = sek.rows.filter((r) => r.value !== null && r.value !== 0);
        if (rader.length === 0) return null;
        return (
          <div key={sek.title}>
            <Rubrik>{sek.title}</Rubrik>
            {rader.map((r, i) => (
              <Rad
                key={`${r.code}-${i}`}
                titel={`${r.code} ${r.label}`}
                meta={
                  r.source_accounts.length
                    ? r.source_accounts.map((a) => `${a.account} ${kronor(a.value)}`).join(" · ")
                    : r.sru_fields.length
                      ? `fält ${r.sru_fields.join(", ")}`
                      : undefined
                }
                hoger={kronor(r.value)}
              />
            ))}
          </div>
        );
      })}
      <Rubrik>Filer</Rubrik>
      <Filer filer={b.nedladdningar.filter((n) => n.id.includes("sru"))} />
    </>
  );
}

// ─── Moms ─────────────────────────────────────────────────────────────────

function MomsFlik({ b }: { b: Bokslut }) {
  const m = b.moms;
  return (
    <>
      <div className="bok-mono pt-[14px] text-[12px] text-bok-meta">Period {m.period}</div>
      {(m.warnings ?? []).map((w) => (
        <div key={w} className="mt-[14px]">
          <VyBanner ton="varning" text={w} />
        </div>
      ))}
      <Rubrik>Rutor</Rubrik>
      {m.boxes
        .filter((r) => r.amount_sek !== 0 || r.box === "49")
        .map((r) => (
          <Rad
            key={r.box}
            titel={`${r.box} ${r.label}`}
            meta={
              r.sources.length && r.box !== "49"
                ? r.sources.map((s) => `${s.account_code} ${kronor(s.amount_sek)}`).join(" · ")
                : undefined
            }
            hoger={kronor(r.amount_sek)}
            summa={r.box === "49"}
          />
        ))}
      <Rubrik>Filer</Rubrik>
      <Filer filer={b.nedladdningar.filter((n) => n.id === "eskd" || n.id === "moms_pdf")} />
    </>
  );
}

// ─── Årsredovisning ───────────────────────────────────────────────────────

function ArRader({ rader }: { rader: ArRad[] }) {
  return (
    <>
      {rader.map((r) => (
        <Rad key={r.key} titel={r.label} hoger={<ParKolumner par={r.belopp} />} />
      ))}
    </>
  );
}

function ArFlik({ b }: { b: Bokslut }) {
  const ar = b.arsredovisning;
  const rr = ar.resultatrakning;
  const br = ar.balansrakning;
  const vd = ar.forvaltningsberattelse.vinstdisposition;
  return (
    <>
      {ar.missing.length > 0 && (
        <div className="mt-[14px]">
          <VyBanner
            ton="varning"
            text={`Uppgifter saknas: ${ar.missing.map((m) => m.label.toLowerCase()).join(", ")}. De står markerade i PDF:en tills de fylls i under Uppgifter.`}
          />
        </div>
      )}
      <Rubrik>Filer</Rubrik>
      <Filer filer={b.nedladdningar.filter((n) => n.grupp === "Bolagsverket")} />

      <div className="bok-mono flex justify-end gap-4 pt-5 text-[11px] text-bok-meta">
        <span className="w-[86px] text-right">{ar.period.end.slice(0, 4)}</span>
        <span className="w-[86px] text-right">{ar.prior_period.end.slice(0, 4)}</span>
      </div>
      <Rubrik>Resultaträkning</Rubrik>
      {rr.sektioner.map((s) =>
        s.rader.length ? (
          <ArRader key={s.titel} rader={s.rader} />
        ) : s.summa ? (
          <Rad key={s.titel} titel={s.titel} hoger={<ParKolumner par={s.summa} summa />} summa />
        ) : null
      )}
      <Rad titel="Årets resultat" hoger={<ParKolumner par={rr.arets_resultat} summa />} summa />

      <Rubrik>Balansräkning · tillgångar</Rubrik>
      {br.tillgangar.flatMap((d) => d.grupper.flatMap((g) => g.rader)).map((r) => (
        <Rad key={r.key} titel={r.label} hoger={<ParKolumner par={r.belopp} />} />
      ))}
      <Rad titel="Summa tillgångar" hoger={<ParKolumner par={br.summa_tillgangar} summa />} summa />

      <Rubrik>Balansräkning · eget kapital och skulder</Rubrik>
      <ArRader rader={[...br.eget_kapital.bundet.rader, ...br.eget_kapital.fritt.rader]} />
      <Rad titel="Summa eget kapital" hoger={<ParKolumner par={br.eget_kapital.summa} summa />} summa />
      {br.skulder.map((s) => (
        <div key={s.titel}>
          <ArRader rader={s.rader} />
        </div>
      ))}
      <Rad titel="Summa eget kapital och skulder" hoger={<ParKolumner par={br.summa_ek_skulder} summa />} summa />

      <Rubrik>Förslag till vinstdisposition</Rubrik>
      <Rad titel="Till förfogande" hoger={kronor(vd.summa)} />
      <Rad titel="Utdelas till aktieägarna" hoger={kronor(vd.utdelning)} />
      <Rad titel="Balanseras i ny räkning" hoger={kronor(vd.i_ny_rakning)} />

      {ar.warnings.map((w) => (
        <div key={w} className="mt-[10px]">
          <VyBanner ton="neutral" text={w} />
        </div>
      ))}
    </>
  );
}

// ─── Uppgifter ────────────────────────────────────────────────────────────

type Falt = {
  key: string;
  label: string;
  typ: "text" | "textarea" | "tal" | "datum" | "konton" | "procent";
  hjalp?: string;
};

const AR_FALT: Falt[] = [
  { key: "ar.verksamhet", label: "Verksamhetens art och inriktning", typ: "textarea", hjalp: "Förvaltningsberättelsen, t.ex. vad bolaget gör och vilket verksamhetsår det är." },
  { key: "ar.vasentliga_handelser", label: "Väsentliga händelser under året", typ: "textarea" },
  { key: "ar.medeltal_anstallda", label: "Medelantal anställda", typ: "tal" },
  { key: "ar.medeltal_anstallda_fg", label: "Medelantal anställda föregående år", typ: "tal" },
  { key: "ar.utdelning", label: "Föreslagen utdelning (kr)", typ: "tal" },
  { key: "ar.ort", label: "Ort", typ: "text" },
  { key: "ar.datum", label: "Datum för underskrift", typ: "datum" },
  { key: "ar.stamma_datum", label: "Datum för årsstämman", typ: "datum" },
  { key: "ar.intygare", label: "Undertecknar fastställelseintyget", typ: "text" },
];

const INK2S_FALT: Falt[] = [
  { key: "ink2s.ej_avdragsgilla_konton", label: "Ej avdragsgilla konton (4.3c)", typ: "konton" },
  { key: "ink2s.skattefria_konton", label: "Skattefria konton (4.5c)", typ: "konton" },
  { key: "ink2s.slr", label: "Statslåneräntan november året innan (%)", typ: "procent", hjalp: "Behövs bara om Bok inte känner räntan för året." },
  { key: "ink2s.belopp.7653", label: "4.3c angivet belopp", typ: "tal" },
  { key: "ink2s.belopp.7754", label: "4.5c angivet belopp", typ: "tal" },
  { key: "ink2s.belopp.7654", label: "4.6a angivet belopp", typ: "tal" },
  { key: "ink2s.belopp.7667", label: "4.6d angivet belopp", typ: "tal" },
];

type Underskrift = { namn: string; roll: string };

function tillText(v: unknown, typ: Falt["typ"]): string {
  if (v === undefined || v === null) return "";
  if (typ === "konton" && Array.isArray(v)) return v.join(", ");
  return String(v);
}

function franText(s: string, typ: Falt["typ"]): unknown {
  const t = s.trim();
  if (t === "") return null;
  if (typ === "tal") return Number(t.replace(/\s/g, "").replace(",", "."));
  if (typ === "procent") return Number(t.replace(",", "."));
  if (typ === "konton") return t.split(/[\s,;]+/).filter(Boolean);
  return t;
}

function UppgifterFlik({ b }: { b: Bokslut }) {
  const queryClient = useQueryClient();
  const arId = b.fiscal_year.id;
  const alla = [...AR_FALT, ...INK2S_FALT];
  const start = () =>
    Object.fromEntries(alla.map((f) => [f.key, tillText(b.uppgifter[f.key], f.typ)])) as Record<string, string>;
  const [varden, setVarden] = useState<Record<string, string>>(start);
  const [underskrifter, setUnderskrifter] = useState<Underskrift[]>(
    ((b.uppgifter["ar.underskrifter"] as Underskrift[] | undefined) ?? b.arsredovisning.underskrifter.personer) || []
  );
  const [upplysningar, setUpplysningar] = useState<{ uppdragstagare: boolean; revision: boolean }>(
    (b.uppgifter["ink2s.upplysningar"] as { uppdragstagare: boolean; revision: boolean } | undefined) ?? {
      uppdragstagare: false,
      revision: false,
    }
  );
  const [sparat, setSparat] = useState(false);
  useEffect(() => setSparat(false), [varden, underskrifter, upplysningar]);

  const spara = useMutation({
    mutationFn: () => {
      const values: Uppgifter = {};
      for (const f of alla) {
        const ny = franText(varden[f.key] ?? "", f.typ);
        const gammal = b.uppgifter[f.key] ?? null;
        if (JSON.stringify(ny) !== JSON.stringify(gammal)) values[f.key] = ny;
      }
      const personer = underskrifter.filter((u) => u.namn.trim() && u.roll.trim());
      if (JSON.stringify(personer) !== JSON.stringify(b.uppgifter["ar.underskrifter"] ?? null)) {
        values["ar.underskrifter"] = personer.length ? personer : null;
      }
      if (JSON.stringify(upplysningar) !== JSON.stringify(b.uppgifter["ink2s.upplysningar"] ?? { uppdragstagare: false, revision: false })) {
        values["ink2s.upplysningar"] = upplysningar;
      }
      if (Object.keys(values).length === 0) return Promise.resolve(b.uppgifter);
      return bokslutApi.sparaUppgifter(arId, values);
    },
    onSuccess: () => {
      setSparat(true);
      queryClient.invalidateQueries({ queryKey: bokslutNyckel(arId) });
    },
  });

  const felText = (() => {
    const e = spara.error as { response?: { data?: { detail?: { details?: string } } } } | null;
    return e ? e.response?.data?.detail?.details ?? "Uppgifterna kunde inte sparas." : null;
  })();

  const ursprung = start();
  /** "Från 2025" under ett fält vars värde ärvs och inte ändrats här. */
  const arvd = (key: string, oforandrat: boolean) => {
    const fran = b.uppgifter_arvda?.[key];
    if (!fran || !oforandrat) return null;
    return <span className="bok-mono text-[12px] text-bok-meta">från {fran.label}</span>;
  };

  const falt = (f: Falt) => (
    <label key={f.key} className="flex flex-col gap-1 pt-3">
      <span className="text-[13px] text-bok-text-2">{f.label}</span>
      {f.typ === "textarea" ? (
        <textarea
          value={varden[f.key]}
          onChange={(e) => setVarden({ ...varden, [f.key]: e.target.value })}
          rows={3}
          className="rounded-md border border-bok-linje bg-bok-yta px-3 py-[7px] text-[14px] text-bok-text focus:border-bok-lank focus:outline-none"
        />
      ) : (
        <input
          type={f.typ === "datum" ? "date" : "text"}
          inputMode={f.typ === "tal" || f.typ === "procent" ? "decimal" : undefined}
          value={varden[f.key]}
          placeholder={
            f.key === "ink2s.ej_avdragsgilla_konton"
              ? b.skatt.ej_avdragsgilla_konton.join(", ")
              : f.key === "ink2s.skattefria_konton"
                ? b.skatt.skattefria_konton.join(", ")
                : f.key.startsWith("ink2s.belopp.")
                  ? `beräknat ${kronor(b.skatt.justeringar.find((j) => `ink2s.belopp.${j.code}` === f.key)?.calculated)}`
                  : undefined
          }
          onChange={(e) => setVarden({ ...varden, [f.key]: e.target.value })}
          className="bok-mono rounded-md border border-bok-linje bg-bok-yta px-3 py-[7px] text-[13px] text-bok-text placeholder:text-bok-meta focus:border-bok-lank focus:outline-none"
        />
      )}
      {f.hjalp && <span className="text-[12px] text-bok-meta">{f.hjalp}</span>}
      {arvd(f.key, varden[f.key] === ursprung[f.key])}
    </label>
  );

  const fritt = b.arsredovisning.balansrakning.fritt_eget_kapital[0] ?? 0;

  return (
    <form
      className="flex flex-col"
      onSubmit={(e) => {
        e.preventDefault();
        spara.mutate();
      }}
    >
      <Rubrik>Årsredovisningen</Rubrik>
      {AR_FALT.map(falt)}
      <button
        type="button"
        onClick={() => setVarden({ ...varden, "ar.utdelning": String(fritt) })}
        className="bok-mono self-start pt-1 text-[12px] text-bok-lank underline-offset-2 hover:underline"
      >
        Föreslå hela fria egna kapitalet ({kronor(fritt)})
      </button>

      <Rubrik>Underskrifter</Rubrik>
      {underskrifter.map((u, i) => (
        <div key={i} className="flex gap-2 pt-2">
          <input
            aria-label="Namn"
            placeholder="Namn"
            value={u.namn}
            onChange={(e) => setUnderskrifter(underskrifter.map((x, j) => (j === i ? { ...x, namn: e.target.value } : x)))}
            className="min-w-0 flex-1 rounded-md border border-bok-linje bg-bok-yta px-3 py-[7px] text-[14px] text-bok-text placeholder:text-bok-meta focus:border-bok-lank focus:outline-none"
          />
          <input
            aria-label="Roll"
            placeholder="Roll"
            value={u.roll}
            onChange={(e) => setUnderskrifter(underskrifter.map((x, j) => (j === i ? { ...x, roll: e.target.value } : x)))}
            className="min-w-0 flex-1 rounded-md border border-bok-linje bg-bok-yta px-3 py-[7px] text-[14px] text-bok-text placeholder:text-bok-meta focus:border-bok-lank focus:outline-none"
          />
          <button
            type="button"
            aria-label="Ta bort"
            onClick={() => setUnderskrifter(underskrifter.filter((_, j) => j !== i))}
            className="px-2 text-bok-meta hover:text-bok-text"
          >
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => setUnderskrifter([...underskrifter, { namn: "", roll: "Styrelseledamot" }])}
        className="bok-mono self-start pt-2 text-[12px] text-bok-lank underline-offset-2 hover:underline"
      >
        + Lägg till underskrift
      </button>
      {arvd("ar.underskrifter", JSON.stringify(underskrifter) === JSON.stringify(b.uppgifter["ar.underskrifter"] ?? null))}

      <Rubrik>Inkomstdeklarationen</Rubrik>
      {INK2S_FALT.map(falt)}
      <label className="flex items-center gap-2 pt-3 text-[13px] text-bok-text-2">
        <input
          type="checkbox"
          checked={upplysningar.uppdragstagare}
          onChange={(e) => setUpplysningar({ ...upplysningar, uppdragstagare: e.target.checked })}
        />
        Uppdragstagare (t.ex. redovisningskonsult) har biträtt vid årsredovisningen
      </label>
      <label className="flex items-center gap-2 pt-2 text-[13px] text-bok-text-2">
        <input
          type="checkbox"
          checked={upplysningar.revision}
          onChange={(e) => setUpplysningar({ ...upplysningar, revision: e.target.checked })}
        />
        Årsredovisningen har varit föremål för revision
      </label>
      {arvd("ink2s.upplysningar", JSON.stringify(upplysningar) === JSON.stringify(b.uppgifter["ink2s.upplysningar"] ?? null))}

      {felText && (
        <div className="mt-[14px]">
          <VyBanner ton="fel" text={felText} />
        </div>
      )}
      <div className="flex items-center gap-3 pt-5">
        <button
          type="submit"
          disabled={spara.isPending}
          className="rounded-md bg-bok-black px-4 py-[8px] text-[14px] text-bok-yta hover:bg-bok-black-hover disabled:opacity-60"
        >
          {spara.isPending ? "Sparar…" : "Spara uppgifterna"}
        </button>
        {sparat && <span className="bok-mono text-[12px] text-bok-klart-meta">sparat</span>}
      </div>
      <div className="pt-4 text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">
        Uppgifterna bokför ingenting. Varje ändring sparas som en ny rad med vem som gjorde den. Ett värde märkt
        &quot;från&quot; ett tidigare år följer med det året tills du ändrar det här. Ett tomt fält tar bort
        uppgiften, och ett tomt beloppsfält i inkomstdeklarationen betyder att det beräknade beloppet gäller.
      </div>
    </form>
  );
}
