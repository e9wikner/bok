# Phase 6 Verification: Agent Instruction Entrypoint and API Discovery

**Verified:** 2026-06-04T22:29:00Z
**Status:** Passed

## Scope Verified

- Public-safe agent instruction entrypoint exists at `GET /api/v1/agent-instructions/entrypoint`.
- Entrypoint returns service identity, configured API version, relative docs/schema/health links, bearer auth guidance, ordered startup sequence, workflow endpoints, guardrails, unsupported features, and agent startup instructions.
- Placeholder agent key lifecycle, generated spec/tool, and durable idempotency routes are removed from the API.
- Authenticated ping returns bounded dynamic data: status, service, configured version, actor, and current UTC timestamp.
- README points owner/agent onboarding to the entrypoint and `BOKFOERING_API_KEY`, not removed placeholder endpoints.

## Verification Commands

```bash
.venv/bin/python -m pytest tests/test_agent_entrypoint.py tests/test_agent_instructions_separation.py tests/test_agent_accounting_workflow.py
```

Result: passed, 23 tests.

```bash
rg "/api/v1/agent/keys|/api/v1/agent/spec|/api/v1/agent/operations/idempotent" README.md api/routes tests
```

Result: no matches. Exit code 1 is expected for a successful no-match search.

```bash
rg "/api/v1/agent-instructions/entrypoint" README.md tests api/routes/agent_instructions.py
```

Result: found references in `api/routes/agent_instructions.py`, `README.md`, and `tests/test_agent_entrypoint.py`.

```bash
rg -n "@router\.(get|post|put|delete)\(\"/(keys|spec|operations/idempotent)|uuid|hashlib|2026-03-21T10:00:00" api/routes/agent.py
```

Result: no matches. Exit code 1 is expected for a successful no-match search.

## Requirement Coverage

- **ONBD-01:** Passed. Entrypoint route exists and is tested without auth.
- **ONBD-02:** Passed. Entrypoint includes service, version, docs, schema, health, and ping paths.
- **ONBD-03:** Passed. Entrypoint includes ordered startup workflow.
- **ONBD-04:** Passed. Entrypoint includes bookkeeping guardrails.
- **AUTH-02:** Passed. Placeholder key lifecycle routes are removed and README no longer presents them.
- **API-01:** Passed. Ping returns current configured version, actor, and current timestamp.
- **API-02:** Passed. Placeholder schema/tool routes are removed; `/openapi.json` is the truthful schema link.
- **API-03:** Passed. Entrypoint links instructions, corrections, pending intake, direct posting, processing failure, and source-context endpoints.
- **VER-01:** Passed. Backend tests cover entrypoint contract, safe content, auth guidance, ping behavior, and removed-route behavior.

## Residual Notes

- Verification uses `.venv/bin/python -m pytest` because system Python does not have pytest installed.
- Tests emit existing Python 3.14 deprecation warnings from pytest-asyncio, sqlite adapters, and one Pydantic class-based config. These warnings are unrelated to Phase 6 behavior.
- Phase 7 still owns deployment documentation requirements: `AUTH-01`, `DOCS-01`, `DOCS-02`, `DOCS-03`, `DOCS-04`, and `VER-02`.

## Conclusion

Phase 6 passes aggregate verification and is ready to complete.
