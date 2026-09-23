import { aldersTon } from "@/lib/chattyta/alder";
import type { BeslutSvar } from "@/lib/chattyta/api";
import type { DecisionInlagg } from "@/lib/chattyta/typer";
import { formatBelopp } from "@/lib/skal/format";

/**
 * `BeslutKort` och `GodkannKort` (komponenter.md §Kort i tråden,
 * SPEC-chattyta.md §5, §7): ett `decision`-inlägg, och vad servern i dag
 * säger om beslutet.
 *
 * Två källor, med var sin roll:
 * - **Inlägget** (`inlagg.body`) är vad agenten sa. Rubrik, belopp, `reason`
 *   och `consequence` ritas ordagrant därifrån och ändras aldrig
 *   (antagande 2, 3) — inte heller när beslutet besvarats.
 * - **Beslutet** (`beslut`, ur `useBeslut`) bär det inlägget inte kan veta:
 *   `status`, `kind` och `age_days`. Det styr bara rubrikraden och tonen.
 *
 * `beslut` saknas när frågan inte svarat, misslyckats, eller när id:t inte
 * finns i vyns lista (taket 200, `useBeslut`). Då ritas öppet läge — ett
 * beslutsinlägg är öppet tills servern sagt annat, och ett öppet kort utan
 * knappar kan inte göra någon skada — men rubriken säger bara
 * `Behöver ditt beslut`: sorten (avstod/godkännande) står inte i inlägget,
 * och kortet påstår inte något servern inte sagt.
 *
 * Inga knappar i något läge. Kroppen säger inte vad en primär- eller
 * sekundärknapp skulle göra (tasks/chattyta/todo.md C6, obs); alternativen
 * är ett eget `options`-inlägg (C7), och fritexten i `ChattFalt` är alltid
 * en väg (§7, README.md: primärknappen är aldrig den enda vägen).
 */

type Lage = "oppen" | "besvarad" | "ersatt";

function lageAv(beslut: BeslutSvar | undefined): Lage {
  switch (beslut?.status) {
    case "answered":
      return "besvarad";
    case "superseded":
      return "ersatt";
    default:
      return "oppen";
  }
}

/**
 * Rubrikradens text. `Besvarat` utan klockslag och utan svaret: SPEC §5 vill
 * `Besvarat · HH:MM` + svaret, men `DecisionResponse` (api/schemas.py) bär
 * varken `answered_at`, `answer_option_id` eller `answer_text` — de finns
 * bara i `409`-kroppen. Människans svar står redan i tråden som hennes
 * eget `user_text`-inlägg; ett klockslag klienten hittat på vore ett
 * påstående om bokföringen som servern inte gjort.
 */
function rubrik(lage: Lage, beslut: BeslutSvar | undefined): string {
  if (lage === "besvarad") return "Besvarat";
  if (lage === "ersatt") return "Inte längre aktuellt";
  if (!beslut) return "Behöver ditt beslut";
  return beslut.kind === "approval"
    ? "Väntar på ditt godkännande"
    : "Agenten avstod · behöver ditt beslut";
}

/**
 * Källradens färg. Bara ett öppet beslut väntar, och bara ett som väntar kan
 * bli för gammalt (§10: regeln gäller det som väntar på människan). Utan
 * `age_days` väntar-tonen — aldrig gissat röd, som `VyRad` utan `ageDays`.
 */
function kallFarg(lage: Lage, beslut: BeslutSvar | undefined): string {
  if (lage !== "oppen") return "var(--bok-text-svag)";
  if (!beslut) return "var(--bok-vantar-meta)";
  return aldersTon(beslut.age_days) === "forfallen"
    ? "var(--bok-fel-meta)"
    : "var(--bok-vantar-meta)";
}

/**
 * `källa · id`, plus datumet ur listan när det finns — inlägget bär bara
 * `{kind, id}` (`_decision_body`), komponenter.md vill "källa och datum".
 * Serverns strängar, ingen översättning: `kind` är öppen (`BeslutKallaSvar`).
 */
function kallText(inlagg: DecisionInlagg, beslut: BeslutSvar | undefined): string | null {
  const kalla = inlagg.body.source;
  if (!kalla) return null;
  const datum = beslut?.source?.date;
  return [kalla.kind, kalla.id, datum].filter(Boolean).join(" · ");
}

export function BeslutKort({
  inlagg,
  beslut,
}: {
  inlagg: DecisionInlagg;
  /** Beslutet ur `GET /decisions`; `undefined` = okänt (se ovan). */
  beslut?: BeslutSvar;
}) {
  const { title, amount, reason, consequence } = inlagg.body;
  const lage = lageAv(beslut);
  const kalla = kallText(inlagg, beslut);

  // Gult bär betydelse: något väntar på människan (globals.css). Ett
  // besvarat eller ersatt beslut väntar inte, så det får neutral yta.
  const yta =
    lage === "oppen"
      ? "border-bok-vantar-kant bg-bok-vantar-yta"
      : lage === "besvarad"
        ? "border-bok-kant bg-bok-yta"
        : "border-bok-linje bg-bok-yta-svag";
  const rubrikFarg =
    lage === "oppen"
      ? "text-bok-vantar-text"
      : lage === "besvarad"
        ? "text-bok-klart-text"
        : "text-bok-text-svag";

  return (
    <div
      data-inlagg-id={inlagg.id}
      data-beslut-lage={lage}
      data-beslut-kant={beslut ? "ja" : "nej"}
      // Alla kort: max-bredd 560, radius 12, padding 20/22, kolumn gap 14–16.
      className={`flex w-full max-w-[560px] flex-col gap-[14px] rounded-[12px] border px-[22px] py-[20px] ${yta}`}
    >
      {/* Rubrikrad: text 14/500 + mono 12 med källa och datum. */}
      <div className="flex items-baseline justify-between gap-[14px]">
        <span data-testid="beslut-rubrik" className={`text-[14px] font-medium ${rubrikFarg}`}>
          {rubrik(lage, beslut)}
        </span>
        {kalla && (
          <span
            data-testid="beslut-kalla"
            className="bok-mono whitespace-nowrap text-[12px]"
            style={{ color: kallFarg(lage, beslut) }}
          >
            {kalla}
          </span>
        )}
      </div>

      {/* Kropp: rubrik 15 och belopp mono 15 tabulärt på samma baslinje. */}
      <div className="flex flex-col gap-[6px]">
        <div className="flex items-baseline justify-between gap-[14px]">
          <span className="min-w-0 text-[15px] text-bok-text">{title}</span>
          {amount !== null && (
            <span
              data-testid="beslut-belopp"
              className="bok-mono bok-tal whitespace-nowrap text-[15px] text-bok-text"
            >
              {formatBelopp(amount)}
            </span>
          )}
        </div>
        {/* Förklaring 14/1.55 #78716c (ingen token; samma som förslagets fot). */}
        <p className="m-0 text-[14px] leading-[1.55] text-[#78716c]">{reason}</p>
      </div>

      {/*
       * Konsekvensen bär varningen och är inte metatext (§11, komponenter.md
       * om `VerifikationsForslag`): mono 12 #52525b, samma som förslagets
       * notis, aldrig `text-bok-meta`.
       */}
      <p className="bok-mono m-0 text-[12px] text-bok-text-dampad">{consequence}</p>
    </div>
  );
}
