"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { FALT, Falt, Knapp, Rubrik } from "@/components/skal/Formular";
import { VyBanner } from "@/components/skal/VyBanner";
import { VyHeaderStatus } from "@/components/skal/VyHeaderStatus";
import { VyRadSkelett } from "@/components/skal/VyRad";
import { felText } from "@/lib/skal/anstallda";
import {
  FALTEN,
  FORETAGET_NYCKEL,
  type Formular,
  foretagetApi,
  foretagetStatus,
  formularFel,
  formularFran,
  saknasForFaktura,
} from "@/lib/skal/foretaget";
import { lageFarg } from "@/lib/skal/lage";

/**
 * Företaget (`installningar.foretaget`): företagets uppgifter och det som står på
 * fakturan. Ingen egen tråd — den chattar i Fakturerings, där uppgifterna
 * behövs.
 */
export function ForetagetVy({ titel, variant }: { titel: string; variant: "desktop" | "mobil" }) {
  const { data, isError } = useQuery({
    queryKey: FORETAGET_NYCKEL,
    queryFn: foretagetApi.hamta,
    staleTime: 60 * 1000,
  });
  const status = foretagetStatus(data, isError);
  const pad = variant === "desktop" ? "px-6" : "px-[18px]";
  // Här och inte i formuläret: ett sparat svar byter nyckel på formuläret.
  const [sparat, setSparat] = useState(false);

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
            <VyBanner ton="fel" text="Företagets uppgifter kunde inte läsas. Ladda om sidan." />
          </div>
        ) : !data ? (
          <div className="pt-5">
            <VyRadSkelett />
          </div>
        ) : (
          <Uppgifter
            key={JSON.stringify(data)}
            start={formularFran(data)}
            saknas={saknasForFaktura(data)}
            sparat={sparat}
            setSparat={setSparat}
          />
        )}

        <div className="pt-5 text-[13px] leading-[1.55] text-bok-text-svag [text-wrap:pretty]">
          Uppgifterna står på fakturorna och i årsredovisningen. En faktura som redan är utfärdad ändras inte. Du kan
          också be agenten fylla i dem.
        </div>
      </div>
    </div>
  );
}

function Uppgifter({
  start,
  saknas,
  sparat,
  setSparat,
}: {
  start: Formular;
  saknas: string[];
  sparat: boolean;
  setSparat: (v: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [f, setF] = useState<Formular>(start);
  const [fel, setFel] = useState<string | null>(null);
  const andrat = JSON.stringify(f) !== JSON.stringify(start);

  useEffect(() => {
    if (andrat) setSparat(false);
  }, [andrat, setSparat]);

  const spara = useMutation({
    mutationFn: foretagetApi.spara,
    onMutate: () => setFel(null),
    onSuccess: (svar) => {
      queryClient.setQueryData(FORETAGET_NYCKEL, svar);
      setSparat(true);
    },
    onError: (e) => setFel(felText(e, "Uppgifterna kunde inte sparas.")),
  });

  const falt = (grupp: "foretaget" | "fakturan") =>
    FALTEN.filter((x) => x.grupp === grupp).map((x) => (
      <Falt key={x.key} etikett={x.etikett} hjalp={x.hjalp}>
        <input
          value={f[x.key]}
          onChange={(e) => setF({ ...f, [x.key]: e.target.value })}
          className={FALT}
          autoComplete="off"
        />
      </Falt>
    ));

  return (
    <form
      className="flex flex-col"
      onSubmit={(e) => {
        e.preventDefault();
        const stopp = formularFel(f);
        if (stopp) {
          setFel(stopp);
          return;
        }
        spara.mutate(f);
      }}
    >
      {saknas.length > 0 && (
        <div className="mt-[14px]">
          <VyBanner ton="varning" text={`För att utfärda en faktura saknas: ${saknas.join(", ")}.`} />
        </div>
      )}

      <Rubrik>Företaget</Rubrik>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">{falt("foretaget")}</div>

      <Rubrik>På fakturan</Rubrik>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">{falt("fakturan")}</div>
      <label className="flex items-center gap-2 pt-3 text-[14px] text-bok-text">
        <input type="checkbox" checked={f.f_skatt} onChange={(e) => setF({ ...f, f_skatt: e.target.checked })} />
        Godkänd för F-skatt
      </label>

      {fel && (
        <div className="mt-[14px]">
          <VyBanner ton="fel" text={fel} />
        </div>
      )}
      <div className="flex items-center gap-3 pt-4">
        <Knapp disabled={!andrat || spara.isPending}>{spara.isPending ? "Sparar…" : "Spara"}</Knapp>
        {andrat && (
          <Knapp type="button" sekundar onClick={() => setF(start)}>
            Ångra
          </Knapp>
        )}
        {sparat && !andrat && <span className="bok-mono text-[12px] text-bok-klart-meta">sparat</span>}
      </div>
    </form>
  );
}
