"""Tests for the public agent instruction entrypoint."""

import json
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from api.main import app
from config import settings

ENTRYPOINT_PATH = "/api/v1/agent-instructions/entrypoint"
DRIFT_DOC_PATH = Path("docs/to_agent/01_drift_och_atkomst.md")
PROCESS_DOC_PATH = Path("docs/to_agent/02_bokforingsprocess.md")
EXPECTED_PATHS = {
    "/api/v1/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/agent/test/ping",
    "/api/v1/agent-instructions/accounting",
    "/api/v1/accounting-corrections",
    "/api/v1/agent/intake/pending",
    "/api/v1/agent/intake/{source_id}/processing",
    "/api/v1/agent/intake/{source_id}/failed",
    "/api/v1/agent/vouchers",
    "/api/v1/vouchers/{voucher_id}/source-context",
    "/api/v1/vouchers/{voucher_id}/correction-draft",
    "/api/v1/vouchers/{voucher_id}/correction-notes/{note_id}/suggest",
    "/api/v1/vouchers/{voucher_id}/correction-notes/{note_id}/reject",
    "/api/v1/agent/status",
}


@pytest_asyncio.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _entrypoint(async_client: httpx.AsyncClient) -> dict:
    response = await async_client.get(ENTRYPOINT_PATH)
    assert response.status_code == 200
    return response.json()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.api_key}"}


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


@pytest.mark.asyncio
async def test_agent_entrypoint_is_public_without_auth(async_client):
    response = await async_client.get(ENTRYPOINT_PATH)

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "bokfoering-api"
    assert "version" in data
    assert data["auth"]["value_format"] == "Bearer <BOKFOERING_API_KEY>"


@pytest.mark.asyncio
async def test_agent_entrypoint_contains_expected_links_and_workflow_paths(
    async_client,
):
    data = await _entrypoint(async_client)
    serialized = json.dumps(data)

    for path in EXPECTED_PATHS:
        assert path in serialized

    assert data["links"]["openapi"] == "/openapi.json"
    assert data["workflow_endpoints"]["ping"]["path"] == "/api/v1/agent/test/ping"
    assert (
        data["workflow_endpoints"]["post_voucher"]["path"] == "/api/v1/agent/vouchers"
    )
    assert data["workflow_endpoints"]["agent_status"]["path"] == "/api/v1/agent/status"
    assert data["workflow_endpoints"]["agent_status"]["method"] == "GET"


@pytest.mark.asyncio
async def test_agent_entrypoint_documents_correction_note_workflow(async_client):
    data = await _entrypoint(async_client)
    serialized = json.dumps(data)

    assert "correction_note" in serialized
    assert "/api/v1/vouchers/{voucher_id}/correction-draft" in serialized
    assert "/api/v1/vouchers/{voucher_id}/source-context" in serialized
    assert "draft B-series" in serialized
    assert "Never edit the original posted voucher directly" in serialized


@pytest.mark.asyncio
async def test_agent_entrypoint_uses_relative_paths_only(async_client):
    data = await _entrypoint(async_client)

    for value in _strings(data):
        assert "http://" not in value
        assert "https://" not in value

    path_values = [value for value in _strings(data) if value.startswith("/")]
    assert path_values
    assert all(value.startswith("/") for value in path_values)


@pytest.mark.asyncio
async def test_agent_entrypoint_prescribes_startup_order_and_guardrails(async_client):
    data = await _entrypoint(async_client)
    sequence = data["startup_sequence"]

    assert sequence[0]["path"] == ENTRYPOINT_PATH
    assert sequence[0]["auth_required"] is False
    assert sequence[1]["path"] == "/api/v1/agent/test/ping"
    assert sequence[1]["auth_required"] is True
    assert sequence[2]["path"] == "/api/v1/agent-instructions/accounting"
    assert sequence[3]["path"] == "/api/v1/accounting-corrections"
    assert sequence[4]["path"] == "/api/v1/agent/intake/pending"

    guidance = json.dumps(data["startup_sequence"] + data["guardrails"])
    assert "one item at a time" in guidance
    assert "immutable" in guidance
    assert "correction vouchers" in guidance
    assert "failed or warning" in guidance
    assert "intake_source_ids" in guidance
    assert "pending queue" in guidance
    assert "guidance" in guidance
    assert "Idempotency-Key" in guidance
    assert "Idempotent-Replay" in guidance


@pytest.mark.asyncio
async def test_agent_entrypoint_tells_agents_to_stop_on_auth_failure(async_client):
    data = await _entrypoint(async_client)
    serialized = json.dumps(data).lower()

    assert data["auth"]["required_on"] == (
        "all workflow endpoints except this public entrypoint and health checks"
    )
    assert data["auth"]["check"]["on_401"]
    assert "401" in serialized
    assert "fix auth" in serialized or "fix the authorization header" in serialized
    assert "until ping returns 200" in serialized


@pytest.mark.asyncio
async def test_agent_entrypoint_documents_bank_input_transaction_source(async_client):
    data = await _entrypoint(async_client)
    contract = data["bank_input_contract"]
    serialized = json.dumps(contract)

    assert contract["queue_source"] == "/api/v1/agent/intake/pending"
    assert "transaction_ids" in contract["transaction_ids_source"]
    assert contract["download"] == "/api/v1/bank-inputs/{bank_input_id}/file"
    assert contract["post_voucher_fields"] == ["bank_input_ids", "bank_transaction_ids"]
    assert "/api/v1/bank-transactions" in serialized
    assert "not part of the current agent API" in serialized


@pytest.mark.asyncio
async def test_agent_entrypoint_discloses_the_internal_runtime_status_endpoint(
    async_client,
):
    data = await _entrypoint(async_client)
    serialized = json.dumps(data)

    assert "/api/v1/agent/status" in serialized
    assert data["workflow_endpoints"]["agent_status"]["path"] == "/api/v1/agent/status"
    guardrails = " ".join(str(item) for item in data["guardrails"])
    assert "/api/v1/agent/status" in guardrails
    assert "internal runtime" in guardrails
    assert "runs this external agent did not start" in guardrails


@pytest.mark.asyncio
async def test_agent_entrypoint_discloses_unsupported_features(async_client):
    data = await _entrypoint(async_client)
    unsupported = " ".join(data["unsupported_features"]).lower()

    assert "persistent" in unsupported
    assert "credential lifecycle" in unsupported
    assert "generated tool-schema discovery" in unsupported
    # Durable idempotency now covers posting and correcting. The disclosure
    # narrows as the implementation grows; it never disappears.
    assert (
        "durable idempotency covers /api/v1/agent/vouchers and "
        "/api/v1/vouchers/{voucher_id}/correct" in unsupported
    )
    assert "/api/v1/bank-transactions" in unsupported


@pytest.mark.asyncio
async def test_agent_entrypoint_documents_idempotency_contract(async_client):
    data = await _entrypoint(async_client)
    contract = data["idempotency_contract"]

    assert contract["header"] == "Idempotency-Key"
    assert "UUID" in contract["value_format"]
    assert contract["required_on"] == [
        "/api/v1/agent/vouchers",
        "/api/v1/vouchers/{voucher_id}/correct",
    ]
    assert contract["server_enforced"] is False
    assert "same key" in contract["retry_rule"]
    assert "Idempotent-Replay: true" in contract["retry_rule"]
    assert "new key" in contract["one_key_per_event"]
    assert contract["conflicts"]["422"].startswith("idempotency_key_reuse")
    assert contract["conflicts"]["409"].startswith("request_in_flight")
    assert contract["conflicts"]["400"].startswith("invalid_idempotency_key")
    assert "idempotency_key_missing" in contract["transition"]


def test_agent_process_doc_requires_an_idempotency_key_on_posting():
    text = PROCESS_DOC_PATH.read_text(encoding="utf-8")

    assert "Idempotency-Key" in text
    assert "Idempotent-Replay: true" in text
    assert "idempotency_key_reuse" in text
    assert "request_in_flight" in text
    assert "En affärshändelse, en nyckel" in text
    assert "Omförsök använder samma nyckel" in text


def test_agent_process_doc_describes_the_internal_runtime_path():
    text = PROCESS_DOC_PATH.read_text(encoding="utf-8")

    assert "AGENT_RUNTIME_ENABLED=true" in text
    assert "intern runtime" in text
    assert "startas manuellt tills vidare" in text
    assert "vägrar starta\nutan en prissatt modell" in text
    assert (
        "posta när underlaget och konteringen är tillräckligt klara, avstå annars"
        in text
    )
    # The external, human-started path is still explicitly documented as
    # working exactly as before (SPEC-agentruntime.md §12.5b) -- this note
    # must not read as if it replaced that path.
    assert "En människa kan fortfarande starta en" in text
    assert "scripts/bok-curl" in text


def test_agent_process_doc_distinguishes_a_thread_reply_from_an_abstention():
    """SPEC-tradar.md §11/T13: the one thing the thread path changed about
    what the agent *does*.

    A turn that ends with no tool call is an unresolved outcome for a
    document (`agent_no_outcome`) and a perfectly good *answer* in a thread.
    This directory is literally the system prompt, and it is shared byte for
    byte by both entry points (test case 12), so it has to name both -- a
    model reading only the document rule would treat answering a question as
    a failure and reach for `registrera_avstaende` to close the turn.
    """
    text = PROCESS_DOC_PATH.read_text(encoding="utf-8")

    # Both entry points are named, and each one's outcomes with it.
    assert "Ett underlagspass ur kön" in text
    assert "Ett meddelande i en tråd" in text
    assert "ett rent svar ett fullgott utfall" in text
    assert "oavslutat utfall" in text

    # And the misuse the distinction exists to prevent is called out.
    assert "inte för att avsluta ett samtal" in text
    assert "Ett samtalssvar i en tråd är inte ett" in text


def test_agent_process_doc_keeps_the_ledger_rules_identical_on_both_paths():
    """The threshold for posting does not move because a human asked.

    SPEC-tradar.md antagande 4: "En agent som postar från ett chattsvar går
    samma väg som en agent som postar från ett underlag." If this ever reads
    as two different standards, the thread has become a softer way into the
    general ledger.
    """
    text = PROCESS_DOC_PATH.read_text(encoding="utf-8")

    assert "Tröskeln för att posta är densamma oavsett vem" in text
    assert "samma verktyg, samma skrivväg till" in text
    assert "samma immutabilitet" in text
    # Unchanged, and still stated unconditionally.
    assert "Postade verifikationer är immutabla" in text


@pytest.mark.asyncio
async def test_agent_entrypoint_excludes_sensitive_or_company_state_fields(
    async_client,
):
    serialized = json.dumps(await _entrypoint(async_client))

    for forbidden in [
        "http://",
        "https://",
        "secret_key",
        "api_key",
        "token_value",
        "original_filename",
    ]:
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_agent_ping_requires_auth(async_client):
    response = await async_client.post("/api/v1/agent/test/ping")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_agent_ping_returns_dynamic_bounded_auth_data(async_client):
    response = await async_client.post(
        "/api/v1/agent/test/ping",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "bokfoering-api"
    assert data["version"] == settings.api_version
    assert data["agent"] == "api"
    assert "timestamp" in data
    assert datetime.fromisoformat(data["timestamp"]).tzinfo is not None
    assert data["timestamp"] != "2026-03-21" + "T10:00:00"


@pytest.mark.asyncio
async def test_placeholder_agent_routes_are_removed(async_client):
    removed_routes = [
        ("GET", "/api/v1/agent/" + "spec/openapi", None),
        ("POST", "/api/v1/agent/" + "spec/tools", {}),
        ("GET", "/api/v1/agent/" + "keys", None),
        ("POST", "/api/v1/agent/" + "operations/idempotent/test-op", {}),
    ]

    for method, path, payload in removed_routes:
        response = await async_client.request(
            method,
            path,
            headers=_auth_headers(),
            json=payload,
        )
        assert response.status_code in {404, 405}


def test_agent_process_doc_describes_be_om_beslut_and_when_to_use_it():
    """SPEC-beslut.md §6.4, §8: the tool exists, and the distinction from
    ``registrera_avstaende`` this task builds on -- a decision arising in a
    conversation in a view versus a `failed` attempt on a queued source.
    """
    text = PROCESS_DOC_PATH.read_text(encoding="utf-8")

    assert "be_om_beslut" in text
    assert "Det postar\ningenting, det ändrar ingenting" in text
    assert "hör till ett beslut som uppstår i ett samtal i en vy" in text
    assert (
        "`registrera_avstaende` hör till ett underlag i intagskön och "
        "skriver ett\n`failed`-försök" in text
    )


def test_agent_process_doc_states_the_decision_options_threshold():
    """SPEC-beslut.md §11.1: the rule the agent needs to be able to follow --
    an options list that changes the books without an open decision behind
    it is rejected by the server.
    """
    text = PROCESS_DOC_PATH.read_text(encoding="utf-8")

    assert (
        "varje ändring i böckerna som en människa väljer är antingen tagen\n"
        "inuti ett redan öppet beslut, eller själv ett beslut" in text
    )
    assert "**avvisas av servern**" in text
    assert "Lägg fram beslutet först, lägg alternativen under" in text


def test_agent_process_doc_states_the_options_list_contract_rules():
    """SPEC-beslut.md §6.3/§11.1: the two server-enforced rules on the
    alternative list, not a client styling choice.
    """
    text = PROCESS_DOC_PATH.read_text(encoding="utf-8")

    assert "serverregler, inte stilfrågor" in text
    assert "högst ett alternativ får vara `recommended`" in text
    assert "sista alternativet ska alltid vara en väg ut" in text


def test_agent_process_doc_says_the_agents_own_text_is_stored_verbatim():
    """SPEC-beslut.md §6.4/plan.md: `reason`, `consequence` and each
    option's `rationale` are shown to the human exactly as written -- a
    reason to write them for a reader, not a log.
    """
    text = PROCESS_DOC_PATH.read_text(encoding="utf-8")

    assert (
        "`reason`, `consequence` och varje alternativs `rationale` lagras "
        "och visas för\nanvändaren ordagrant" in text
    )


def _process_doc_flat() -> str:
    """The process doc with its line wrapping undone, so an assertion pins
    the sentence and not where the editor happened to break it."""
    return " ".join(PROCESS_DOC_PATH.read_text(encoding="utf-8").split())


def test_agent_process_doc_describes_foresla_verifikation():
    """SPEC-flode-verifikationer.md §5.1, §5.7: the eleventh tool exists,
    it never posts, the human does, and the number comes with the posting.
    """
    text = _process_doc_flat()

    assert "## Lägg fram ett förslag" in text
    assert "`foresla_verifikation` skapar ett förslag" in text
    assert "Det postar aldrig" in text
    assert "numret sätts först då" in text


def test_agent_process_doc_says_when_to_propose_and_when_to_post_directly():
    """SPEC-flode-verifikationer.md §12.2 with SPEC-beslut.md §11.1: a
    proposal after an answered decision carries `decision_id`, direct
    posting stays for what the agent is sure of -- and a proposal is not a
    softer way around the abstention list.
    """
    text = _process_doc_flat()

    assert "användaren har besvarat ett beslut" in text
    assert "ange beslutets id i `decision_id`" in text
    assert "vill att användaren ser konteringen innan den bokförs" in text
    assert "Posta direkt med `posta_verifikation` när" in text
    assert "Ett förslag är inte ett sätt att slippa avstå" in text
    assert "`replaces_draft_id`" in text
    # The threshold for posting is still stated, unchanged, for both paths.
    assert "Tröskeln för att posta är densamma oavsett vem" in text


def test_agent_process_doc_says_a_correction_is_always_a_proposal():
    """SPEC-flode-verifikationer.md §12.5: the agent may post directly, but
    never a correction. It goes through a proposal the human posts, with
    `correction_of` -- and if that cannot be made, the agent says so rather
    than posting the correction itself.
    """
    text = _process_doc_flat()

    assert (
        "En rättelse av en postad verifikation är alltid ett förslag, aldrig "
        "`posta_verifikation`" in text
    )
    assert "originalets id i `correction_of`" in text
    assert "posta aldrig en rättelse själv" in text


def _flat(text: str) -> str:
    return " ".join(text.split())


def _assert_interpretation_rules(text: str) -> None:
    """The rules of SPEC-underlagstolkning.md §9, as SPEC-flode-underlag.md
    §11.2 rewrote them, as the agent reads them. Tool names are the ones in
    ``services.agent_tools._TOOL_SPECS``."""
    # The rules sit in the accounting instruction, not somewhere else.
    instruction = text[text.index("# Bokföringsinstruktion för svensk redovisning") :]
    assert "## Tolka underlaget innan du bokför" in instruction

    # Interpret before posting or proposing.
    assert "Innan du postar eller föreslår en verifikation för ett underlag:" in text
    assert "läs filen med `hamta_underlagsfil` och anropa `tolka_underlag`" in text
    first_rule = instruction.index("anropa `tolka_underlag`")
    assert first_rule < instruction.index("`posta_verifikation`")
    # U15 (§12.6 f): a session without the tool does the same over HTTP.
    assert (
        "En session utan verktyget `tolka_underlag` gör samma sak med "
        "`POST /api/v1/intake/{id}/interpretation`, med samma fält" in text
    )
    assert instruction.index("POST /api/v1/intake/{id}/interpretation") < (
        instruction.index('**`match.kind = "exact"`')
    )

    # A match on an already posted voucher: do not post. Rewritten by
    # flode-underlag (§11.2 punkt 3-4): an exact match is linked, no
    # longer abstained from; a difference is still abstained from in the
    # pass, with the number and the difference, and laid out as a decision
    # with both amounts in a thread.
    assert '`match.kind = "exact"`' in text
    assert '`match.kind = "amount_diff"`' in text
    assert "Posta inte" in text
    assert (
        "avstå med `registrera_avstaende` och skriv verifikationsnumret och "
        "differensen i motiveringen" in text
    )
    assert "båda beloppen" in text

    # U13 (§12.6 d): an exact amount without a date is not told apart from
    # a recurring amount -- do not post, abstain in the pass with the
    # number and the missing date, ask in a thread.
    assert '`match.kind = "exact_no_date"`' in text
    assert "underlaget saknar datum" in text
    assert (
        "avstå med `registrera_avstaende` och skriv verifikationsnumret och att "
        "underlaget saknar datum i motiveringen" in text
    )
    assert "fråga om det är samma köp" in text
    assert "nämn verifikationsnumret och beloppet" in text
    no_date = text.index('`match.kind = "exact_no_date"`')
    assert text.index("Posta inte", no_date) < text.index("`match = null`")

    # No match but candidates: ask, do not choose.
    assert "`match = null`" in text
    assert "Välj inte själv bland kandidaterna" in text

    # Low confidence: no guessed amounts.
    assert '`confidence = "low"`' in text
    assert "gissa inte fram ett belopp" in text

    # The hypothesis is rendered as a hypothesis.
    assert "återge den som en hypotes, inte som ett faktum" in text
    assert "uttryckligen säger att det är en gissning" in text


def _assert_no_queue_driving(text: str) -> None:
    """L7: nothing tells the agent to ask for an underlag on its own, oldest
    first, or to name the next voucher missing one. Phrasings, not sentences."""
    flat = _flat(text).lower()
    assert "**be om underlag**" not in flat
    assert "be om ett i taget" not in flat
    assert "äldst först" not in flat
    assert "be om dess underlag" not in flat
    assert not re.search(r"nästa\s+(verifikation|underlag)", flat)
    assert not re.search(r"nästa[^.]{0,80}saknar underlag", flat)
    assert "hur många som är kvar" not in flat


def _assert_linking_rules(text: str) -> None:
    """SPEC-flode-underlag.md §11.2's nine points (test case 43)."""
    instruction = text[text.index("# Bokföringsinstruktion för svensk redovisning") :]
    section = instruction[
        instruction.index("## Tolka underlaget innan du bokför") : instruction.index(
            "## Periodisering och datum"
        )
    ]

    # 1. The agent does not drive the queue of vouchers missing an underlag
    # (SPEC-lasbarhet.md §4.2, L7): it answers when asked, from
    # las_verifikationer, with the reason per voucher.
    assert "be inte om underlag på eget initiativ" in section
    assert "Frågar användaren vilka som saknar underlag" in section
    assert "`las_verifikationer`" in section
    assert "`missing_attachment`" in section
    assert "`age_days`" in section
    assert "varför underlaget behövs för just den verifikationen" in section
    _assert_no_queue_driving(section)

    # 2. Nothing linked without a yes but the exact. The old "say you read
    # the file" is gone: SPEC-lasbarhet.md §4.2, the agent does not narrate
    # its tools.
    assert "säg att du läser den" not in section
    assert (
        "Ingenting kopplas förrän användaren har sagt ja, utom vid exakt match"
        in section
    )

    # 3. Exact: link with koppla_underlag, in a thread and in the pass.
    exact = section.index('**`match.kind = "exact"`:**')
    assert section.index("`koppla_underlag`", exact) < section.index(
        '`match.kind = "amount_diff"`'
    )
    assert "i en tråd och i ett underlagspass" in section
    assert "`source_matches_posted_voucher`" in section
    assert "`POST /api/v1/intake/{id}/link`" in section

    # 4. Difference in a thread: be_om_beslut with the three options, in the
    # panel's order; the pass abstains as before.
    assert '`source: {"kind": "intake_source", "id": …}`' in section
    assert "båda beloppen, underlagets och verifikationens, i `reason`" in section
    first = section.index("*Koppla och bokför skillnaden*")
    second = section.index("*Koppla utan att ändra*")
    third = section.index("*Det är ett annat köp*")
    assert first < second < third
    assert "`is_exit`" in section[third:]
    assert "Rekommendera alternativ 1 när `hypothesis` pekar på en rad" in section
    assert "koppla med `koppla_underlag` och beslutets `decision_id`" in section

    # 5. The difference is proposed after the link, never posted directly.
    assert (
        "**Bokför skillnaden** (alternativ 1) med `foresla_verifikation` och "
        "beslutets `decision_id`, efter kopplingen" in section
    )
    assert "Aldrig med `posta_verifikation`, och aldrig före kopplingen" in section

    # 6. Exact without date: a yes is a decision, not a link on free text.
    assert "inte en koppling på ett fritextsvar" in section

    # 7. No match: ask which voucher; the answer is a decision.
    assert "Svaret blir ett beslut om den verifikationen" in section
    assert "tolka om med `expected_voucher_id` först" in section

    # 8. Low confidence: ask for a new underlag, do not link.
    assert "gissa inte fram ett belopp och koppla inte" in section

    # 9. After a link: one sentence about the link, nothing about the next
    # voucher (SPEC-lasbarhet.md §4.2, L7).
    rule_9 = section[section.index("**Efter en koppling:**") :]
    assert "en mening om kopplingen" in rule_9
    assert "ålder" not in rule_9

    # The stop list names the link.
    stop = instruction[instruction.index("## Stopplista") :]
    assert "kopplas med `koppla_underlag` i stället" in stop


@pytest.mark.asyncio
async def test_accounting_instruction_as_served_requires_tolka_underlag(
    test_db, async_client
):
    """SPEC-underlagstolkning.md §9/§10 test case 38: the instruction as the
    accounting endpoint serves it -- the one an external agent reads at step
    three of its startup sequence -- carries the new rules."""
    response = await async_client.get(
        "/api/v1/agent-instructions/accounting", headers=_auth_headers()
    )
    assert response.status_code == 200

    _assert_interpretation_rules(_flat(response.json()["system"]["content_markdown"]))
    _assert_linking_rules(_flat(response.json()["system"]["content_markdown"]))


def test_runtime_system_prompt_requires_tolka_underlag(test_db):
    """Test case 38, the internal runtime's side: the same rules reach the
    system prompt the runtime sends to the model."""
    from services.agent_session import build_system_prompt

    _assert_interpretation_rules(_flat(build_system_prompt()))
    _assert_linking_rules(_flat(build_system_prompt()))


def test_agent_system_access_doc_does_not_advertise_removed_schema_routes():
    text = DRIFT_DOC_PATH.read_text(encoding="utf-8")

    assert "GET /api/v1/agent/spec/openapi" not in text
    assert "POST /api/v1/agent/spec/tools" not in text
    assert "finns inte i aktuell version" in text


ACCOUNTING_DOC_PATH = Path("docs/to_agent/03_bokforingsinstruktion.md")


def _thread_writing_section(text: str) -> str:
    """The section "Att skriva i en tråd" (SPEC-lasbarhet.md §4.2, M3),
    sliced out of the accounting instruction."""
    instruction = text[text.index("# Bokföringsinstruktion för svensk redovisning") :]
    heading = "## Att skriva i en tråd"
    assert heading in instruction
    start = instruction.index(heading)
    # After the agent's writing rules, before the stop list.
    assert instruction.index("## Skrivregler för agenten") < start
    return instruction[start : instruction.index("## Stopplista")]


def _bullets(section: str) -> list[str]:
    """The section's bullets, flattened and without emphasis markers."""
    return [
        _flat(chunk).replace("**", "").lower() for chunk in section.split("\n- ")[1:]
    ]


def _assert_thread_writing_rules(text: str) -> None:
    section = _thread_writing_section(text)
    bullets = _bullets(section)

    # After be_om_beslut the final answer is one sentence pointing at the
    # decision, without repeating the card.
    after_decision = [
        b
        for b in bullets
        if "`be_om_beslut`" in b and "slutsvar" in b and "en mening" in b
    ]
    assert after_decision, "no rule on the final answer after be_om_beslut"
    assert "upprepa inte" in after_decision[0]

    # The final answer is at most three sentences otherwise.
    assert any("slutsvar" in b and "tre meningar" in b for b in bullets)

    # The decision's own fields are short.
    fields = [b for b in bullets if "`reason`" in b and "`consequence`" in b]
    assert fields and "`rationale`" in fields[0]

    # The user is "du"; the agent does not narrate its tools.
    assert any('"du"' in b and '"människan"' in b for b in bullets)
    assert any("verktyg" in b and "skriv resultatet" in b for b in bullets)

    # After a posting, the number; after a link, one sentence about the link
    # and nothing about the next voucher (L7).
    assert any("postning" in b and "verifikationsnumret" in b for b in bullets)
    after_link = [b for b in bullets if b.startswith("efter en koppling")]
    assert after_link, "no rule on the final answer after a link"
    assert "en mening om kopplingen" in after_link[0]
    assert "ålder" not in after_link[0]
    _assert_no_queue_driving(section)


def test_accounting_instruction_has_the_thread_writing_section():
    """SPEC-lasbarhet.md M3: the file itself carries the section."""
    _assert_thread_writing_rules(ACCOUNTING_DOC_PATH.read_text(encoding="utf-8"))


def test_runtime_system_prompt_has_the_thread_writing_section(test_db):
    """M3, the runtime's side: the section reaches the model's system prompt."""
    from services.agent_session import build_system_prompt

    _assert_thread_writing_rules(build_system_prompt())


def test_accounting_instruction_does_not_drive_the_underlag_queue():
    """SPEC-lasbarhet.md §4.2 L7: the list in Böcker → Verifikationer shows
    what is missing, and the user picks what to upload next. Nowhere in 03
    does the agent ask for an underlag on its own or name the next one."""
    _assert_no_queue_driving(ACCOUNTING_DOC_PATH.read_text(encoding="utf-8"))


# The one place "människan" may stand: the rule in 03 that forbids it,
# quoted. Everything else the agent reads says "användaren".
_MANNISKAN_PROHIBITION = 'Kalla aldrig användaren "människan"'


def test_agent_reads_anvandaren_not_manniskan():
    """SPEC-lasbarhet.md §4.2, L6: the agent repeats what it reads, so
    neither the tool schema the model gets nor ``docs/to_agent/*.md`` calls
    the user "människan" -- save the quoted rule that forbids it."""
    from services.agent_tools import AGENT_TOOL_DEFINITIONS

    schema = json.dumps(AGENT_TOOL_DEFINITIONS, ensure_ascii=False)
    assert "människan" not in schema.lower()

    for path in sorted(Path("docs/to_agent").glob("*.md")):
        text = " ".join(path.read_text(encoding="utf-8").split())
        text = text.replace(_MANNISKAN_PROHIBITION, "")
        assert "människan" not in text.lower(), path.name


def test_be_om_beslut_fields_state_their_length():
    """SPEC-lasbarhet.md §4.2, L6: the lengths from "Att skriva i en tråd"
    are in the schema, on the fields themselves."""
    from services.agent_tools import AGENT_TOOL_DEFINITIONS

    (tool,) = [t for t in AGENT_TOOL_DEFINITIONS if t["name"] == "be_om_beslut"]
    schema = tool["input_schema"]
    props = schema["properties"]
    assert "högst två meningar" in props["reason"]["description"].lower()
    assert "belopp" in props["reason"]["description"]
    assert "en mening" in props["consequence"]["description"].lower()
    option = schema["$defs"]["BeOmBeslutOption"]["properties"]
    assert "en mening" in option["rationale"]["description"].lower()
