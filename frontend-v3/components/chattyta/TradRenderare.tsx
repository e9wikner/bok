import { createContext, useContext, useState } from "react";
import { AlternativLista } from "@/components/chattyta/AlternativLista";
import { BeslutKort } from "@/components/chattyta/BeslutKort";
import { FelKort } from "@/components/chattyta/FelKort";
import { FilInlagg } from "@/components/chattyta/FilInlagg";
import { JamforelseRader, RadLista } from "@/components/chattyta/JamforelseRader";
import { SkriverIndikator } from "@/components/chattyta/SkriverIndikator";
import { TradInlagg } from "@/components/chattyta/TradInlagg";
import { PostaKnappar, VerifikationsForslag } from "@/components/chattyta/VerifikationsForslag";
import { useBeslut } from "@/hooks/useBeslut";
import { skriverText } from "@/lib/chattyta/etiketter";
import { arOptimistisk } from "@/lib/chattyta/trad";
import type { Strommande } from "@/lib/chattyta/trad";
import type {
  AgentTextInlagg,
  DecisionInlagg,
  DraftInlagg,
  Inlagg,
  OptionsInlagg,
} from "@/lib/chattyta/typer";

/**
 * Trådens renderare (SPEC-chattyta.md §5): ett inlägg in, en komponent ut.
 *
 * En `switch` på `type`, en rad per typ, och ingenting annat. Allt som avgör
 * OM ett inlägg kan visas är redan avgjort i `parseInlagg` (§4.1) — hit kommer
 * bara typade inlägg och `okant_kontrakt`. Därför läser ingen gren `body` på
 * sitt eget sätt, och här finns inga `?? ""`.
 *
 * Alla åtta typer har en renderare sedan C13; `OkantKontrakt` ritas bara för
 * verkliga kontraktsbrott (§4.4), aldrig för en känd typ.
 *
 * `viewKey` behövs bara av beslutskorten och alternativlistan: statusen läses
 * per vy (§7), och inlägget bär ingen `view_key`. Utan den står de i öppet
 * läge.
 *
 * Ordningen är serverns (`listaInlagg`); renderaren flyttar och slår inte
 * ihop något (§5).
 */

/**
 * Lägger fokus i SAMMA kolumns `ChattFalt` — förslagskortets `Ändra`
 * (SPEC-chattyta.md §8 steg 4). Ges av `ChattKolumn`/`ChattList`, som äger
 * både tråden och fältet. Ett kontext och inte ett `id`-uppslag: svepraden
 * ritar en sidas alla vyer, var och en med ett fält med samma `id`, och
 * `getElementById` skulle hitta den första, inte kortets. `null` = inget
 * fält i närheten; då ritas ingen `Ändra`.
 */
export const ChattFaltFokus = createContext<(() => void) | null>(null);

export function TradRenderare({
  inlagg,
  strommande,
  viewKey,
}: {
  inlagg: Inlagg[];
  strommande: Strommande | null;
  viewKey?: string;
}) {
  return (
    <>
      {inlagg.map((i) => (
        <InlaggRenderare key={i.id} inlagg={i} viewKey={viewKey} />
      ))}
      {strommande && <StrommandeInlagg strommande={strommande} />}
      <TradAnnons inlagg={inlagg} strommande={strommande} />
    </>
  );
}

/**
 * Den dolda live-regionen (SPEC-chattyta.md §11, testfall 31).
 *
 * Trådytan är INTE en live-region: då läste skärmläsaren varje
 * `message.delta {text}` som ett nytt ord. Här sägs två saker, och bara de:
 *
 * - medan agenten arbetar: indikatorns text (`Läser…`, `Postar
 *   verifikation…`). Text-deltan ändrar den inte, så den annonseras en gång
 *   per byte av `activity`;
 * - när turen är klar: de inlägg som kom under turen, hela.
 *
 * "Under turen" = inlägg som inte fanns när platshållaren dök upp. En tråd
 * som laddas, en återuppspelning utan pågående tur och människans eget
 * inlägg annonseras inte — hon har inte väntat på dem. Minnet av vad som
 * fanns vid turens start bor i state, uppdaterat under renderingen (Reacts
 * mönster för att härleda ur föregående props), inte i en effekt.
 */
function TradAnnons({ inlagg, strommande }: { inlagg: Inlagg[]; strommande: Strommande | null }) {
  const [minne, setMinne] = useState<{
    arbetar: boolean;
    vidStart: ReadonlySet<string>;
    fardigt: string;
  }>({ arbetar: false, vidStart: new Set(), fardigt: "" });

  const arbetar = strommande !== null;
  if (arbetar && !minne.arbetar) {
    setMinne({ arbetar, vidStart: new Set(inlagg.map((i) => i.id)), fardigt: "" });
  } else if (!arbetar && minne.arbetar) {
    const nya = inlagg.filter((i) => !minne.vidStart.has(i.id) && !arOptimistisk(i));
    setMinne({ arbetar, vidStart: new Set(), fardigt: nya.map(annonsText).filter(Boolean).join(" ") });
  }

  return (
    <div data-testid="trad-annons" className="sr-only" aria-live="polite" aria-atomic="true">
      {strommande ? skriverText(strommande.activity) : minne.fardigt}
    </div>
  );
}

/**
 * Vad regionen säger om ett färdigt inlägg: kortets bärande text, ordagrant
 * ur kroppen. Människans egna inlägg sägs inte — hon skrev dem nyss.
 */
function annonsText(i: Inlagg): string {
  switch (i.type) {
    case "agent_text":
      return `Agenten: ${i.body.text}`;
    case "decision":
      return `Beslut: ${i.body.title}`;
    case "options":
      return `Alternativ: ${i.body.options.map((o) => o.title).join(", ")}`;
    case "draft":
      return `Förslag: ${i.body.title}`;
    case "error":
      return `Något gick fel: ${i.body.cause}`;
    case "receipt":
      return i.body.title;
    case "okant_kontrakt":
      return "Ett kort kunde inte visas.";
    case "user_text":
    case "user_file":
      return "";
  }
}

export function InlaggRenderare({ inlagg, viewKey }: { inlagg: Inlagg; viewKey?: string }) {
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
      return <ForslagInlagg inlagg={inlagg} />;
    case "decision":
      return <BeslutInlagg inlagg={inlagg} viewKey={viewKey} />;
    case "options":
      return <AlternativInlagg inlagg={inlagg} viewKey={viewKey} />;
    case "error":
      // `Försök igen` bara med `retry_draft_id` (§9); kortet avgör det självt.
      return <FelKort inlagg={inlagg} />;
    case "okant_kontrakt":
      return <OkantKontrakt typ={inlagg.ursprungligTyp} id={inlagg.id} />;
  }
}

/**
 * Beslutskortet med sin status (§7). Varje kort anropar `useBeslut`, men
 * nyckeln är vyns, så TanStack Query ger ETT `GET /decisions` per vy
 * (testfall 20). Hooken bor i en egen komponent i stället för i
 * `TradRenderare` så att bara en tråd som faktiskt har ett beslutsinlägg
 * frågar — och så att ytor som ritar tråden utan beslut inte behöver en
 * `QueryClientProvider`.
 */
function BeslutInlagg({ inlagg, viewKey }: { inlagg: DecisionInlagg; viewKey?: string }) {
  const uppslag = useBeslut(viewKey);
  return <BeslutKort inlagg={inlagg} beslut={uppslag?.get(inlagg.body.decision_id)} />;
}

/**
 * Alternativlistan med beslutets status (§7), av samma skäl och med samma
 * fråga som `BeslutInlagg`: listan och kortet för samma beslut delar ETT
 * `GET /decisions` per vy. Statusen låser listan när beslutet redan är
 * besvarat eller ersatt — vid en omladdning, eller när svaret gavs med text.
 */
function AlternativInlagg({ inlagg, viewKey }: { inlagg: OptionsInlagg; viewKey?: string }) {
  const uppslag = useBeslut(viewKey);
  return <AlternativLista inlagg={inlagg} beslut={uppslag?.get(inlagg.body.decision_id)} />;
}

/**
 * Förslaget med `Posta` och `Ändra` (§8, C12). Knapparna bor i en egen
 * komponent av samma skäl som `BeslutInlagg`: bara en tråd med ett utkast
 * behöver `QueryClientProvider` (postningen invaliderar frågor). Kortet får
 * `draft_id` och inget annat att posta med — nyckeln görs i `postaUtkast`
 * (antagande 4, C11).
 */
function ForslagInlagg({ inlagg }: { inlagg: DraftInlagg }) {
  const fokuseraFalt = useContext(ChattFaltFokus);
  return (
    <VerifikationsForslag
      inlagg={inlagg}
      knappar={<PostaKnappar draftId={inlagg.body.draft_id} onAndra={fokuseraFalt ?? undefined} />}
    />
  );
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
