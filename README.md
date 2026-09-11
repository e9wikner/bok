# Bok — bokföringssystem

Egenbyggt bokföringssystem för svenska aktiebolag: FastAPI-backend med dubbel
bokföring och oföränderligt revisionsspår, Next.js-frontend för granskning, och
ett agent-API så att en LLM-agent kan sköta löpande bokföring medan backend
upprätthåller de formella kraven.

Följer Bokföringslagen (BFL) och BFNAR 2013:2, använder BAS 2026 som kontoplan
och genererar K2-årsredovisning.

**Licens:** MIT — fri att använda, modifiera och hosta för ditt eget företag. Se
[LICENSE](LICENSE).

## Kom igång

```bash
git clone https://github.com/e9wikner/bok.git
cd bok
docker compose up --build
# API:      http://localhost:8000   (dokumentation på /docs)
# Frontend: http://localhost:3000
```

Utan containrar:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py --init-db --seed     # engångsinit med testdata
python main.py

cd frontend-v3 && npm install && npm run dev
```

## API-referens

Backend genererar sin egen referens. Det finns ingen handskriven
endpoint-dokumentation att hålla i synk:

- `http://localhost:8000/docs` — interaktiv Swagger UI
- `http://localhost:8000/openapi.json` — maskinläsbart schema

## Agentintegration

Agenten får två saker: adressen till instansen och `BOKFOERING_API_KEY`. Resten
hämtar den själv.

```bash
curl -fsS "$BOK_API_URL/api/v1/agent-instructions/entrypoint"   # publik, ingen auth
curl -fsS -X POST "$BOK_API_URL/api/v1/agent/test/ping" \
  -H "Authorization: Bearer $BOKFOERING_API_KEY"                # auth-kontroll
```

Entrypointen innehåller startup-instruktioner, auth-check och länkar vidare in i
arbetsflödet. Driftreglerna agenten läser finns i
[`docs/to_agent/`](docs/to_agent/) — de serveras av API:t, så de är en del av
systemets beteende och inte bara dokumentation.

För Claude Code och liknande finns en setup-only skill i
`.agents/skills/bok-connect/SKILL.md` (exponerad som `.claude/skills/bok-connect`).
API-anropen går genom `scripts/bok-curl`, som löser adressen ur `BOK_API_URL` och
sätter bearer-headern utan att nyckeln skrivs ut.

## Drift

Den skarpa instansen kör som två rootless Podman-quadlets på hemservern
`hubbabubba`. Se [`deploy/hubbabubba/README.md`](deploy/hubbabubba/README.md)
för installation, deploy, mappintag över SMB och rollback.

Docker Compose (`docker-compose.yml`) är den andra vägen, avsedd för lokal drift
och utveckling. Fjärrdeploy från en arbetsstation stöds inte — skriv ett eget
skript om du behöver det.

## Utveckling

```bash
pytest tests/ -v
black . && isort . && flake8 && mypy .
cd frontend-v3 && npm run lint
```

Arkitektur, invarianter och konventioner: [AGENTS.md](AGENTS.md).
