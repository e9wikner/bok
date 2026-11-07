# Modellutvärdering

`scripts/model_eval.py` jämför LLM-modeller på underlagspasset. Varje fall är
ett riktigt underlag med känd kontering. För varje modell och fall kopieras en
fryst kopia av böckerna, fallets verifikation tas bort och underlaget sätts
tillbaka till väntande. Sedan bokför samma kod som i drift (`run_session`)
underlaget, och resultatet jämförs med facit. De riktiga böckerna läses bara,
de skrivs aldrig.

Ögonblicksbilderna ligger i `/srv/appdata/bok/model-eval/`, utanför repot. De
innehåller företagets böcker och underlag och får aldrig checkas in.

## Köra igen med nya modeller

1. Lägg till modellen i `_MODELS` i `services/llm/__init__.py`: protokoll
   (`chat` eller `messages`) och pris från <https://opencode.ai/docs/go/>.
   Modeller som bara finns på `/responses` (GPT Luna, Grok, Muse) har ingen
   adapter i Bok. En chat-modell som behöver `reasoning_effort` får en rad i
   `_REASONING_EFFORT`. Lägg också till cachepriset i
   `GATEWAY_CHAT_CACHE_READ_ORE` i skriptet, så att kostnadsuppskattningen
   blir rätt.
2. Kör mot samma ögonblicksbild, så att resultaten går att jämföra:

   ```bash
   venv/bin/python scripts/model_eval.py run --snapshot 2026-10-06 \
       --models opencode-go/ny-modell --jobs 6
   ```

   Färdiga par modell/fall hoppas över, så det går att avbryta och fortsätta.
   `--retry-errors` kör om par som slutade med fel (t.ex. 429),
   `--cases A-32,pay-101274` gör ett billigt röktest.
3. Rapporten skrivs till `<ögonblicksbild>/report.md` och skrivs ut. Den
   går också att ta fram separat med `report --snapshot 2026-10-06`.

## Ny ögonblicksbild

```bash
venv/bin/python scripts/model_eval.py freeze --name 2027-01-15 \
    --manual /srv/appdata/bok/model-eval/manual-cases.json
```

`freeze` väljer postade, okorrigerade verifikationer med kopplat underlag i
öppna perioder, högst två per sorts underlag (`--per-group`). Facit
(`cases.json`) är böckernas egen kontering, oftast agentens. Gå igenom det,
rätta det som är fel och sätt `"verified": true`. Rapporten markerar fall
utan verifierat facit. `report` poängsätter de sparade konteringarna mot
`cases.json` som den ser ut nu, så ett rättat facit kräver ingen ny körning.
`manual-cases.json` innehåller handskrivna fall för underlag som ännu inte är
bokförda, med samma format.

`freeze` hämtar facit ur böckerna på nytt, så det som redan är granskat måste
föras över. Kopiera `expected`, `note` och `"verified": true` från förra
ögonblicksbildens `cases.json` för de fall som har samma `id` och
`source_id`. Spara först det frysta originalet som `cases.frozen.json`.

Resultat från olika ögonblicksbilder går inte att jämföra rakt av: fallen,
instruktionerna och koden kan ha ändrats emellan. `meta.json` visar commit
och instruktionsversion för varje ögonblicksbild.

## Så räknas resultatet

- **correct**: samma nettobelopp per konto och samma datum.
- **≈date / ≈amounts**: rätt rader men annat datum, eller rätt konton men
  andra belopp.
- **wrong**: bokfört på andra konton. Den skadliga sorten.
- Ett kvitto i utländsk valuta bestämmer inget kronbelopp. Ett sådant fall
  kan ange `"amount_tolerance": 0.05` i facit, och beloppet per konto får då
  avvika så mycket.
- **none**: avstod eller föreslog inget. Ofarligt, men lämnar arbete åt en
  människa.
- Kostnad i öre per fall. *bok* är det Boks dagsbudget räknar; chat-adaptern
  rapporterar inga cachade token, så de räknas som vanlig indata. *gw est.*
  är vad gatewayen debiterar, med cachade token till cachepris.

## Läge 2026-10-06 (pausat)

Facit för underlagspasset är beslutat i D1–D6. Besluten och motiveringen står i
`/srv/appdata/bok/model-eval/2026-10-01/facit-forslag.md`, och reglerna står i
bokföringsinstruktionerna v5:

- D1: programvara och molntjänster på 6500.
- D2: tjänster från utanför EU bokförs utan moms.
- D3: kronbeloppet tas från kvittot eller filnamnet, annars avstår agenten.
- D4: telefoni, internet och domäner på 6200.
- D5: lön på 7210/2710/2820 och arbetsgivaravgift på 7510/2730.
- D6: friskvård på 7300, Lysa på 6500/2640 och obetald leverantörsfaktura på 2440.

Konto 7210 skapades för D5.

Ögonblicksbilden `2026-10-06` (instruktioner v5, 26 fall, 20 med verifierat
facit) gav deepseek-v4.1-flash och qwen3.8-flash 24 rätt var. Under v4 fick
bästa modellen 14 rätt. deepseek-v4.1-flash är standardmodell i drift
(`LLM_DEFAULT_MODEL` i `bok.env`) och i `config.py`.

Nästa steg, när arbetet tas upp igen:

1. **D7, medlemsavgifter.** Fall A-31 (Småföretagarnas Riksförbund, 613 kr) har
   inget verifierat facit, och modellerna konterar det olika: 6500, 6900, 1920
   eller 2440. BAS har 6980 Föreningsavgifter, men kontot finns inte i
   kontoplanen. Besluta om kontot och om momsen, skriv in regeln i
   instruktionerna (v6) och rätta facit.
2. **Granska resten av facit.** A-2, A-4, A-14, A-15 och A-16 är inte
   verifierade. Modellerna håller med böckerna i alla dessa fall, så det
   handlar mest om att bekräfta och sätta `"verified": true`.
3. **Avstående som rätt svar.** På A-11 (Anthropic, bara EUR och inget
   kronbelopp i filnamnet) avstår alla modeller, precis som D3 säger. Ändå
   räknas det som `none`. Fall där reglerna kräver att agenten avstår bör kunna
   ange det i facit, så att `_score` räknar avståendet som rätt.
4. **Efter v6:** frys en ny ögonblicksbild, för över facit enligt ovan och kör
   alla modeller igen.

Omräkning till kronor med Riksbankens kurs står i `oppna-beslut.md`.
