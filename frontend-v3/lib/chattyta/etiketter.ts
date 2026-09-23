/**
 * Verktygsnamn → svensk etikett (SPEC-chattyta.md §5, testfall 11).
 *
 * Servern skickar två saker om samma verktygsanrop: ett spår i inläggets
 * `traces[]`, där `label` redan är översatt av `build_trace`, och ett
 * `message.delta {activity}` medan agenten arbetar, där bara verktygets
 * NAMN följer med (`services/thread_stream.py::_on_tool_call`). Indikatorn
 * måste alltså översätta själv — och med SAMMA ord som chippet som följer,
 * annars heter ett verktyg en sak medan det körs och en annan när det är
 * klart.
 *
 * Tabellen är en kopia av `services/thread_service.py::_TRACE_LABELS` och
 * ska hållas lika. Testet i `components/chattyta/__tests__/text.test.tsx`
 * listar den ordagrant; ändras serverns ändras båda i samma commit. Den står
 * här, på ett ställe, i stället för i `SkriverIndikator`, så att den som
 * letar efter "var översätts verktygsnamn i klienten" hittar ett svar.
 */

export const SPAR_ETIKETTER: Readonly<Record<string, string>> = {
  las_kontoplan: "kontoplanen läst",
  las_perioder: "perioderna lästa",
  las_verifikationer: "verifikationer lästa",
  las_korrigeringar: "korrigeringshistoriken läst",
  las_underlag: "underlag lästa",
  hamta_underlagsfil: "underlagsfilen hämtad",
  las_bankhandelser: "bankhändelser lästa",
  posta_verifikation: "verifikation postad",
  registrera_avstaende: "avstående registrerat",
};

/**
 * Samma verktyg, i presens — vad `SkriverIndikator` säger MEDAN det körs.
 *
 * `activity` sänds när verktyget anropas, inte när det är klart
 * (`_on_tool_call`). Chippets perfekt (`verifikation postad`) vore därför
 * ett påstående om huvudboken som inte har hänt än. komponenter.md ger
 * formen: *"Postar verifikation A-118…"*. Samma nycklar som
 * `SPAR_ETIKETTER`; testet kräver att båda tabellerna täcker samma verktyg.
 */
export const SKRIVER_ETIKETTER: Readonly<Record<string, string>> = {
  las_kontoplan: "Läser kontoplanen…",
  las_perioder: "Läser perioderna…",
  las_verifikationer: "Läser verifikationer…",
  las_korrigeringar: "Läser korrigeringshistoriken…",
  las_underlag: "Läser underlag…",
  hamta_underlagsfil: "Hämtar underlagsfilen…",
  las_bankhandelser: "Läser bankhändelser…",
  posta_verifikation: "Postar verifikation…",
  registrera_avstaende: "Registrerar avstående…",
};

/**
 * Vad `SkriverIndikator` säger innan agenten anropat något verktyg.
 * komponenter.md: *"Aldrig en anonym spinner."*
 */
export const SKRIVER_FORVAL = "Läser…";

/**
 * Indikatorns text ur senaste `activity`. Aldrig tom (SPEC §5).
 *
 * Ett okänt verktyg visas med sitt namn — samma fallback som
 * `_TRACE_LABELS.get(name, name)` på servern. Ett tekniskt namn är sämre än
 * en etikett men bättre än att låtsas veta vad agenten gör.
 */
export function skriverText(activity?: string | null): string {
  const namn = activity?.trim();
  if (!namn) return SKRIVER_FORVAL;
  return SKRIVER_ETIKETTER[namn] ?? `${namn}…`;
}
