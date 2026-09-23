import { FilInlagg } from "@/components/chattyta/FilInlagg";
import { JamforelseRader, RadLista } from "@/components/chattyta/JamforelseRader";
import { SkriverIndikator } from "@/components/chattyta/SkriverIndikator";
import { TradInlagg } from "@/components/chattyta/TradInlagg";
import { VerifikationsForslag } from "@/components/chattyta/VerifikationsForslag";
import type { Strommande } from "@/lib/chattyta/trad";
import type { AgentTextInlagg, Inlagg } from "@/lib/chattyta/typer";

/**
 * Trådens renderare (SPEC-chattyta.md §5): ett inlägg in, en komponent ut.
 *
 * En `switch` på `type`, en rad per typ, och ingenting annat. Allt som avgör
 * OM ett inlägg kan visas är redan avgjort i `parseInlagg` (§4.1) — hit kommer
 * bara typade inlägg och `okant_kontrakt`. Därför läser ingen gren `body` på
 * sitt eget sätt, och här finns inga `?? ""`.
 *
 * Typer utan renderare än (`decision`, `options`, `error`) blir samma rad som
 * ett kontraktsbrott: ärligt, inte tomt (plan.md, C4 → C5). C6, C7 och C13
 * byter bara ut sin gren.
 *
 * Ordningen är serverns (`listaInlagg`); renderaren flyttar och slår inte
 * ihop något (§5).
 */
export function TradRenderare({
  inlagg,
  strommande,
}: {
  inlagg: Inlagg[];
  strommande: Strommande | null;
}) {
  return (
    <>
      {inlagg.map((i) => (
        <InlaggRenderare key={i.id} inlagg={i} />
      ))}
      {strommande && <StrommandeInlagg strommande={strommande} />}
    </>
  );
}

export function InlaggRenderare({ inlagg }: { inlagg: Inlagg }) {
  switch (inlagg.type) {
    case "agent_text":
      return (
        <TradInlagg
          inlagg={inlagg}
          // `RadLista/i-tråd` bara när kroppen bär rader (§5). En tom lista
          // ritar RadLista själv som ingenting.
          radLista={inlagg.body.rows ? <RadLista rader={inlagg.body.rows} /> : undefined}
        />
      );
    case "user_text":
      return <TradInlagg inlagg={inlagg} />;
    case "user_file":
      return <FilInlagg inlagg={inlagg} />;
    case "receipt":
      return <JamforelseRader kropp={inlagg.body} />;
    case "draft":
      // Utan knappar: `Posta` kopplas först i C12, efter idempotensnyckeln
      // (C11, ANALYS.md §7). En knapp före nyckeln vore en väg till två
      // verifikationer i en append-only-bok.
      return <VerifikationsForslag inlagg={inlagg} />;
    // Byggs i C6 (`decision`), C7 (`options`) och C13 (`error`).
    case "decision":
    case "options":
    case "error":
      return <OkantKontrakt typ={inlagg.type} id={inlagg.id} />;
    case "okant_kontrakt":
      return <OkantKontrakt typ={inlagg.ursprungligTyp} id={inlagg.id} />;
  }
}

/**
 * `okant_kontrakt` (§4.4): en neutral rad i mono 12. Den säger att något
 * finns utan att låtsas veta vad — och pekar ut vilket inlägg, så att den som
 * felsöker hittar det. Ingen knapp: det finns inget ärligt att erbjuda.
 */
export function OkantKontrakt({ typ, id }: { typ: string; id: string }) {
  return (
    <p data-testid="okant-kontrakt" className="bok-mono m-0 text-[12px] text-bok-text-svag">
      {`kortet kunde inte visas · ${typ} · ${id}`}
    </p>
  );
}

/**
 * Agentens svar medan det skrivs (§6.3). Texten som hittills kommit ritas som
 * ett vanligt agentinlägg, och indikatorn under säger vad agenten gör just nu
 * — aldrig en anonym väntan (§2, punkt 2). `message.completed` ersätter
 * alltihop med det lagrade inlägget; det här är bara leveransen.
 */
function StrommandeInlagg({ strommande }: { strommande: Strommande }) {
  const text: AgentTextInlagg | null = strommande.text
    ? {
        id: strommande.id,
        seq: -1,
        type: "agent_text",
        actor: "agent",
        // Ingen tid än: servern stämplar inlägget när det lagras. En tom
        // sträng ger metaraden `agenten` utan klockslag (`klockslag`).
        created_at: "",
        traces: null,
        run_id: strommande.run_id,
        body: { text: strommande.text },
      }
    : null;
  return (
    <>
      {text && <TradInlagg inlagg={text} />}
      <SkriverIndikator activity={strommande.activity} />
    </>
  );
}
