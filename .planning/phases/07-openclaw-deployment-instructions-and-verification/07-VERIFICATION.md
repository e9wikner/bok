# Phase 7 Verification: OpenClaw Deployment Instructions and Verification

**Verified:** 2026-06-05T12:00:00Z
**Status:** Passed

## Scope Verified

- `DEPLOYMENT.md` includes a post-deploy OpenClaw/HTTP-agent setup section (`### 10. Koppla OpenClaw eller annan HTTP-agent`) after first login and before the LAN update section.
- Human frontend URL (`http://SERVER_IP_OR_HOSTNAME:3000/login`) is clearly separated from agent backend API URL (`http://SERVER_IP_OR_HOSTNAME:8000`).
- Docker-internal URL (`BACKEND_URL=http://api:8000`) is explicitly warned against for external agents.
- Public HTTPS note distinguishes `https://${APP_DOMAIN}` for humans and `https://${API_DOMAIN}` for agents.
- Curl verification commands cover backend health (`/health`), public entrypoint (`/api/v1/agent-instructions/entrypoint`), and authenticated agent ping (`POST /api/v1/agent/test/ping` with `Authorization: Bearer ${API_KEY}`).
- Setup docs use shell variables (`BOK_API_URL`, `API_KEY`) and contain no expected response snippets.
- First OpenClaw instruction is setup-only: delegates to the entrypoint, verifies access, reports readiness, asks the owner before bookkeeping, and explicitly does not process pending intake.
- Troubleshooting covers 401 auth failures, wrong frontend port/base URL, and Docker-internal URL confusion.
- Documentation examples are deterministically checked against actual route paths and auth behavior via `tests/test_deployment_docs.py`.
- Unsupported features (MCP, persistent key lifecycle, generated tool schemas, durable idempotency, model providers) are not presented as supported setup requirements.

## Verification Commands

```bash
.venv/bin/python -m pytest tests/test_deployment_docs.py -q
```

Result: passed, 25 tests.

```bash
.venv/bin/python -m pytest tests/test_deployment_docs.py tests/test_agent_entrypoint.py -q
```

Result: passed, 34 tests.

```bash
rg "### 10\. Koppla" DEPLOYMENT.md
```

Result: found.

```bash
rg "BOK_API_URL=|API_KEY=|Authorization: Bearer|/api/v1/agent-instructions/entrypoint|/api/v1/agent/test/ping" DEPLOYMENT.md
```

Result: found.

```bash
rg "http://SERVER_IP_OR_HOSTNAME:3000/login|http://SERVER_IP_OR_HOSTNAME:8000|BACKEND_URL=http://api:8000" DEPLOYMENT.md
```

Result: found.

```bash
rg "https://\\\$\{API_DOMAIN\}|https://\\\$\{APP_DOMAIN\}" DEPLOYMENT.md
```

Result: found.

```bash
rg "MCP|persistent.*key|generated tool.*schema|durable idempotency|model provider" DEPLOYMENT.md
```

Result: no matches in the OpenClaw setup section (exit code 1 is expected for a successful no-match search).

## Requirement Coverage

- **AUTH-01:** Passed. Deployment docs explain `Authorization: Bearer <BOKFOERING_API_KEY>` as the supported v1.2 agent credential. Tests verify bearer auth wording and ping behavior.
- **DOCS-01:** Passed. `DEPLOYMENT.md` includes a post-deploy OpenClaw/HTTP-agent setup section after first login.
- **DOCS-02:** Passed. Deployment docs distinguish the human frontend URL from the backend API URL for agents on LAN, and include the public HTTPS separation note.
- **DOCS-03:** Passed. Deployment docs include concrete `curl` checks for health and authenticated agent ping using shell variables.
- **DOCS-04:** Passed. Deployment docs include a first setup-only OpenClaw instruction that delegates to the entrypoint and asks the owner before bookkeeping.
- **VER-02:** Passed. Tests check documentation examples against actual route paths and auth behavior (`/health` 200, entrypoint public, ping 401/200 with auth).

## Residual Notes

- Verification uses `.venv/bin/python -m pytest` because system Python does not have pytest installed.
- Tests emit existing Python 3.14 deprecation warnings from pytest-asyncio and sqlite adapters. These warnings are unrelated to Phase 7 behavior.
- One pre-existing test failure (`test_correction_voucher` in `test_ledger.py`) is unrelated to Phase 7 changes and was not introduced by this phase.

## Conclusion

Phase 7 passes aggregate verification and is ready to complete.
