## Rapporten

Ladda upp rapporten med `POST /api/v1/review/reports` och
`Content-Type: application/json`. Formatet står i `report_schema`. Ange din
agent och din modell ärligt.

```json
{
  "id": "6f1c2a4e-8d3b-4c1a-9e2f-0b7d5a3c9e11",
  "fiscal_year_id": "<fiscal_year.id>",
  "reviewer": {"agent": "<din agent>", "model": "<din modell>"},
  "instruction_sha256": "<instruction_sha256>",
  "summary_markdown": "Helhetsbedömning. Vad som granskades, hur urvalet gjordes och vad granskningen inte täcker.",
  "examined_voucher_ids": ["<voucher id>"],
  "findings": [
    {
      "severity": "material",
      "area": "moms",
      "title": "Utländsk tjänst bokförd utan omvänd moms",
      "description": "Vad du såg, i vilket underlag, och varför det är fel.",
      "rule": "ML 1 kap. 2 § första st. 2",
      "voucher_ids": ["<voucher id>"],
      "amount_ore": 125000,
      "suggested_correction": "Boka 2645/2614 med 25 % på 5 000 kr."
    }
  ]
}
```

- `id` är ett UUID som du skapar en gång per rapport. Skapa det innan du
  bygger rapporten och spara det i en fil, så att en omkörning av ditt eget
  skript skickar samma `id`. Skickar du samma `id`
  och samma innehåll igen får du den sparade rapporten tillbaka (`200`). Det
  blir ingen dubblett. Samma `id` med annat innehåll ger
  `409 review_report_id_conflict`. En ny rapport får ett nytt `id`.
- `instruction_sha256` är värdet från `GET /api/v1/review/instructions`.
- `severity` är `material`, `should_fix` eller `observation`.
- `area` är `moms`, `periodisering`, `privat`, `underlag`, `avstamning`,
  `bokslut`, `forvaltning` eller `ovrigt`.
- `rule`, `voucher_ids`, `amount_ore` och `suggested_correction` får utelämnas.
  `amount_ore` är ett heltal i öre.
- `findings` får vara en tom lista.

Servern kontrollerar hela rapporten innan något sparas. Ett id i
`voucher_ids` eller `examined_voucher_ids` som inte är en postad verifikation
i året ger `422 invalid_voucher_id`, och `invalid_voucher_ids` listar dem.
Rätta och skicka igen med samma `id`. `201` betyder att rapporten är sparad.

Svaret är den sparade rapporten. Utöver det du skickade har den `uploaded_by`,
`uploaded_at`, `counts` (antal anmärkningar per `severity`),
`instruction_outdated` (`true` om instruktionen har ändrats sedan du läste den)
och, för varje anmärkning, `vouchers` med verifikationernas nummer och datum.
Läs `counts` och kontrollera att alla anmärkningar kom med.
