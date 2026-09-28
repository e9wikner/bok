"""`flode-underlag` and the intake pass: the thread owns its files (FU11,
D4, §11.3) and the scripted flows (FU18, testfall 39-42).

Test case numbers refer to SPEC-flode-underlag.md §14. No real LLM: the
pass and the thread turns run with `agentruntime`'s scripted client.
"""

from repositories.intake_repo import IntakeRepository
from tests import test_flode_underlag as fu
from tests.test_flode_underlag import make_source, make_thread

# The module's fixtures, bound here so pytest finds them in this file.
accounts = fu.accounts
client = fu.client
intake_dir = fu.intake_dir
period_id = fu.period_id


def _dropped_in_thread(thread, source_id: str) -> None:
    """A `user_file` post for *source_id*, as `POST /threads/{vk}/messages`
    with an attachment writes it."""
    from services.thread_service import ThreadService

    ThreadService.record_user_file(
        thread,
        filename="kvitto.jpg",
        size_bytes=1024,
        actor="stefan",
        intake_source_id=source_id,
    )


def _counting(monkeypatch):
    from db.database import db

    calls: list = []
    original = db.execute

    def counting(sql, *args, **kwargs):
        calls.append(sql)
        return original(sql, *args, **kwargs)

    monkeypatch.setattr(db, "execute", counting)
    return calls


# ---------------------------------------------------------------------------
# FU11 — the pass skips the thread's files (D4, §11.3)
# ---------------------------------------------------------------------------


def test_38_list_pending_skips_a_source_dropped_in_a_thread(period_id, monkeypatch):
    """Testfall 38: the source with a `user_file` post is not listed, the
    other is; one query each for the list and the count."""
    in_thread = make_source()
    queued = make_source()
    _dropped_in_thread(make_thread(period_id), in_thread)

    calls = _counting(monkeypatch)
    listed = IntakeRepository.list_pending()
    counted = IntakeRepository.count_pending()

    assert [s.id for s in listed] == [queued]
    assert counted == 1
    assert len(calls) == 2
    assert all("user_file" in sql for sql in calls)


def test_38_the_intake_page_still_shows_both(client, auth_headers, period_id):
    """`GET /intake/workspace` reads `list_by_status`: the intake page's
    queue is not the pass's."""
    in_thread = make_source()
    queued = make_source()
    _dropped_in_thread(make_thread(period_id), in_thread)

    resp = client.get(
        "/api/v1/intake/workspace",
        headers=auth_headers,
        params={"status": "pending", "kind": "voucher_source"},
    )

    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert {in_thread, queued} <= ids


def test_fu11_las_underlag_and_the_agent_queue_follow(client, auth_headers, period_id):
    """Avvikelse 3: `las_underlag`, `GET /agent/intake/pending` and the
    status's `queue_depth` read the same queue -- the thread owns the file
    there too."""
    from services.agent_tools import execute_tool
    from services.llm import LLMCapabilities

    in_thread = make_source()
    queued = make_source()
    _dropped_in_thread(make_thread(period_id), in_thread)

    tool = execute_tool(
        "las_underlag",
        {},
        actor="agent",
        capabilities=LLMCapabilities(
            cache_breakpoint=True,
            pdf_document_blocks=True,
            refusal_stop_reason=True,
            streaming=True,
        ),
    )
    http = client.get("/api/v1/agent/intake/pending", headers=auth_headers)

    assert [item["id"] for item in tool["items"]] == [queued]
    assert tool["total"] == 1
    assert http.status_code == 200, http.text
    assert [item["id"] for item in http.json()["items"]] == [queued]


def test_fu11_a_user_text_post_does_not_take_the_source(period_id):
    """Only a `user_file` post naming the source takes it out."""
    from repositories.thread_repo import ThreadRepository

    source_id = make_source()
    ThreadRepository.add_post(
        thread_id=make_thread(period_id).id,
        post_type="user_text",
        actor="stefan",
        body={"text": f"Kvittot {source_id}", "intake_source_id": source_id},
    )

    assert [s.id for s in IntakeRepository.list_pending()] == [source_id]
