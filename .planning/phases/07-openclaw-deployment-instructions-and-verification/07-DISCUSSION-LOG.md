# Phase 7: OpenClaw Deployment Instructions and Verification - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-06-05
**Phase:** 7-OpenClaw Deployment Instructions and Verification
**Areas discussed:** Owner setup flow, URL guidance, First OpenClaw instruction, Verification examples

---

## Owner Setup Flow

| Option | Description | Selected |
|--------|-------------|----------|
| After login | Put setup immediately after first login, so the owner deploys, verifies, logs in, then connects the agent. | yes |
| After verification | Put setup right after backend/frontend checks, before first login. | |
| Separate appendix | Keep deployment flow shorter, but make the agent path easier to miss. | |

**User's choice:** After login.
**Notes:** OpenClaw setup should be part of the normal post-deploy owner flow.

| Option | Description | Selected |
|--------|-------------|----------|
| Short checklist | 5-7 concrete steps with commands and the starter prompt. | yes |
| Full walkthrough | More explanatory text for each step. | |
| Minimal pointer | Just link the entrypoint and auth format. | |

**User's choice:** Short checklist.
**Notes:** Keep `DEPLOYMENT.md` practical and concise.

| Option | Description | Selected |
|--------|-------------|----------|
| Generic HTTP agent | Describe OpenClaw as an agent that can make HTTP requests with bearer auth. | yes |
| OpenClaw-specific UI | Mention likely UI fields but avoid exact screens. | |
| Exact OpenClaw screens | Pin docs to known OpenClaw screens. | |

**User's choice:** Generic HTTP agent.
**Notes:** Avoid relying on undocumented or version-specific OpenClaw UI details.

| Option | Description | Selected |
|--------|-------------|----------|
| Entrypoint URL + API key | Give OpenClaw the backend entrypoint URL and `BOKFOERING_API_KEY`. | yes |
| Entrypoint URL only | Safer wording, but incomplete unless the key is configured elsewhere. | |
| Long pasted prompt | More self-contained, but duplicates the entrypoint and can go stale. | |

**User's choice:** Entrypoint URL plus API key.
**Notes:** Matches Phase 6's entrypoint delegation decision.

---

## URL Guidance

| Option | Description | Selected |
|--------|-------------|----------|
| Server LAN URL | Use `http://SERVER_IP_OR_HOSTNAME:8000` for OpenClaw and port 3000 for humans. | yes |
| Localhost first | Use `http://localhost:8000`; simple on the server but wrong from another machine. | |
| Both equal weight | Show localhost and LAN host variants everywhere. | |

**User's choice:** Server LAN URL.
**Notes:** OpenClaw may run outside the Bok server, so LAN host guidance is primary.

| Option | Description | Selected |
|--------|-------------|----------|
| Brief separate note | LAN is primary; public HTTPS uses `https://${API_DOMAIN}` for OpenClaw and `https://${APP_DOMAIN}` for humans. | yes |
| Full parallel path | Mirror all commands for LAN and public HTTPS. | |
| LAN only | Omit public agent URL guidance. | |

**User's choice:** Brief separate note.
**Notes:** Keep the recommended path LAN-first while preventing confusion for HTTPS users.

| Option | Description | Selected |
|--------|-------------|----------|
| Warn against `http://api:8000` | Say Docker-internal `BACKEND_URL` is not for OpenClaw outside Docker. | yes |
| Mention only human/API URLs | Cleaner but may leave users copying `.env.production`. | |
| Show a URL table | Very clear but heavier than a short checklist. | |

**User's choice:** Warn against `http://api:8000`.
**Notes:** This directly addresses likely confusion from existing deployment env vars.

| Option | Description | Selected |
|--------|-------------|----------|
| Concrete replaceable value | Show a full replaceable entrypoint URL. | |
| Path plus explanation | Show path separately from base URL. | |
| Environment variable style | Define an API URL variable and use it in examples. | yes |

**User's choice:** Environment variable style.
**Notes:** Useful for both entrypoint and curl commands.

---

## First OpenClaw Instruction

| Option | Description | Selected |
|--------|-------------|----------|
| Entrypoint delegation | Tell OpenClaw to fetch the entrypoint and follow its startup sequence. | yes |
| Self-contained prompt | Include the main startup sequence directly in the prompt. | |
| Verification-only prompt | Ask OpenClaw only to verify access. | |

**User's choice:** Entrypoint delegation.
**Notes:** The entrypoint remains authoritative.

| Option | Description | Selected |
|--------|-------------|----------|
| Process pending work | Process pending intake automatically one item at a time. | |
| Report before posting | Summarize pending work before posting. | |
| Verify only | Limit the first prompt to connection setup. | yes |

**User's choice:** Verify only.
**Notes:** First setup prompt should not begin bookkeeping.

| Option | Description | Selected |
|--------|-------------|----------|
| Mention but don't start | Mention direct posting but only verify connection. | |
| Do not mention posting | Keep the prompt narrowly about connectivity. | |
| Include next-step hint | Verify access, then ask the owner before starting the first bookkeeping run. | yes |

**User's choice:** Include next-step hint.
**Notes:** The first prompt should bridge into the actual bookkeeping run without starting it automatically.

| Option | Description | Selected |
|--------|-------------|----------|
| Connection readiness | Report entrypoint fetched, ping succeeded, and API base URL used. | |
| Full startup inventory | Also list discovered workflow endpoints and guardrails. | |
| Owner action checklist | Report readiness plus the exact next owner command/prompt to start bookkeeping. | yes |

**User's choice:** Owner action checklist.
**Notes:** The output should be useful to the owner after deployment verification.

---

## Verification Examples

| Option | Description | Selected |
|--------|-------------|----------|
| Health + ping + entrypoint | Verify backend health, public entrypoint, and authenticated ping. | yes |
| Ping only | Minimal and focused. | |
| Full startup sequence | Also verify accounting instructions and corrections. | |

**User's choice:** Health + ping + entrypoint.
**Notes:** Covers setup without requiring company-specific state.

| Option | Description | Selected |
|--------|-------------|----------|
| Shell variable | Define `API_KEY=...` then use `Authorization: Bearer ${API_KEY}`. | yes |
| Inline placeholder | Use `Authorization: Bearer <BOKFOERING_API_KEY>`. | |
| Read from env file | Source `.env.production`. | |

**User's choice:** Shell variable.
**Notes:** Avoid repeating secrets in commands.

| Option | Description | Selected |
|--------|-------------|----------|
| Small snippets | Show key fields only. | |
| No snippets | Commands only. | yes |
| Full JSON examples | Show full responses. | |

**User's choice:** No snippets.
**Notes:** Keeps setup docs from becoming brittle.

| Option | Description | Selected |
|--------|-------------|----------|
| Common failures list | Add notes beside setup for auth, port, and Docker URL failures. | |
| Command-only | Let the general troubleshooting section handle errors. | |
| Move to troubleshooting | Add an agent-specific troubleshooting subsection. | yes |

**User's choice:** Move to troubleshooting.
**Notes:** Setup remains clean while errors are still covered.

---

## the agent's Discretion

- Exact Swedish phrasing and heading names.
- Exact shell variable names for examples.
- Test file organization for documentation/example verification.

## Deferred Ideas

None.
