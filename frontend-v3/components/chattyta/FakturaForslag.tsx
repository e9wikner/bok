"use client";

import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { useUtfardaFaktura, utfardaFelText, type UtfardaLage } from "@/hooks/useUtfardaFaktura";
import { UTFARDA_KVAR, type ForslagStatusSvar } from "@/lib/chattyta/api";
import { oppnaPdf } from "@/lib/chattyta/pdf";
import type { FakturaDraftInlagg, FakturaRadData } from "@/lib/chattyta/typer";
import type { UtfardandeForslag } from "@/lib/chattyta/utfardanden";
import { formatBelopp } from "@/lib/skal/format";

/**
 * `FakturaForslag` (komponenter.md: *"`FakturaForslag` (Rad / Antal /
 * Belopp)"*, SPEC-fakturering-f1.md §6.2): fakturan som kunden kommer att se
 * den. Samma skal som `VerifikationsForslag`, eftersom det är samma sorts
 * beslut.
 *
 * Kortet visar serverns kropp ordagrant. Ingen summa räknas här: öre in,
 * `formatBelopp` ut, och antalet delas bara med 100 för att skrivas.
 *
 * **Lägena** (§6.3) ur förslagets rad i `GET /drafts`:
 * - saknas eller `pending`: `Utfärda` och `Ändra`, med felraden om
 *   `last_error_code` finns;
 * - `issued`: `Utfärdad · {nummer} · {verifikation}` och `PDF`;
 * - `superseded`: `Ersatt av ett nytt förslag`;
 * - `rejected`: `Förkastat`.
 * Konsekvensnotisen står kvar i alla lägen.
 */
export function FakturaForslag({
  inlagg,
  knappar,
  forslag,
}: {
  inlagg: FakturaDraftInlagg;
  /** `UtfardaKnappar`, eller ingenting. Ritas bara i `pending`. */
  knappar?: ReactNode;
  forslag?: ForslagStatusSvar;
}) {
  const { title, meta, recipient, rows, totals, terms, footnote, consequence } = inlagg.body;
  const status = forslag?.status;

  return (
    <div
      data-inlagg-id={inlagg.id}
      data-testid="faktura-forslag"
      className="w-full max-w-[560px] overflow-hidden rounded-[12px] border border-bok-kant bg-bok-yta"
    >
      <div className="flex items-baseline justify-between gap-[14px] border-b border-bok-linje-svag px-[18px] py-[14px]">
        <span className="min-w-0 text-[15px] font-medium text-bok-text">{title}</span>
        <span className="bok-mono whitespace-nowrap text-[12px] text-bok-meta">{meta}</span>
      </div>

      {/* Mottagaren: namn, adress med sina radbrytningar, Er referens. */}
      <div data-testid="faktura-mottagare" className="px-[18px] pt-[10px] text-[13px] leading-[1.5] text-bok-text">
        <div>{recipient.name}</div>
        <div className="whitespace-pre-line text-bok-text-dampad">{recipient.address}</div>
        {recipient.reference && (
          <div className="text-bok-text-dampad">{`Er referens: ${recipient.reference}`}</div>
        )}
        <div className="bok-mono pt-[2px] text-[12px] text-bok-meta">{`Betalningsvillkor ${terms}`}</div>
      </div>

      <div className="flex items-baseline gap-[8px] px-[18px] pb-[2px] pt-[10px]">
        <span className="bok-mono flex-1 text-[10px] uppercase tracking-wide text-bok-meta">Rad</span>
        <span className="bok-mono w-[92px] text-right text-[10px] uppercase tracking-wide text-bok-meta">
          Antal
        </span>
        <span className="bok-mono w-[92px] text-right text-[10px] uppercase tracking-wide text-bok-meta">
          Belopp
        </span>
      </div>

      <div>
        {rows.map((rad, i) => (
          <FakturaRad key={`${rad.text}-${i}`} rad={rad} />
        ))}
      </div>

      <div data-testid="faktura-summor" className="px-[18px] pt-[6px]">
        {totals.map((t, i) => (
          <div
            key={`${t.key}-${i}`}
            data-testid="faktura-summa"
            className={`flex items-baseline justify-between gap-[8px] py-[4px] text-[14px] ${
              t.key === "total" ? "font-medium text-bok-text" : "text-bok-text-dampad"
            }`}
          >
            <span>{t.text}</span>
            <span className="bok-mono bok-tal whitespace-nowrap">{formatBelopp(t.amount_ore)}</span>
          </div>
        ))}
      </div>

      {footnote && (
        <p data-testid="forslag-fot" className="px-[18px] pt-[10px] text-[13px] leading-[1.55] text-[#78716c]">
          {footnote}
        </p>
      )}

      <div
        data-testid="forslag-knapprad"
        className="flex flex-wrap items-center gap-[10px] px-[18px] pb-[16px] pt-[14px]"
      >
        {status === "issued" ? (
          <UtfardadEtikett forslag={forslag} />
        ) : status === "superseded" ? (
          <Etikett testid="forslag-ersatt" text="Ersatt av ett nytt förslag" />
        ) : status === "rejected" ? (
          <Etikett testid="forslag-forkastat" text="Förkastat" />
        ) : (
          knappar
        )}
        <span className="bok-mono whitespace-pre-line text-[12px] text-bok-text-dampad">{consequence}</span>
      </div>
    </div>
  );
}

/** `24 h`, `7,5 h`: antalet delat med 100, decimaler med komma, och enheten. */
export function formatAntal(quantityCenti: number, enhet: string): string {
  const antal = new Intl.NumberFormat("sv-SE", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
    useGrouping: true,
  }).format(quantityCenti / 100);
  return `${antal.replace(/ /g, " ")} ${enhet}`;
}

function FakturaRad({ rad }: { rad: FakturaRadData }) {
  const detalj = [rad.delivery, `${formatBelopp(rad.unit_price_ore)} kr/${rad.unit}`]
    .filter(Boolean)
    .join(" · ");
  return (
    <div
      data-testid="faktura-rad"
      className="flex items-baseline gap-[8px] border-b border-bok-linje-svagast px-[18px] py-[9px]"
    >
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-[14px] text-bok-text">{rad.text}</span>
        <span className="bok-mono text-[12px] text-bok-meta">{detalj}</span>
      </span>
      <span data-kolumn="antal" className="bok-mono bok-tal w-[92px] whitespace-nowrap text-right text-[14px] text-bok-text">
        {formatAntal(rad.quantity_centi, rad.unit)}
      </span>
      <span data-kolumn="belopp" className="bok-mono bok-tal w-[92px] whitespace-nowrap text-right text-[14px] text-bok-text">
        {formatBelopp(rad.amount_ore)}
      </span>
    </div>
  );
}

const Etikett = ({ text, testid }: { text: string; testid: string }) => (
  <span
    role="status"
    data-testid={testid}
    className="bok-mono rounded-full border border-bok-linje bg-bok-linje-svagast px-[10px] py-[3px] text-[12px] text-bok-text-dampad"
  >
    {text}
  </span>
);

const KLAR =
  "bok-mono rounded-full border border-bok-klart-kant bg-bok-klart-yta px-[10px] py-[3px] text-[12px] text-bok-klart-text outline-none";

const PRIMAR =
  "min-h-[46px] rounded-[8px] bg-bok-black px-[16px] text-[14px] font-medium text-bok-yta hover:bg-bok-black-hover aria-disabled:cursor-default aria-disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-bok-lank";
const SEKUNDAR =
  "min-h-[46px] rounded-[8px] border border-bok-kant bg-bok-yta px-[16px] text-[14px] text-bok-text hover:bg-bok-yta-svag aria-disabled:cursor-default aria-disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-bok-lank";

function PdfKnapp({ pdfUrl }: { pdfUrl: string }) {
  return (
    <button type="button" data-testid="oppna-pdf" onClick={() => void oppnaPdf(pdfUrl)} className={SEKUNDAR}>
      PDF
    </button>
  );
}

function UtfardadEtikett({
  forslag,
  nummer,
  pdfUrl,
  etikettRef,
}: {
  forslag?: ForslagStatusSvar;
  nummer?: string | null;
  pdfUrl?: string | null;
  etikettRef?: (el: HTMLElement | null) => void;
}) {
  const faktura = forslag?.invoice;
  const delar = ["Utfärdad", nummer ?? faktura?.invoice_number, faktura?.voucher].filter(Boolean);
  const pdf = pdfUrl ?? faktura?.pdf_url ?? null;
  return (
    <>
      <span ref={etikettRef} tabIndex={-1} role="status" data-testid="utfarda-klart" className={KLAR}>
        {delar.join(" · ")}
      </span>
      {pdf && <PdfKnapp pdfUrl={pdf} />}
    </>
  );
}

/**
 * `Utfärda` + `Ändra` och utfallen i §7.1. Kortet ger bara `draftId`; ingen
 * faktura konstrueras här (regel 3). `onAndra` fokuserar chattfältet och
 * skickar ingenting.
 */
export function UtfardaKnappar({
  inlagg,
  onAndra,
  serverFel,
}: {
  inlagg: FakturaDraftInlagg;
  onAndra?: () => void;
  /** `last_error_code` ur `GET /drafts`. */
  serverFel?: string | null;
}) {
  const body = inlagg.body;
  // Ögonblicksbilden för vyns optimistiska rad (§10.2), ur kortets egna fält.
  const forslag: UtfardandeForslag = useMemo(
    () => ({
      kund: body.recipient.name,
      nummer: body.title.replace(/^Faktura\s+/, "").split(" · ")[0] ?? "",
      belopp: body.totals.find((t) => t.key === "total")?.amount_ore ?? 0,
      forfaller: body.totals.find((t) => t.key === "total")?.text.replace(/^Att betala senast\s+/, "") ?? "",
    }),
    [body]
  );
  const { lage: egetLage, langsam, utfarda } = useUtfardaFaktura(body.draft_id, forslag);
  const lage = medServerFel(egetLage, serverFel);
  const utfardar = lage.lage === "utfardar";

  const flyttaFokus = useRef(false);
  const utfallRef = useRef<HTMLElement | null>(null);
  const satUtfall = (el: HTMLElement | null) => {
    utfallRef.current = el;
  };
  useEffect(() => {
    if (!flyttaFokus.current || lage.lage === "utfardar" || lage.lage === "redo") return;
    flyttaFokus.current = false;
    utfallRef.current?.focus();
  }, [lage]);

  if (lage.lage === "utfardad") {
    return (
      <UtfardadEtikett
        etikettRef={satUtfall}
        nummer={lage.faktura?.invoice_number ?? forslag.nummer}
        pdfUrl={lage.faktura?.pdf_url}
      />
    );
  }
  if (lage.lage === "ersatt") {
    return <Etikett testid="forslag-ersatt" text="Ersatt av ett nytt förslag" />;
  }

  const fel =
    lage.lage === "fel"
      ? utfardaFelText(lage.kod)
      : lage.lage === "natverk"
        ? "Svaret kom inte fram. Försök igen — samma förslag kan bara bli en faktura."
        : null;
  // Knappen tas bort vid trycket (§7.1) och står kvar bara där ett nytt
  // tryck kan lyckas (beslut 8).
  const kanUtfarda = lage.lage === "redo" || lage.lage === "natverk" || (lage.lage === "fel" && lage.kvar);

  return (
    <>
      {fel && (
        <p
          ref={satUtfall}
          tabIndex={-1}
          role="status"
          data-testid="utfarda-fel"
          className="m-0 basis-full rounded-[8px] border border-bok-fel-kant bg-bok-fel-yta px-[12px] py-[8px] text-[13px] leading-[1.5] text-bok-fel-text outline-none"
        >
          {fel}
        </p>
      )}
      {utfardar && (
        <span role="status" data-testid="utfardar" className="bok-mono text-[12px] text-bok-text-dampad">
          {langsam ? "Utfärdar fortfarande…" : "Utfärdar…"}
        </span>
      )}
      {kanUtfarda && (
        <button
          type="button"
          onClick={() => {
            flyttaFokus.current = true;
            utfarda();
          }}
          className={PRIMAR}
        >
          {lage.lage === "natverk" ? "Försök igen" : "Utfärda"}
        </button>
      )}
      {onAndra && !utfardar && (
        <button type="button" onClick={onAndra} className={SEKUNDAR}>
          Ändra
        </button>
      )}
    </>
  );
}

/**
 * Klickets eget utfall går före serverns felkod, utom när det inte säger
 * något (`redo`). Efter en omladdning bär raden bara koden.
 */
function medServerFel(lage: UtfardaLage, serverFel: string | null | undefined): UtfardaLage {
  if (!serverFel || lage.lage !== "redo") return lage;
  return {
    lage: "fel",
    kod: serverFel,
    kvar: UTFARDA_KVAR.has(serverFel),
  };
}
