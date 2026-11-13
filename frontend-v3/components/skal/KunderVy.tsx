"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { FALT, Falt, Knapp, Rubrik } from "@/components/skal/Formular";
import { VyBanner } from "@/components/skal/VyBanner";
import { VyHeaderStatus } from "@/components/skal/VyHeaderStatus";
import { VyRadSkelett } from "@/components/skal/VyRad";
import { felText } from "@/lib/skal/anstallda";
import { formatBelopp } from "@/lib/skal/format";
import {
  ARTIKLAR_NYCKEL,
  KUNDER_NYCKEL,
  MOMSKODER,
  artikelMeta,
  kronorTillOre,
  kundMeta,
  kunderApi,
  kunderStatus,
} from "@/lib/skal/kunder";
import { lageFarg } from "@/lib/skal/lage";

/**
 * Kunder och artiklar (`betala.kunder`): registren fakturorna skrivs ur.
 * Ingen egen tråd — den chattar i Fakturerings.
 */
export function KunderVy({ titel, variant }: { titel: string; variant: "desktop" | "mobil" }) {
  const kunder = useQuery({ queryKey: KUNDER_NYCKEL, queryFn: kunderApi.kunder, staleTime: 60 * 1000 });
  const artiklar = useQuery({ queryKey: ARTIKLAR_NYCKEL, queryFn: kunderApi.artiklar, staleTime: 60 * 1000 });
  const isError = kunder.isError || artiklar.isError;
  const status = kunderStatus(kunder.data, artiklar.data, isError);
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
        {isError ? (
          <div className="mt-[14px]">
            <VyBanner ton="fel" text="Kunderna och artiklarna kunde inte läsas. Ladda om sidan." />
          </div>
        ) : !kunder.data || !artiklar.data ? (
          <div className="pt-5">
            <VyRadSkelett />
          </div>
        ) : (
          <>
            <Rubrik>Kunder</Rubrik>
            {kunder.data.map((k) => (
              <Rad key={k.id} titel={k.name} meta={kundMeta(k)} hoger="" />
            ))}
            <NyKund />

            <Rubrik>Artiklar</Rubrik>
            {artiklar.data.map((a) => (
              <Rad key={a.id} titel={a.name} meta={artikelMeta(a)} hoger={formatBelopp(a.unit_price)} />
            ))}
            <NyArtikel />
          </>
        )}

        <div className="pt-5 text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">
          Agenten läser kunderna och artiklarna när den lägger fram en faktura. Du kan också be den lägga till en kund.
        </div>
      </div>
    </div>
  );
}

function Rad({ titel, meta, hoger }: { titel: string; meta: string; hoger: string }) {
  return (
    <div data-testid="registerrad" className="flex items-baseline gap-3 border-b border-bok-linje-svagast py-[7px]">
      <div className="min-w-0 flex-1">
        <div className="text-[14px] leading-[1.35] text-bok-text">{titel}</div>
        <div className="bok-mono pt-[2px] text-[11px] leading-[1.45] text-bok-meta">{meta}</div>
      </div>
      {hoger && <span className="bok-mono bok-tal shrink-0 text-[14px]">{hoger}</span>}
    </div>
  );
}

/** En knapp som fäller ut formuläret, och fäller ihop det när det är sparat. */
function Utfallbar({ etikett, children }: { etikett: string; children: (stang: () => void) => React.ReactNode }) {
  const [oppen, setOppen] = useState(false);
  return oppen ? (
    <div className="pt-3">{children(() => setOppen(false))}</div>
  ) : (
    <div className="pt-3">
      <Knapp type="button" sekundar onClick={() => setOppen(true)}>
        {etikett}
      </Knapp>
    </div>
  );
}

function NyKund() {
  const queryClient = useQueryClient();
  return (
    <Utfallbar etikett="Ny kund">
      {(stang) => <KundFormular onSparad={() => { void queryClient.invalidateQueries({ queryKey: KUNDER_NYCKEL }); stang(); }} onAvbryt={stang} />}
    </Utfallbar>
  );
}

function KundFormular({ onSparad, onAvbryt }: { onSparad: () => void; onAvbryt: () => void }) {
  const [namn, setNamn] = useState("");
  const [orgnr, setOrgnr] = useState("");
  const [epost, setEpost] = useState("");
  const [adress, setAdress] = useState("");
  const [dagar, setDagar] = useState("30");
  const [fel, setFel] = useState<string | null>(null);
  const spara = useMutation({
    mutationFn: kunderApi.skapaKund,
    onMutate: () => setFel(null),
    onSuccess: onSparad,
    onError: (e) => setFel(felText(e, "Kunden kunde inte sparas.")),
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const villkor = Number(dagar);
        if (!namn.trim()) return setFel("Kunden behöver ett namn.");
        if (!Number.isInteger(villkor) || villkor < 0) return setFel("Betalningsvillkoret är ett antal dagar.");
        spara.mutate({
          name: namn.trim(),
          org_number: orgnr.trim() || null,
          email: epost.trim() || null,
          address: adress.trim() || null,
          payment_terms_days: villkor,
        });
      }}
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Falt etikett="Namn">
          <input value={namn} onChange={(e) => setNamn(e.target.value)} className={FALT} />
        </Falt>
        <Falt etikett="Organisationsnummer">
          <input value={orgnr} onChange={(e) => setOrgnr(e.target.value)} className={FALT} />
        </Falt>
        <Falt etikett="E-post för fakturor">
          <input type="email" value={epost} onChange={(e) => setEpost(e.target.value)} className={FALT} />
        </Falt>
        <Falt etikett="Betalningsvillkor (dagar)">
          <input inputMode="numeric" value={dagar} onChange={(e) => setDagar(e.target.value)} className={FALT} />
        </Falt>
      </div>
      <Falt etikett="Adress" hjalp="Som på fakturan, en rad per rad.">
        <textarea value={adress} onChange={(e) => setAdress(e.target.value)} rows={3} className={FALT} />
      </Falt>
      {fel && <VyBanner ton="fel" text={fel} />}
      <div className="flex gap-3">
        <Knapp disabled={spara.isPending}>{spara.isPending ? "Sparar…" : "Spara kund"}</Knapp>
        <Knapp type="button" sekundar onClick={onAvbryt}>
          Avbryt
        </Knapp>
      </div>
    </form>
  );
}

function NyArtikel() {
  const queryClient = useQueryClient();
  return (
    <Utfallbar etikett="Ny artikel">
      {(stang) => <ArtikelFormular onSparad={() => { void queryClient.invalidateQueries({ queryKey: ARTIKLAR_NYCKEL }); stang(); }} onAvbryt={stang} />}
    </Utfallbar>
  );
}

function ArtikelFormular({ onSparad, onAvbryt }: { onSparad: () => void; onAvbryt: () => void }) {
  const [nummer, setNummer] = useState("");
  const [namn, setNamn] = useState("");
  const [enhet, setEnhet] = useState("h");
  const [pris, setPris] = useState("");
  const [moms, setMoms] = useState("MP1");
  const [konto, setKonto] = useState("3011");
  const [fel, setFel] = useState<string | null>(null);
  const spara = useMutation({
    mutationFn: kunderApi.skapaArtikel,
    onMutate: () => setFel(null),
    onSuccess: onSparad,
    onError: (e) => setFel(felText(e, "Artikeln kunde inte sparas.")),
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const ore = kronorTillOre(pris);
        if (!nummer.trim() || !namn.trim()) return setFel("Artikeln behöver ett nummer och ett namn.");
        if (ore === null) return setFel("Priset är ett belopp i kronor, t.ex. 950 eller 950,50.");
        if (!/^\d{4}$/.test(konto.trim())) return setFel("Intäktskontot är ett kontonummer med fyra siffror.");
        spara.mutate({
          article_number: nummer.trim(),
          name: namn.trim(),
          unit: enhet.trim() || "st",
          unit_price: ore,
          vat_code: moms,
          revenue_account: konto.trim(),
        });
      }}
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Falt etikett="Artikelnummer">
          <input value={nummer} onChange={(e) => setNummer(e.target.value)} className={FALT} />
        </Falt>
        <Falt etikett="Namn">
          <input value={namn} onChange={(e) => setNamn(e.target.value)} className={FALT} />
        </Falt>
        <Falt etikett="Pris exkl. moms (kr)">
          <input inputMode="decimal" value={pris} onChange={(e) => setPris(e.target.value)} className={FALT} />
        </Falt>
        <Falt etikett="Enhet">
          <input value={enhet} onChange={(e) => setEnhet(e.target.value)} className={FALT} />
        </Falt>
        <Falt etikett="Moms">
          <select value={moms} onChange={(e) => setMoms(e.target.value)} className={FALT}>
            {MOMSKODER.map((m) => (
              <option key={m.kod} value={m.kod}>
                {m.text}
              </option>
            ))}
          </select>
        </Falt>
        <Falt etikett="Intäktskonto">
          <input inputMode="numeric" value={konto} onChange={(e) => setKonto(e.target.value)} className={FALT} />
        </Falt>
      </div>
      {fel && <VyBanner ton="fel" text={fel} />}
      <div className="flex gap-3">
        <Knapp disabled={spara.isPending}>{spara.isPending ? "Sparar…" : "Spara artikel"}</Knapp>
        <Knapp type="button" sekundar onClick={onAvbryt}>
          Avbryt
        </Knapp>
      </div>
    </form>
  );
}
