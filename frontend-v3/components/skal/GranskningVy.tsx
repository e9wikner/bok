"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { AgentText } from "@/components/chattyta/TradInlagg";
import { useDetalj } from "@/components/skal/DetaljKontext";
import { VyBanner } from "@/components/skal/VyBanner";
import { VyHeaderStatus } from "@/components/skal/VyHeaderStatus";
import { VyRadSkelett } from "@/components/skal/VyRad";
import apiClient from "@/lib/api";
import {
  ALLVARLIGHETER,
  ALLVARLIGHET_TEXT,
  type Allvarlighet,
  type Anmarkning,
  type AnmarkningsVerifikation,
  type Antal,
  type GranskningsVal,
  type Rapport,
  type Rapportrad,
  type Tackning,
  beloppKr,
  granskareText,
  granskningApi,
  granskningStatus,
  ingangUrl,
  lasVal,
  omradeText,
  rapportNyckel,
  rapporterNyckel,
  sorteraAnmarkningar,
  sorteraRapporter,
  sparaVal,
  tackningNyckel,
  tackningsrader,
  uppladdadText,
} from "@/lib/skal/granskning";
import { lageFarg } from "@/lib/skal/lage";

/**
 * Granskning (`bokslut.granskning`): granskningsrapporterna som externa
 * agenter har laddat upp för året i årsväljaren, och Täckning, som visar
 * vilka verifikationer rapporterna anmärkte på. Bok granskar ingenting
 * själv (`docs/granskning.md`). Ett fel som en rapport pekar ut rättas i
 * bokföringen, med en B-verifikation. Chattar i Översiktens tråd.
 */

/** Den fasta texten, ordagrant ur specen. Den står i frontend, aldrig i agentens rapport. */
export const FAST_TEXT = "Granskningen är styrelsens egen kontroll. Den är inte en revision och ersätter inte en revisor.";

const ALLVARLIGHET_FARG: Record<Allvarlighet, string> = {
  material: "text-bok-fel-meta",
  should_fix: "text-bok-vantar-meta",
  observation: "text-bok-meta",
};

export function GranskningVy({
  titel,
  arId,
  arEtikett,
  variant,
}: {
  titel: string;
  /** Året i årsväljaren; `null` när det inte finns något räkenskapsår. */
  arId: string | null | undefined;
  /** Årets namn, "2025", till texten som en agent kan få. */
  arEtikett?: string;
  variant: "desktop" | "mobil";
}) {
  const rapporter = useQuery({
    queryKey: rapporterNyckel(arId ?? ""),
    queryFn: () => granskningApi.rapporter(arId ?? ""),
    enabled: !!arId,
    staleTime: 30 * 1000,
  });
  const [val, setValState] = useState<GranskningsVal>(() => (arId ? lasVal(arId) : { flik: "rapporter", rapport: null }));
  // Ett annat år har sitt eget val.
  useEffect(() => {
    if (arId) setValState(lasVal(arId));
  }, [arId]);
  const setVal = (ny: GranskningsVal) => {
    setValState(ny);
    if (arId) sparaVal(arId, ny);
  };

  const status = granskningStatus(rapporter.data, rapporter.isError, arId);
  const pad = variant === "desktop" ? "px-6" : "px-[18px]";

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
        <div className="mt-[14px]">
          <VyBanner ton="neutral" text={FAST_TEXT} />
        </div>

        {arId === null ? (
          <div className="pt-5 text-[13px] text-bok-text-svag">Det finns inget räkenskapsår att granska.</div>
        ) : rapporter.isError ? (
          <div className="mt-[14px]">
            <VyBanner ton="fel" text="Granskningsrapporterna kunde inte läsas. Ladda om sidan." />
          </div>
        ) : !rapporter.data || !arId ? (
          <div className="pt-5">
            <VyRadSkelett />
          </div>
        ) : (
          <>
            <div role="group" aria-label="Visa" className="flex flex-wrap gap-[6px] pt-[14px]">
              {(
                [
                  { key: "rapporter", titel: "Rapporter" },
                  { key: "tackning", titel: "Täckning" },
                ] as const
              ).map((f) => (
                <button
                  key={f.key}
                  type="button"
                  aria-pressed={val.flik === f.key}
                  onClick={() => setVal({ ...val, flik: f.key })}
                  className={`bok-mono rounded-full border px-[10px] py-[3px] text-[12px] ${
                    val.flik === f.key
                      ? "border-bok-text bg-bok-text text-bok-yta"
                      : "border-bok-linje text-bok-text-2 hover:bg-bok-yta-svag"
                  }`}
                >
                  {f.titel}
                </button>
              ))}
            </div>

            {val.flik === "tackning" ? (
              <TackningFlik arId={arId} />
            ) : val.rapport && rapporter.data.some((r) => r.id === val.rapport) ? (
              <RapportDetalj id={val.rapport} onTillbaka={() => setVal({ ...val, rapport: null })} />
            ) : rapporter.data.length === 0 ? (
              <TomtLage arId={arId} arEtikett={arEtikett} />
            ) : (
              <RapportLista rapporter={rapporter.data} onOppna={(id) => setVal({ ...val, rapport: id })} />
            )}
          </>
        )}

        <div className="pt-5 text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">
          En rapport ändras aldrig. En ny granskning blir en ny rapport, och flera granskare kan jämföras sida vid
          sida. Det en rapport pekar ut rättas i bokföringen, med en rättelseverifikation.
        </div>
      </div>
    </div>
  );
}

// ─── Byggstenar ───────────────────────────────────────────────────────────

function Rubrik({ children }: { children: React.ReactNode }) {
  return <div className="bok-etikett pb-[6px] pt-5 text-[10px] text-bok-meta">{children}</div>;
}

function AldreInstruktion() {
  return <span className="text-bok-vantar-meta">granskad mot en äldre instruktion</span>;
}

/** "2 väsentliga · 1 bör rättas · 0 iakttagelser", varje antal i sin färg. */
function AntalPerAllvarlighet({ c }: { c: Antal }) {
  return (
    <span className="flex flex-wrap justify-end gap-x-3 gap-y-[2px]">
      {ALLVARLIGHETER.map((s) => (
        <span key={s} className={c[s] > 0 ? ALLVARLIGHET_FARG[s] : "text-bok-meta"} data-testid={`antal-${s}`}>
          {c[s]} {ALLVARLIGHET_TEXT[s].toLowerCase()}
        </span>
      ))}
    </span>
  );
}

function VerifikationsLank({ v }: { v: { id: string; number: string } }) {
  const detalj = useDetalj();
  const text = v.number || "verifikation";
  if (!detalj || !v.id) return <span className="bok-mono">{text}</span>;
  return (
    <button
      type="button"
      onClick={() => detalj.oppna({ typ: "ver", id: v.id })}
      className="bok-mono text-bok-lank underline-offset-2 hover:text-bok-lank-hover hover:underline"
    >
      {text}
    </button>
  );
}

// ─── Rapporterna ──────────────────────────────────────────────────────────

function RapportLista({ rapporter, onOppna }: { rapporter: Rapportrad[]; onOppna: (id: string) => void }) {
  return (
    <>
      <Rubrik>Granskningsrapporter</Rubrik>
      {sorteraRapporter(rapporter).map((r) => (
        <button
          key={r.id}
          type="button"
          data-testid="granskningsrapport"
          onClick={() => onOppna(r.id)}
          className="-mx-2 flex w-[calc(100%+16px)] items-start justify-between gap-3 border-b border-bok-linje-svagast px-2 py-[8px] text-left hover:bg-bok-yta-svag"
        >
          <span className="min-w-0">
            <span className="block text-[14px] leading-[1.35] text-bok-text">
              {granskareText(r.reviewer_agent, r.reviewer_model)}
            </span>
            <span className="bok-mono block pt-[2px] text-[11px] leading-[1.45] text-bok-meta">
              {uppladdadText(r.uploaded_at)}
              {r.instruction_outdated && (
                <>
                  {" · "}
                  <AldreInstruktion />
                </>
              )}
            </span>
          </span>
          <span className="bok-mono bok-tal shrink-0 text-right text-[12px]">
            <AntalPerAllvarlighet c={r.counts} />
          </span>
        </button>
      ))}
    </>
  );
}

function TomtLage({ arId, arEtikett }: { arId: string; arEtikett?: string }) {
  const url = ingangUrl(apiClient.defaults.baseURL, typeof window === "undefined" ? "" : window.location.origin);
  const aret = ["Granska räkenskapsåret", arEtikett, `(fiscal_year_id ${arId})`].filter(Boolean).join(" ");
  const uppdrag = `${aret} och ladda upp en granskningsrapport. Börja här: ${url}`;
  return (
    <>
      <Rubrik>Ingen rapport än</Rubrik>
      <div className="flex flex-col gap-3 text-[14px] leading-[1.55] text-bok-text-2 [text-wrap:pretty]">
        <p className="m-0">
          Det finns ingen granskningsrapport för året. Bok granskar inte själv: en agent, vilken som helst, läser
          böckerna genom API:et och laddar upp sin rapport hit.
        </p>
        <p className="m-0">Peka agenten på ingången, som säger hur den autentiserar sig och var instruktionen finns:</p>
        <code
          data-testid="granskning-ingang"
          className="bok-mono block select-all break-all rounded-md bg-bok-bubbla px-3 py-2 text-[13px] text-bok-text"
        >
          {url}
        </code>
        <p className="m-0">
          Agenten behöver granskningsnyckeln, <span className="bok-mono text-[13px]">BOKFOERING_REVIEW_KEY</span>,
          som bearer. Den nyckeln kan bara läsa och ladda upp en rapport; ge aldrig agenten bokföringens nyckel. Till
          exempel:
        </p>
        <code className="bok-mono block select-all whitespace-pre-wrap break-words rounded-md bg-bok-bubbla px-3 py-2 text-[13px] text-bok-text">
          {uppdrag}
        </code>
        <p className="m-0 text-[13px] text-bok-text-svag">
          Kör flera agenter eller modeller, så får du flera oberoende rapporter om samma år att jämföra under Täckning.
        </p>
      </div>
    </>
  );
}

function RapportDetalj({ id, onTillbaka }: { id: string; onTillbaka: () => void }) {
  const { data, isError } = useQuery({
    queryKey: rapportNyckel(id),
    queryFn: () => granskningApi.rapport(id),
    // En rapport ändras aldrig.
    staleTime: Infinity,
  });
  return (
    <>
      <button
        type="button"
        onClick={onTillbaka}
        className="bok-mono self-start pt-[14px] text-left text-[12px] text-bok-lank underline-offset-2 hover:text-bok-lank-hover hover:underline"
      >
        ← Alla rapporter
      </button>
      {isError ? (
        <div className="mt-[14px]">
          <VyBanner ton="fel" text="Rapporten kunde inte läsas. Ladda om sidan." />
        </div>
      ) : !data ? (
        <div className="pt-5">
          <VyRadSkelett />
        </div>
      ) : (
        <RapportInnehall r={data} />
      )}
    </>
  );
}

function RapportInnehall({ r }: { r: Rapport }) {
  const anmarkningar = sorteraAnmarkningar(r.findings);
  return (
    <>
      <div className="pt-[14px] text-[16px] font-medium leading-tight text-bok-text">
        {granskareText(r.reviewer_agent, r.reviewer_model)}
      </div>
      <div className="bok-mono pt-1 text-[12px] leading-[1.5] text-bok-meta">
        {uppladdadText(r.uploaded_at)} · uppladdad av {r.uploaded_by || "okänd"} · prövade {r.examined_voucher_count}{" "}
        {r.examined_voucher_count === 1 ? "verifikation" : "verifikationer"}
        {r.instruction_outdated && (
          <>
            {" · "}
            <AldreInstruktion />
          </>
        )}
      </div>
      <div className="bok-mono bok-tal pt-1 text-[12px]">
        <span className="inline-flex">
          <AntalPerAllvarlighet c={r.counts} />
        </span>
      </div>

      <Rubrik>Sammanfattning</Rubrik>
      {r.summary_markdown.trim() ? (
        <div data-testid="granskning-sammanfattning">
          <AgentText text={r.summary_markdown} />
        </div>
      ) : (
        <div className="bok-mono text-[12px] text-bok-meta">Ingen sammanfattning.</div>
      )}

      <Rubrik>Anmärkningar</Rubrik>
      {anmarkningar.length === 0 ? (
        <div className="text-[14px] text-bok-text-2">Inga anmärkningar.</div>
      ) : (
        anmarkningar.map((a) => <AnmarkningRad key={a.id || a.position} a={a} />)
      )}
    </>
  );
}

function AnmarkningRad({ a }: { a: Anmarkning }) {
  const belopp = beloppKr(a.amount_ore);
  return (
    <div data-testid="anmarkning" className="flex flex-col gap-[6px] border-b border-bok-linje-svagast py-3">
      <div className="bok-mono flex flex-wrap gap-x-2 text-[11px] leading-[1.45]">
        <span className={`font-medium ${ALLVARLIGHET_FARG[a.severity]}`}>{ALLVARLIGHET_TEXT[a.severity]}</span>
        <span className="text-bok-meta">·</span>
        <span className="text-bok-meta">{omradeText(a.area)}</span>
      </div>
      <div className="text-[14px] font-medium leading-[1.35] text-bok-text">{a.title}</div>
      {a.description && (
        <div className="whitespace-pre-line text-[14px] leading-[1.55] text-bok-text-2 [text-wrap:pretty]">
          {a.description}
        </div>
      )}
      <dl className="m-0 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-[13px] leading-[1.5]">
        {a.rule && <Uppgift etikett="Regel">{a.rule}</Uppgift>}
        {belopp && (
          <Uppgift etikett="Belopp">
            <span className="bok-mono bok-tal">{belopp}</span>
          </Uppgift>
        )}
        {a.suggested_correction && (
          <Uppgift etikett="Förslag till rättelse">
            <span className="whitespace-pre-line">{a.suggested_correction}</span>
          </Uppgift>
        )}
        {a.vouchers.length > 0 && (
          <Uppgift etikett={a.vouchers.length === 1 ? "Verifikation" : "Verifikationer"}>
            <span className="flex flex-wrap gap-x-3 gap-y-1">
              {a.vouchers.map((v: AnmarkningsVerifikation) => (
                <span key={v.id} className="whitespace-nowrap">
                  <VerifikationsLank v={v} />
                  {v.date && <span className="bok-mono pl-1 text-[12px] text-bok-meta">{v.date}</span>}
                </span>
              ))}
            </span>
          </Uppgift>
        )}
      </dl>
    </div>
  );
}

function Uppgift({ etikett, children }: { etikett: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-bok-meta">{etikett}</dt>
      <dd className="m-0 min-w-0 text-bok-text-2">{children}</dd>
    </>
  );
}

// ─── Täckning ─────────────────────────────────────────────────────────────

const CELL = "border-b border-bok-linje-svagast px-2 py-[7px] text-left align-top";
const RUBRIKCELL = "border-b border-bok-kant px-2 pb-[6px] pt-2 text-left align-bottom font-normal text-bok-text-svag";

function TackningFlik({ arId }: { arId: string }) {
  const { data, isError } = useQuery({
    queryKey: tackningNyckel(arId),
    queryFn: () => granskningApi.tackning(arId),
    staleTime: 30 * 1000,
  });
  if (isError) {
    return (
      <div className="mt-[14px]">
        <VyBanner ton="fel" text="Täckningen kunde inte läsas. Ladda om sidan." />
      </div>
    );
  }
  if (!data) {
    return (
      <div className="pt-5">
        <VyRadSkelett />
      </div>
    );
  }
  return <TackningTabell t={data} />;
}

export function TackningTabell({ t }: { t: Tackning }) {
  const rader = tackningsrader(t);
  return (
    <>
      <Rubrik>Verifikationer med anmärkning</Rubrik>
      <div className="pb-2 text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">
        En anmärkning som flera granskare har gjort oberoende av varandra väger tyngre än en som bara en har gjort.
        Flest granskare står först.
      </div>
      {t.report_count === 0 ? (
        <div className="bok-mono pt-2 text-[12px] text-bok-meta">Ingen rapport än.</div>
      ) : rader.length === 0 ? (
        <div className="bok-mono pt-2 text-[12px] text-bok-meta">Ingen rapport anmärkte på en enskild verifikation.</div>
      ) : (
        <div className="-mx-2 overflow-x-auto">
          <table className="bok-tal w-full min-w-[640px] border-collapse text-[13px] leading-[1.45]">
            <thead className="bok-mono text-[11px]">
              <tr>
                <th className={RUBRIKCELL}>Verifikation</th>
                <th className={RUBRIKCELL}>Datum</th>
                <th className={RUBRIKCELL}>Beskrivning</th>
                <th className={`${RUBRIKCELL} text-right`}>Prövad av</th>
                <th className={RUBRIKCELL}>Anmärkt av</th>
              </tr>
            </thead>
            <tbody>
              {rader.map((v) => (
                <tr key={v.voucher_id} data-testid="tackningsrad">
                  <td className={`${CELL} whitespace-nowrap`}>
                    <VerifikationsLank v={{ id: v.voucher_id, number: v.number }} />
                  </td>
                  <td className={`${CELL} bok-mono whitespace-nowrap text-bok-text-2`}>{v.date}</td>
                  <td className={`${CELL} text-bok-text`}>{v.description}</td>
                  <td className={`${CELL} bok-mono whitespace-nowrap text-right text-bok-text-2`}>
                    {v.examined_by_count} av {t.report_count}
                  </td>
                  <td className={CELL}>
                    <ul className="m-0 flex list-none flex-col gap-[2px] p-0">
                      {v.granskare.map((g) => (
                        <li key={g.nyckel}>
                          <span className="text-bok-text">{granskareText(g.agent, g.model)}</span>{" "}
                          <span className={`bok-mono text-[11px] ${ALLVARLIGHET_FARG[g.severity]}`}>
                            {ALLVARLIGHET_TEXT[g.severity].toLowerCase()}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
