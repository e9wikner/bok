/**
 * Verktygsnamn → svensk presensetikett för `SkriverIndikator`
 * (SPEC-chattyta.md §5, SPEC-lasbarhet §4.3).
 *
 * Medan agenten arbetar skickar servern `message.delta {activity}` med bara
 * verktygets NAMN (`services/thread_stream.py::_on_tool_call`). Indikatorn
 * översätter själv. Klienten ritar inga spår (`traces[]`), så det här är
 * enda stället ett verktygsnamn blir ord i klienten.
 *
 * `activity` sänds när verktyget anropas, inte när det är klart. Etiketten
 * står därför i presens — perfekt (`verifikation postad`) vore ett
 * påstående om huvudboken som inte har hänt än. komponenter.md ger formen:
 * *"Postar verifikation A-118…"*.
 *
 * Varje verktyg i `services/agent_tools.py::_TOOL_SPECS` ska ha en etikett.
 * Testet i `components/chattyta/__tests__/text.test.tsx` listar verktygen;
 * `tests/test_tradar.py` kontrollerar att listan är serverns.
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
  be_om_beslut: "Lägger fram ett beslut…",
  foresla_verifikation: "Föreslår en verifikation…",
  tolka_underlag: "Tolkar underlaget…",
  koppla_underlag: "Kopplar underlaget…",
  stang_perioder: "Låser perioder…",
  koppla_bort_underlag: "Kopplar bort underlaget…",
  las_okopplade_banktransaktioner: "Läser okopplade banktransaktioner…",
  koppla_banktransaktion: "Kopplar kontoutdraget…",
  koppla_bort_banktransaktion: "Kopplar bort kontoutdraget…",
  las_loner: "Läser lönerna…",
  registrera_anstalld: "Registrerar den anställda…",
  satt_lon: "Sätter lönen…",
  skapa_lonekorning: "Skapar lönekörningen…",
  foresla_rakenskapsar: "Föreslår ett räkenskapsår…",
  foresla_bolagsinformation: "Föreslår bolagsuppgifter…",
  las_kunder: "Läser kunderna…",
  las_fakturor: "Läser fakturorna…",
  foresla_faktura: "Föreslår en faktura…",
  andra_fakturautkast: "Ändrar fakturaförslaget…",
  sok_verifikationer: "Söker verifikationer…",
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
