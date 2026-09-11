---
name: bok-connect
description: Bootstrap a Bok agent connection by resolving a host, reading the public entrypoint, and verifying bearer access with ping. Stop before bookkeeping.
---

# Bok Bootstrap

Use this skill only to establish and verify access to Bok. The host is supplied
in the prompt/body, not as a first-class skill parameter.

## Reach the API

Use `scripts/bok-curl` from the project root:

```text
scripts/bok-curl <METOD> <SÖKVÄG> [json-fil]
```

It resolves the host from `BOK_API_URL`, defaulting to `http://localhost:8000`.
For any other instance, set it for the invocation:

```text
BOK_API_URL={host} scripts/bok-curl POST /api/v1/agent/test/ping
```

Never read `API_HOST` from `.env`; it is a bind address, not a client URL.

## Authenticate safely

The key value is never read into instructions or output. `bok-curl` resolves it
itself, from `BOKFOERING_API_KEY` or the deployment env file, and sets the bearer
header for you — so no key handling is needed here at all.

Without the wrapper, use `Authorization: Bearer $BOKFOERING_API_KEY` through
shell expansion. Do not use a `.env` fallback, print the command with expansion,
or place the key in Git, chat, instructions, or verification fields. See
`docs/to_agent/01_drift_och_atkomst.md`.

## Bootstrap gate

First confirm the host answers: `GET {host}/health` (no auth). This separates an
unreachable or wrong host from a bad key.

1. `GET {host}/api/v1/agent-instructions/entrypoint` without auth.
2. `POST {host}/api/v1/agent/test/ping` with auth; stop unless it returns
   success. This catches a missing, wrong, or misdirected credential.
3. Read the entrypoint payload and follow its `startup_sequence` contract.

Read the entrypoint; do not duplicate its bookkeeping loop here. This skill
ends after bootstrap and must not scan intake, post vouchers, or start
bookkeeping. Return only non-secret status and the next documented action.
