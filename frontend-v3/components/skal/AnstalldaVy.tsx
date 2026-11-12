"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { VyBanner } from "@/components/skal/VyBanner";
import { VyHeaderStatus } from "@/components/skal/VyHeaderStatus";
import { VyRadSkelett } from "@/components/skal/VyRad";
import type { PayrollEmployee } from "@/lib/api";
import { LONER_NYCKEL } from "@/lib/chattyta/api";
import {
  ANSTALLDA_NYCKEL,
  STANDARD_AVGIFT_PROCENT,
  STANDARD_UTBETALNINGSDAG,
  anstalldaApi,
  anstalldaStatus,
  bpTillProcent,
  felText,
  kronorTillOre,
  maskeraPersonnummer,
  oreTillKronor,
  procentTillBp,
  utbetalningsdatum,
  vanligasteUtbetalningsdag,
} from "@/lib/skal/anstallda";
import { formatBeloppHela } from "@/lib/skal/format";
import { lageFarg } from "@/lib/skal/lage";
import type { Vynyckel } from "@/lib/skal/vyer";

/**
 * Anställda (`betala.anstallda`): där lönerna ställs in.
 *
 * De anställda med sin månadslön, skatt och arbetsgivaravgift, ett formulär
 * för en ny anställd och knappen som skapar månadens lönebesked. Ingenting
 * här bokför: lönebeskeden bokförs i Löner, med ett tryck i kortet agenten
 * lägger fram. Vyn chattar i Löners tråd, som dropzonen i Verifikationers.
 */
export function AnstalldaVy({
  titel,
  variant,
  onGaTill,
}: {
  titel: string;
  variant: "desktop" | "mobil";
  onGaTill: (key: Vynyckel) => void;
}) {
  const { data, isError } = useQuery({
    queryKey: ANSTALLDA_NYCKEL,
    queryFn: anstalldaApi.lista,
    staleTime: 30 * 1000,
  });
  const status = anstalldaStatus(data, isError);
  const pad = variant === "desktop" ? "px-6" : "px-[18px]";
  const [oppen, setOppen] = useState<string | null>(null);

  const aktiva = (data ?? []).filter((a) => a.active);
  const slutat = (data ?? []).filter((a) => !a.active);

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
          Månadslön, skatt och arbetsgivaravgift per anställd · bokförs i Löner
        </div>

        {isError ? (
          <div className="mt-[14px]">
            <VyBanner ton="fel" text="De anställda kunde inte läsas. Ladda om sidan." />
          </div>
        ) : !data ? (
          <div className="pt-5">
            <VyRadSkelett />
          </div>
        ) : (
          <>
            {aktiva.length > 0 && (
              <>
                <Rubrik>Anställda</Rubrik>
                {aktiva.map((a) => (
                  <AnstalldRad
                    key={a.id}
                    a={a}
                    oppen={oppen === a.id}
                    onOppna={() => setOppen(oppen === a.id ? null : a.id)}
                  />
                ))}
              </>
            )}

            {aktiva.length > 0 && <Lonekorning anstallda={data} onGaTill={onGaTill} />}

            <NyAnstalld forsta={aktiva.length === 0} onSkapad={(id) => setOppen(id)} />

            {slutat.length > 0 && (
              <>
                <Rubrik>Slutat</Rubrik>
                {slutat.map((a) => (
                  <AnstalldRad
                    key={a.id}
                    a={a}
                    oppen={oppen === a.id}
                    onOppna={() => setOppen(oppen === a.id ? null : a.id)}
                  />
                ))}
              </>
            )}
          </>
        )}

        <div className="pt-5 text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">
          En ändrad lön gäller lönebesked som skapas efter ändringen; ett lönebesked som redan finns ändras inte.
          Lönebeskeden bokförs i Löner. Du kan också be agenten registrera en anställd eller ändra en lön.
        </div>
      </div>
    </div>
  );
}

// ─── Byggstenar ───────────────────────────────────────────────────────────

const FALT =
  "bok-mono w-full rounded-md border border-bok-linje bg-bok-yta px-3 py-[7px] text-[13px] text-bok-text placeholder:text-bok-meta focus:border-bok-lank focus:outline-none";

function Rubrik({ children }: { children: React.ReactNode }) {
  return <div className="bok-etikett pb-[6px] pt-5 text-[10px] text-bok-meta">{children}</div>;
}

function Falt({
  etikett,
  hjalp,
  children,
}: {
  etikett: string;
  hjalp?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="text-[13px] text-bok-text-2">{etikett}</span>
      {children}
      {hjalp && <span className="text-[12px] text-bok-meta">{hjalp}</span>}
    </label>
  );
}

function Knapp({
  children,
  disabled,
  type = "submit",
  onClick,
  sekundar,
}: {
  children: React.ReactNode;
  disabled?: boolean;
  type?: "submit" | "button";
  onClick?: () => void;
  sekundar?: boolean;
}) {
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={
        sekundar
          ? "rounded-md border border-bok-linje px-4 py-[8px] text-[14px] text-bok-text hover:bg-bok-yta-svag disabled:opacity-60"
          : "rounded-md bg-bok-black px-4 py-[8px] text-[14px] text-bok-yta hover:bg-bok-black-hover disabled:opacity-60"
      }
    >
      {children}
    </button>
  );
}

function lonMeta(a: PayrollEmployee): string {
  const s = a.salary_setting;
  if (!s?.active) return "ingen lön inställd";
  return [
    `skatt ${formatBeloppHela(s.preliminary_tax)}`,
    `avgift ${formatBeloppHela(s.calculated_employer_fee)}`,
    `utbetalning den ${s.payment_day}:e`,
  ].join(" · ");
}

function AnstalldRad({ a, oppen, onOppna }: { a: PayrollEmployee; oppen: boolean; onOppna: () => void }) {
  const s = a.salary_setting?.active ? a.salary_setting : null;
  const saknar = a.active && !s;
  return (
    <div className="border-b border-bok-linje-svagast">
      <button
        type="button"
        onClick={onOppna}
        aria-expanded={oppen}
        className="-mx-2 flex w-[calc(100%+16px)] items-start justify-between gap-3 px-2 py-[8px] text-left hover:bg-bok-yta-svag"
      >
        <div className="min-w-0">
          <div className="text-[14px] leading-[1.35] text-bok-text">{a.name}</div>
          <div className={`bok-mono pt-[2px] text-[11px] leading-[1.45] ${saknar ? "text-bok-vantar-meta" : "text-bok-meta"}`}>
            {lonMeta(a)}
          </div>
        </div>
        <div className="bok-mono bok-tal shrink-0 text-right text-[14px]">
          {s ? formatBeloppHela(s.gross_monthly_salary) : ""}
        </div>
      </button>
      {oppen && <AndraAnstalld a={a} />}
    </div>
  );
}

/** Lönefälten, som text medan de skrivs. */
interface LoneFalt {
  brutto: string;
  skatt: string;
  avgift: string;
  dag: string;
}

function loneFaltFran(a: PayrollEmployee | null): LoneFalt {
  const s = a?.salary_setting?.active ? a.salary_setting : null;
  return {
    brutto: s ? oreTillKronor(s.gross_monthly_salary) : "",
    skatt: s ? oreTillKronor(s.preliminary_tax) : "",
    avgift: s?.employer_fee_rate_bp != null ? bpTillProcent(s.employer_fee_rate_bp) : STANDARD_AVGIFT_PROCENT,
    dag: String(s?.payment_day ?? STANDARD_UTBETALNINGSDAG),
  };
}

/** Lönefälten som server-värden, eller ett fel att visa. */
function tolkaLon(f: LoneFalt) {
  const brutto = kronorTillOre(f.brutto);
  const skatt = kronorTillOre(f.skatt);
  const bp = procentTillBp(f.avgift);
  const dag = Number(f.dag);
  if (brutto === null) return { fel: "Ange bruttolönen i kronor." } as const;
  if (skatt === null) return { fel: "Ange skatten i kronor (0 om ingen skatt dras)." } as const;
  if (skatt > brutto) return { fel: "Skatten kan inte vara större än bruttolönen." } as const;
  if (bp === null) return { fel: "Ange arbetsgivaravgiften i procent, t.ex. 31,42." } as const;
  if (!Number.isInteger(dag) || dag < 1 || dag > 31) return { fel: "Utbetalningsdagen är en dag 1–31." } as const;
  return {
    lon: { gross_monthly_salary: brutto, preliminary_tax: skatt, employer_fee_rate_bp: bp, payment_day: dag },
  } as const;
}

function LoneFaltVy({ f, setF }: { f: LoneFalt; setF: (f: LoneFalt) => void }) {
  const brutto = kronorTillOre(f.brutto);
  const skatt = kronorTillOre(f.skatt);
  const bp = procentTillBp(f.avgift);
  const netto = brutto !== null && skatt !== null && skatt <= brutto ? brutto - skatt : null;
  const avgift = brutto !== null && bp !== null ? Math.round((brutto * bp) / 10000) : null;
  return (
    <>
      <div className="grid grid-cols-1 gap-3 pt-3 sm:grid-cols-2">
        <Falt etikett="Bruttolön per månad, kr">
          <input
            inputMode="decimal"
            value={f.brutto}
            onChange={(e) => setF({ ...f, brutto: e.target.value })}
            placeholder="32 500"
            className={FALT}
          />
        </Falt>
        <Falt etikett="Skatt att dra, kr" hjalp="Ur skattetabellen eller skattebeslutet.">
          <input
            inputMode="decimal"
            value={f.skatt}
            onChange={(e) => setF({ ...f, skatt: e.target.value })}
            placeholder="7 800"
            className={FALT}
          />
        </Falt>
        <Falt etikett="Arbetsgivaravgift, %" hjalp="31,42 för de flesta; lägre för unga och äldre.">
          <input
            inputMode="decimal"
            value={f.avgift}
            onChange={(e) => setF({ ...f, avgift: e.target.value })}
            className={FALT}
          />
        </Falt>
        <Falt etikett="Utbetalningsdag">
          <input
            inputMode="numeric"
            value={f.dag}
            onChange={(e) => setF({ ...f, dag: e.target.value })}
            className={FALT}
          />
        </Falt>
      </div>
      {(netto !== null || avgift !== null) && (
        <div className="bok-mono pt-2 text-[12px] text-bok-meta">
          {[
            netto !== null ? `netto ${formatBeloppHela(netto)}` : null,
            avgift !== null ? `avgift ${formatBeloppHela(avgift)}` : null,
            brutto !== null && avgift !== null ? `kostnad ${formatBeloppHela(brutto + avgift)}` : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </div>
      )}
    </>
  );
}

function useUppdatera() {
  const queryClient = useQueryClient();
  // Löner och Anställda delar nyckel; en ny körning syns i Löner direkt.
  return () => queryClient.invalidateQueries({ queryKey: LONER_NYCKEL });
}

function NyAnstalld({ forsta, onSkapad }: { forsta: boolean; onSkapad: (id: string) => void }) {
  const uppdatera = useUppdatera();
  const [oppen, setOppen] = useState(forsta);
  const [namn, setNamn] = useState("");
  const [pnr, setPnr] = useState("");
  const [epost, setEpost] = useState("");
  const [bank, setBank] = useState("");
  const [lon, setLon] = useState<LoneFalt>(() => loneFaltFran(null));
  const [fel, setFel] = useState<string | null>(null);

  const skapa = useMutation({
    mutationFn: async () => {
      const tolkad = tolkaLon(lon);
      if ("fel" in tolkad) throw new Error(tolkad.fel);
      const a = await anstalldaApi.skapa({
        name: namn.trim(),
        personal_number: pnr.trim() || null,
        email: epost.trim() || null,
        bank_account: bank.trim() || null,
        active: true,
      });
      try {
        return await anstalldaApi.sattLon(a.id, tolkad.lon);
      } catch (e) {
        // Den anställda finns; lönen får sättas om på raden.
        onSkapad(a.id);
        throw e;
      }
    },
    onMutate: () => setFel(null),
    onSuccess: (a) => {
      setNamn("");
      setPnr("");
      setEpost("");
      setBank("");
      setLon(loneFaltFran(null));
      setOppen(false);
      onSkapad(a.id);
    },
    onError: (e) => setFel(e instanceof Error && !("response" in e) ? e.message : felText(e, "Kunde inte spara den anställda.")),
    onSettled: () => void uppdatera(),
  });

  if (!oppen) {
    return (
      <button
        type="button"
        onClick={() => setOppen(true)}
        className="bok-mono self-start pt-4 text-[12px] text-bok-lank underline-offset-2 hover:underline"
      >
        + Ny anställd
      </button>
    );
  }

  return (
    <form
      className="flex flex-col"
      onSubmit={(e) => {
        e.preventDefault();
        if (!namn.trim()) {
          setFel("Ange den anställdas namn.");
          return;
        }
        skapa.mutate();
      }}
    >
      <Rubrik>Ny anställd</Rubrik>
      {forsta && (
        <div className="pb-1 text-[13px] leading-[1.55] text-bok-text-2 [text-wrap:pretty]">
          Inga anställda än. Lägg in den första med sin månadslön, så kan månadens lönebesked skapas.
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 pt-2 sm:grid-cols-2">
        <Falt etikett="Namn">
          <input value={namn} onChange={(e) => setNamn(e.target.value)} className={FALT} autoComplete="off" />
        </Falt>
        <Falt etikett="Personnummer" hjalp="Krävs för arbetsgivardeklarationen.">
          <input
            value={pnr}
            onChange={(e) => setPnr(e.target.value)}
            placeholder="ÅÅÅÅMMDD-XXXX"
            className={FALT}
            autoComplete="off"
          />
        </Falt>
        <Falt etikett="E-post">
          <input type="email" value={epost} onChange={(e) => setEpost(e.target.value)} className={FALT} />
        </Falt>
        <Falt etikett="Bankkonto">
          <input value={bank} onChange={(e) => setBank(e.target.value)} className={FALT} autoComplete="off" />
        </Falt>
      </div>
      <LoneFaltVy f={lon} setF={setLon} />
      {fel && (
        <div className="mt-[14px]">
          <VyBanner ton="fel" text={fel} />
        </div>
      )}
      <div className="flex items-center gap-3 pt-4">
        <Knapp disabled={skapa.isPending}>{skapa.isPending ? "Sparar…" : "Lägg till anställd"}</Knapp>
        {!forsta && (
          <Knapp type="button" sekundar onClick={() => setOppen(false)}>
            Avbryt
          </Knapp>
        )}
      </div>
    </form>
  );
}

function AndraAnstalld({ a }: { a: PayrollEmployee }) {
  const uppdatera = useUppdatera();
  const [namn, setNamn] = useState(a.name);
  const [pnr, setPnr] = useState(a.personal_number ?? "");
  const [epost, setEpost] = useState(a.email ?? "");
  const [bank, setBank] = useState(a.bank_account ?? "");
  const [lon, setLon] = useState<LoneFalt>(() => loneFaltFran(a));
  const [fel, setFel] = useState<string | null>(null);
  const [sparat, setSparat] = useState(false);
  const startLon = loneFaltFran(a);

  const spara = useMutation({
    mutationFn: async (aktiv: boolean) => {
      const uppgifterAndrade =
        namn.trim() !== a.name ||
        (pnr.trim() || null) !== (a.personal_number ?? null) ||
        (epost.trim() || null) !== (a.email ?? null) ||
        (bank.trim() || null) !== (a.bank_account ?? null) ||
        aktiv !== a.active;
      const lonAndrad = JSON.stringify(lon) !== JSON.stringify(startLon);
      const tolkad = lonAndrad && aktiv ? tolkaLon(lon) : null;
      if (tolkad && "fel" in tolkad) throw new Error(tolkad.fel);
      if (uppgifterAndrade) {
        await anstalldaApi.andra(a.id, {
          name: namn.trim(),
          personal_number: pnr.trim() || null,
          email: epost.trim() || null,
          bank_account: bank.trim() || null,
          active: aktiv,
        });
      }
      if (tolkad && "lon" in tolkad) await anstalldaApi.sattLon(a.id, tolkad.lon);
    },
    onMutate: () => {
      setFel(null);
      setSparat(false);
    },
    onSuccess: () => setSparat(true),
    onError: (e) => setFel(e instanceof Error && !("response" in e) ? e.message : felText(e, "Kunde inte spara.")),
    onSettled: () => void uppdatera(),
  });

  const pnrVisas = maskeraPersonnummer(a.personal_number);

  return (
    <form
      className="flex flex-col pb-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (!namn.trim()) {
          setFel("Namnet kan inte vara tomt.");
          return;
        }
        spara.mutate(a.active);
      }}
    >
      <div className="grid grid-cols-1 gap-3 pt-2 sm:grid-cols-2">
        <Falt etikett="Namn">
          <input value={namn} onChange={(e) => setNamn(e.target.value)} className={FALT} autoComplete="off" />
        </Falt>
        <Falt etikett="Personnummer" hjalp={pnrVisas ? undefined : "Krävs för arbetsgivardeklarationen."}>
          <input value={pnr} onChange={(e) => setPnr(e.target.value)} className={FALT} autoComplete="off" />
        </Falt>
        <Falt etikett="E-post">
          <input type="email" value={epost} onChange={(e) => setEpost(e.target.value)} className={FALT} />
        </Falt>
        <Falt etikett="Bankkonto">
          <input value={bank} onChange={(e) => setBank(e.target.value)} className={FALT} autoComplete="off" />
        </Falt>
      </div>
      {a.active && <LoneFaltVy f={lon} setF={setLon} />}
      {fel && (
        <div className="mt-[14px]">
          <VyBanner ton="fel" text={fel} />
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3 pt-4">
        {a.active ? (
          <>
            <Knapp disabled={spara.isPending}>{spara.isPending ? "Sparar…" : "Spara"}</Knapp>
            <Knapp type="button" sekundar disabled={spara.isPending} onClick={() => spara.mutate(false)}>
              Har slutat
            </Knapp>
          </>
        ) : (
          <Knapp type="button" disabled={spara.isPending} onClick={() => spara.mutate(true)}>
            Anställd igen
          </Knapp>
        )}
        {sparat && <span className="bok-mono text-[12px] text-bok-klart-meta">sparat</span>}
      </div>
    </form>
  );
}

const MANADER = [
  "januari", "februari", "mars", "april", "maj", "juni",
  "juli", "augusti", "september", "oktober", "november", "december",
];

function denHarManaden(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/**
 * Månadens lönekörning: ett lönebesked per aktiv anställd med lön, med
 * utbetalning på dagen de flesta har. Körningen och beskeden visas och
 * bokförs i Löner.
 */
function Lonekorning({
  anstallda,
  onGaTill,
}: {
  anstallda: PayrollEmployee[];
  onGaTill: (key: Vynyckel) => void;
}) {
  const uppdatera = useUppdatera();
  const [manad, setManad] = useState(denHarManaden);
  const [dag, setDag] = useState(() => String(vanligasteUtbetalningsdag(anstallda)));
  const [fel, setFel] = useState<string | null>(null);
  const [klar, setKlar] = useState<string | null>(null);

  const medLon = anstallda.filter((a) => a.active && a.salary_setting?.active);
  const [ar, man] = manad.split("-").map(Number);
  const giltig = Number.isInteger(ar) && man >= 1 && man <= 12;
  const dagNr = Number(dag);
  const datum = giltig && Number.isInteger(dagNr) && dagNr >= 1 ? utbetalningsdatum(ar, man, dagNr) : null;
  const brutto = medLon.reduce((s, a) => s + (a.salary_setting?.gross_monthly_salary ?? 0), 0);

  const skapa = useMutation({
    mutationFn: () => anstalldaApi.skapaKorning(ar, man, datum!),
    onMutate: () => {
      setFel(null);
      setKlar(null);
    },
    onSuccess: (k) =>
      setKlar(
        `${k.payslip_count} lönebesked för ${MANADER[man - 1]} ${ar} är skapade. Be agenten bokföra dem i Löner.`
      ),
    onError: (e) => setFel(felText(e, "Kunde inte skapa lönebeskeden.")),
    onSettled: () => void uppdatera(),
  });

  return (
    <form
      className="flex flex-col"
      onSubmit={(e) => {
        e.preventDefault();
        if (!datum) {
          setFel("Välj månad och utbetalningsdag.");
          return;
        }
        skapa.mutate();
      }}
    >
      <Rubrik>Månadens lönebesked</Rubrik>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Falt etikett="Månad">
          <input type="month" value={manad} onChange={(e) => setManad(e.target.value)} className={FALT} />
        </Falt>
        <Falt etikett="Utbetalningsdag" hjalp={datum ? `utbetalning ${datum}` : undefined}>
          <input inputMode="numeric" value={dag} onChange={(e) => setDag(e.target.value)} className={FALT} />
        </Falt>
      </div>
      <div className="bok-mono pt-2 text-[12px] text-bok-meta">
        {medLon.length === 0
          ? "Ingen anställd har en lön inställd."
          : `${medLon.length} lönebesked · brutto ${formatBeloppHela(brutto)}`}
      </div>
      {fel && (
        <div className="mt-[14px]">
          <VyBanner ton="fel" text={fel} />
        </div>
      )}
      {klar && (
        <div className="mt-[14px]">
          <VyBanner ton="klart" text={klar} />
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3 pt-4">
        <Knapp disabled={skapa.isPending || medLon.length === 0}>
          {skapa.isPending ? "Skapar…" : "Skapa lönebesked"}
        </Knapp>
        {klar && (
          <button
            type="button"
            onClick={() => onGaTill("betala.loner")}
            className="bok-mono text-[12px] text-bok-lank underline-offset-2 hover:underline"
          >
            Till Löner →
          </button>
        )}
      </div>
    </form>
  );
}
