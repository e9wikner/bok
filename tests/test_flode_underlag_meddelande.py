"""`flode-underlag`: a message without text (FU14, D8) and the page count of
a pdf in `user_file` (FU17, §10.4).

Test case numbers refer to SPEC-flode-underlag.md §14. The turn is not
run here: `ThreadTurnRunner.start` is captured, so the test sees which post
it hangs on and what the model is told.
"""

import pytest

from config import settings
from repositories.thread_repo import ThreadRepository
from tests import test_flode_underlag as fu
from tests.test_flode_underlag import make_source

# The module's fixtures, bound here so pytest finds them in this file.
accounts = fu.accounts
client = fu.client
intake_dir = fu.intake_dir
period_id = fu.period_id

URL = "/api/v1/threads/bocker.verifikationer/messages"


@pytest.fixture
def started(monkeypatch):
    """Every `ThreadTurnRunner.start` call, as `(trigger_post, message)`,
    with the agent switched on and no turn actually run."""
    from services.thread_stream import ThreadTurnRunner

    calls: list = []

    def capture(self, thread, trigger_post, message, *args, **kwargs):
        calls.append((trigger_post, message))

    monkeypatch.setattr(settings, "agent_runtime_enabled", True)
    monkeypatch.setattr(ThreadTurnRunner, "start", capture)
    return calls


# ---------------------------------------------------------------------------
# FU14 — a message without text, with attachments (D8)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   \n"], ids=["empty", "whitespace"])
def test_33_no_text_one_attachment(client, auth_headers, period_id, started, text):
    """Testfall 33: no `user_text` post, one `user_file`, and the turn
    starts on it with `(bifogade 1 filer)` as the model's message. The
    thread puts no words in the human's mouth."""
    source_id = make_source()

    resp = client.post(
        URL, headers=auth_headers, json={"text": text, "attachments": [source_id]}
    )

    assert resp.status_code == 201, resp.text
    posts = resp.json()["posts"]
    assert [p["type"] for p in posts] == ["user_file"]
    assert posts[0]["body"]["intake_source_id"] == source_id
    stored = ThreadRepository.list_posts(resp.json()["thread_id"])
    assert [p.type for p in stored] == ["user_file"]
    [(trigger, message)] = started
    assert trigger.id == posts[0]["id"]
    assert trigger.type == "user_file"
    assert message == "(bifogade 1 filer)"


def test_33_no_text_two_attachments_starts_on_the_first(
    client, auth_headers, period_id, started
):
    first, second = make_source(), make_source()

    resp = client.post(URL, headers=auth_headers, json={"attachments": [first, second]})

    assert resp.status_code == 201, resp.text
    posts = resp.json()["posts"]
    assert [p["body"]["intake_source_id"] for p in posts] == [first, second]
    [(trigger, message)] = started
    assert trigger.id == posts[0]["id"]
    assert message == "(bifogade 2 filer)"


def test_fu14_text_and_attachment_are_as_before(
    client, auth_headers, period_id, started
):
    """With text: the `user_text` post first, the turn on it, the human's
    own words as the message -- unchanged."""
    source_id = make_source()

    resp = client.post(
        URL,
        headers=auth_headers,
        json={"text": "Kvittot till A-118", "attachments": [source_id]},
    )

    assert resp.status_code == 201, resp.text
    assert [p["type"] for p in resp.json()["posts"]] == ["user_text", "user_file"]
    [(trigger, message)] = started
    assert trigger.type == "user_text"
    assert message == "Kvittot till A-118"


@pytest.mark.parametrize(
    "body",
    [{"text": ""}, {"text": "  "}, {}, {"text": "", "attachments": []}],
    ids=["empty", "whitespace", "nothing", "empty-list"],
)
def test_34_no_text_and_no_attachment_is_422(
    client, auth_headers, period_id, started, body
):
    """Testfall 34: as today -- and text with only whitespace is empty."""
    resp = client.post(URL, headers=auth_headers, json=body)

    assert resp.status_code == 422
    assert started == []
