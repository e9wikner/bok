## Ordning

1. Hämta SIE4-filen för en överblick över kontoplan, saldon och
   verifikationer.
2. Bilda dig en egen uppfattning om varje verifikation du prövar. Utgå från
   raderna och underlaget (`source-context` och filen).
3. Läs rättelsehistorik och kommentarer (`audit`, `correction-notes`,
   `accounting-corrections`) först när du har en egen uppfattning. Då
   påverkar de inte din bedömning.

## Företagets instruktioner

Bolagets bokföringsinstruktioner (`company_instructions`) är påståenden att
pröva, inte regler. De säger hur bolaget vill bokföra. Om en instruktion
strider mot lag eller god redovisningssed är det en anmärkning mot
instruktionen. Verifikationerna som följer den är då också fel.

## Urval

Pröva

- alla stora poster,
- posterna inom riskområdena nedan,
- ett slumpvis urval av resten.

Skriv i `summary_markdown` hur du valde: gränsen för en stor post, vilka
riskområden du gick igenom och hur stort det slumpvisa urvalet var. Lista
varje verifikation du faktiskt prövade i `examined_voucher_ids`.

## Riskområden

Ett litet aktiebolag har de här riskerna:

- **Moms.** Avdragsrätt, omvänd skattskyldighet för köp inom och utanför EU,
  representation och rätt momssats. Stäm av 26xx mot momsdeklarationerna.
- **Privat.** Privata kostnader i bolaget, förmåner och lån till ägaren
  (ABL 21 kap.).
- **Periodisering.** Kostnader och intäkter kring årsskiftet (17xx och 29xx).
- **Underlag.** Underlaget ska stödja verifikationen: belopp, motpart och
  datum. Samma kvitto får inte ligga bakom två kostnader.
- **Avstämningar.** Bank 1930 och skattekontot 1630 ska stämma mot de
  importerade kontoutdragen. Den ingående balansen ska stämma mot fjolårets
  utgående.
- **Bokslut.** Avskrivningar enligt K2, skatteberäkningen och utdelning mot
  fritt eget kapital (ABL 17 kap. 3 §).

## Bevis

Varje anmärkning ska bygga på något du har läst. Ange verifikationerna i
`voucher_ids` när det går. Servern vägrar ett id som inte är en postad
verifikation i året.

Räkna inte fram summor i huvudet. Hämta dem från rapportrutterna
(balansräkning, resultaträkning, huvudbok) och skriv var de kommer ifrån.

## Allvarlighet

- `material`: påverkar årsredovisningen, deklarationen eller
  lagefterlevnaden.
- `should_fix`: ett fel som bör rättas.
- `observation`: en iakttagelse.

"Inga anmärkningar" är ett giltigt utfall. Hitta inte på fynd för att
rapporten ska se grundlig ut.

## Begränsningar

Skriv i sammanfattningen vad granskningen inte täcker:

- inga lager har inventerats,
- inga fysiska tillgångar har setts,
- inga externa bekräftelser har hämtats,
- avsiktligt fusk med förfalskat underlag kan missas.
