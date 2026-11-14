"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { FALT, Falt, Knapp, Rubrik } from "@/components/skal/Formular";
import { VyBanner } from "@/components/skal/VyBanner";
import { VyHeaderStatus } from "@/components/skal/VyHeaderStatus";
import { VyRadSkelett } from "@/components/skal/VyRad";
import { felText } from "@/lib/skal/anstallda";
import { tidpunkt } from "@/lib/skal/dropzone";
import {
  type Instruktioner,
  KORRIGERINGAR_NYCKEL,
  type Omfang,
  instruktionNyckel,
  instruktionStatus,
  instruktionerApi,
  korrigeringText,
} from "@/lib/skal/instruktioner";
import { lageFarg } from "@/lib/skal/lage";

const OM: Record<Omfang, string> = {
  accounting: "Agenten läser reglerna före varje bokföringspass, efter systeminstruktionerna.",
  invoicing: "Agenten läser reglerna innan den lägger fram ett fakturautkast, efter systeminstruktionerna.",
};

const DELAR: { omfang: Omfang; titel: string }[] = [
  { omfang: "accounting", titel: "Bokföring" },
  { omfang: "invoicing", titel: "Fakturering" },
];

/**
 * Instruktioner (`installningar.instruktioner`): företagets egna regler till
 * agenten, en version per sparning — för bokföringen och för faktureringen,
 * en del i taget. Bokföringens del visar också de senaste rättelserna, som
 * är vad reglerna oftast bör lära av. Ingen egen tråd — vyn chattar i
 * Verifikationers.
 */
export function InstruktionerVy({ titel, variant }: { titel: string; variant: "desktop" | "mobil" }) {
  const [omfang, setOmfang] = useState<Omfang>("accounting");
  const { data, isError } = useQuery({
    queryKey: instruktionNyckel(omfang),
    queryFn: () => instruktionerApi.hamta(omfang),
    staleTime: 60 * 1000,
  });
  const status = instruktionStatus(data, isError);
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
        <div role="tablist" aria-label="Regler för" className="flex gap-1 pt-[14px]">
          {DELAR.map((d) => {
            const vald = d.omfang === omfang;
            return (
              <button
                key={d.omfang}
                type="button"
                role="tab"
                aria-selected={vald}
                onClick={() => setOmfang(d.omfang)}
                className={`min-h-[36px] rounded-lg px-3 text-[14px] transition-colors ${
                  vald
                    ? "bg-bok-linje-svagast font-medium text-bok-text"
                    : "text-bok-text-2 hover:bg-bok-yta-svag hover:text-bok-text"
                }`}
              >
                {d.titel}
              </button>
            );
          })}
        </div>
        <div className="pt-[10px] text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">{OM[omfang]}</div>

        {isError ? (
          <div className="mt-[14px]">
            <VyBanner ton="fel" text="Instruktionerna kunde inte läsas. Ladda om sidan." />
          </div>
        ) : !data ? (
          <div className="pt-5">
            <VyRadSkelett />
          </div>
        ) : (
          <>
            {/* Nyckeln bär omfånget: ett byte av del får inte ta med sig osparad text. */}
            <Redigera key={`${omfang}:${data.foretaget?.version_id ?? "ingen"}`} omfang={omfang} data={data} />
            {omfang === "accounting" && <Korrigeringar />}
            <Versioner data={data} />
            <System text={data.system} />
          </>
        )}
      </div>
    </div>
  );
}

function Redigera({ omfang, data }: { omfang: Omfang; data: Instruktioner }) {
  const queryClient = useQueryClient();
  const start = data.foretaget?.content_markdown ?? "";
  const [text, setText] = useState(start);
  const [sammanfattning, setSammanfattning] = useState("");
  const [fel, setFel] = useState<string | null>(null);
  const andrat = text !== start;

  const spara = useMutation({
    mutationFn: () => instruktionerApi.spara(omfang, text, sammanfattning),
    onMutate: () => setFel(null),
    onSuccess: () => {
      setSammanfattning("");
      void queryClient.invalidateQueries({ queryKey: instruktionNyckel(omfang) });
    },
    onError: (e) => setFel(felText(e, "Instruktionerna kunde inte sparas.")),
  });

  return (
    <form
      className="flex flex-col"
      onSubmit={(e) => {
        e.preventDefault();
        spara.mutate();
      }}
    >
      <Rubrik>Företagets regler</Rubrik>
      <textarea
        aria-label="Företagets regler"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Regler och lärdomar för just det här företaget, i markdown."
        className={`${FALT} min-h-[320px] resize-y leading-[1.5]`}
      />
      <div className="flex flex-col gap-3 pt-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <Falt etikett="Vad ändrades">
            <input value={sammanfattning} onChange={(e) => setSammanfattning(e.target.value)} className={FALT} />
          </Falt>
        </div>
        <Knapp disabled={!andrat || !text.trim() || spara.isPending}>
          {spara.isPending ? "Sparar…" : "Spara som ny version"}
        </Knapp>
      </div>
      {fel && (
        <div className="mt-[14px]">
          <VyBanner ton="fel" text={fel} />
        </div>
      )}
    </form>
  );
}

function Korrigeringar() {
  const { data } = useQuery({
    queryKey: KORRIGERINGAR_NYCKEL,
    queryFn: instruktionerApi.korrigeringar,
    staleTime: 60 * 1000,
  });
  if (!data || data.length === 0) return null;
  return (
    <>
      <Rubrik>Senaste rättelser</Rubrik>
      {data.map((k) => (
        <div key={k.id} className="border-b border-bok-linje-svagast py-[7px]">
          <div className="text-[14px] leading-[1.35] text-bok-text">{korrigeringText(k)}</div>
          <div className="bok-mono pt-[2px] text-[11px] leading-[1.45] text-bok-meta">
            {[k.correction_reason || "ingen anledning angiven", tidpunkt(k.created_at)].join(" · ")}
          </div>
        </div>
      ))}
    </>
  );
}

function Versioner({ data }: { data: Instruktioner }) {
  if (data.versioner.length === 0) return null;
  return (
    <>
      <Rubrik>Versioner</Rubrik>
      {data.versioner.map((v) => (
        <div key={v.version_id} className="border-b border-bok-linje-svagast py-[7px]">
          <div className="text-[14px] leading-[1.35] text-bok-text">
            Version {v.version}
            {v.version_id === data.foretaget?.version_id ? " · gäller" : ""}
          </div>
          <div className="bok-mono pt-[2px] text-[11px] leading-[1.45] text-bok-meta">
            {[v.change_summary || "ingen sammanfattning", v.created_by, tidpunkt(v.created_at)].join(" · ")}
          </div>
        </div>
      ))}
    </>
  );
}

function System({ text }: { text: string }) {
  const [oppen, setOppen] = useState(false);
  if (!text.trim()) return null;
  return (
    <>
      <Rubrik>Systeminstruktioner</Rubrik>
      <button
        type="button"
        aria-expanded={oppen}
        onClick={() => setOppen(!oppen)}
        className="self-start text-[13px] text-bok-lank hover:underline"
      >
        {oppen ? "Dölj" : "Visa"} systeminstruktionerna (skrivskyddade)
      </button>
      {oppen && (
        <pre className="bok-mono mt-2 max-h-[420px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-bok-linje bg-bok-yta-svag p-3 text-[12px] leading-[1.5] text-bok-text-2">
          {text}
        </pre>
      )}
    </>
  );
}
