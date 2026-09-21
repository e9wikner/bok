"""API routes for the per-view thread (docs/redesign/SPEC-tradar.md §1, §5).

HTTP only, per AGENTS.md's layering rule: parse, authenticate, resolve the
view and the fiscal year, and map domain outcomes to status codes. Every
decision about what a thread *is* lives in `services/thread_service.py`,
`services/thread_session.py` and `repositories/thread_repo.py`.

`README.md`: "Chatten hör till vyn, inte till appen. Varje vy har sin egen
tråd med sin egen historik. Byter man vy byter man tråd."
"""

import asyncio
import logging
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from fastapi.responses import StreamingResponse

from api.deps import get_current_actor
from api.schemas import (
    ThreadMessageRequest,
    ThreadMessageResponse,
    ThreadModelRequest,
    ThreadModelResponse,
    ThreadPostResponse,
    ThreadResponse,
)
from config import settings
from domain.models import Thread, ThreadPost
from domain.types import ThreadViewKey
from repositories.intake_repo import IntakeRepository
from repositories.period_repo import PeriodRepository
from repositories.thread_repo import ThreadRepository
from services.llm import UnknownModelError, get_model_info
from services.thread_service import ThreadService
from services.thread_stream import (
    EVENT_MESSAGE_COMPLETED,
    ThreadTurnRunner,
    format_sse,
    get_broker,
    post_event_payload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/threads", tags=["threads"])


def _validate_view_key(view_key: str) -> str:
    """SPEC §5: the list of seven is closed and validated.

    An unknown key gives `404`, **not an empty thread** -- otherwise a typo
    in the client silently creates a thread nobody ever finds their way back
    to, and the bug shows up as a conversation that lost its history.
    """
    try:
        return ThreadViewKey(view_key).value
    except ValueError:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={
                "error": f"Unknown view_key: {view_key!r}",
                "code": "unknown_view_key",
                "details": "known views: "
                + ", ".join(key.value for key in ThreadViewKey),
            },
        )


def _current_fiscal_year_id() -> Optional[str]:
    """The fiscal year a new thread belongs to (decision §12.3).

    Same resolution as `services.overview.OverviewService._current_fiscal_
    year`: the year that contains today, else the most recent one --
    `list_fiscal_years` is newest first. `None` when the books have no
    fiscal year at all, which is a legitimate state for a fresh install and
    not an error to raise at a reader.
    """
    from datetime import date

    today = date.today()
    fiscal_years = PeriodRepository.list_fiscal_years()
    for fiscal_year in fiscal_years:
        if fiscal_year.start_date <= today <= fiscal_year.end_date:
            return fiscal_year.id
    return fiscal_years[0].id if fiscal_years else None


def _post_response(post: ThreadPost) -> ThreadPostResponse:
    return ThreadPostResponse(
        id=post.id,
        seq=post.seq,
        type=post.type,
        actor=post.actor,
        created_at=post.created_at,
        body=post.body,
        traces=post.traces,
        run_id=post.run_id,
    )


@router.get("/{view_key}", response_model=ThreadResponse)
async def get_thread(
    view_key: str,
    since: Optional[int] = Query(
        None,
        description=(
            "Exclusive `seq` cursor: returns only the posts after it, so a "
            "client that reconnects gets what it missed and nothing it "
            "already has."
        ),
    ),
    fiscal_year_id: Optional[str] = Query(
        None,
        description=(
            "Read an older year's thread. Omitted, this is the current "
            "year's (decision §12.3: one thread per view and fiscal year)."
        ),
    ),
    actor: str = Depends(get_current_actor),
):
    """The view's thread, oldest post first (SPEC §1).

    A pure read: it creates nothing. A view that has not been written in
    this year answers `200` with an empty `posts` and a `thread_id` of
    `None` -- the thread is created by the first message, not by looking.
    """
    view_key = _validate_view_key(view_key)
    target_year = fiscal_year_id or _current_fiscal_year_id()
    archive = ThreadRepository.list_fiscal_years(view_key)

    thread = ThreadRepository.find(view_key, target_year) if target_year else None
    if thread is None:
        return ThreadResponse(
            view_key=view_key,
            fiscal_year_id=target_year,
            archive_fiscal_year_ids=archive,
        )

    posts = ThreadRepository.list_posts(thread.id, since=since)
    return ThreadResponse(
        view_key=view_key,
        thread_id=thread.id,
        fiscal_year_id=thread.fiscal_year_id,
        model=thread.model,
        posts=[_post_response(post) for post in posts],
        cursor=ThreadRepository.last_seq(thread.id),
        archive_fiscal_year_ids=archive,
    )


@router.post(
    "/{view_key}/messages",
    response_model=ThreadMessageResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def post_message(
    view_key: str,
    request: ThreadMessageRequest,
    actor: str = Depends(get_current_actor),
):
    """Write a message to the view's thread and answer immediately (§6.1).

    The response carries **the human's own posts and nothing else**: her
    reply has to stand in the thread before the agent has said a word
    (§6.1 step 2). The agent's answer arrives over
    `GET /threads/{view_key}/stream`, which is also where the session is
    actually started -- one writer per run, and this request is not it.

    This is also the decision channel: `README.md` requires that every
    decision a `BeslutKort`'s primary button can express is equally
    expressible as plain text here.
    """
    view_key = _validate_view_key(view_key)
    fiscal_year_id = _current_fiscal_year_id()
    if fiscal_year_id is None:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail={
                "error": "No fiscal year exists to hang a thread off",
                "code": "no_fiscal_year",
                "details": (
                    "A thread belongs to a view and a fiscal year "
                    "(SPEC-tradar.md §12.3). Create a fiscal year first."
                ),
            },
        )

    thread = ThreadRepository.get_or_create(
        view_key=view_key,
        fiscal_year_id=fiscal_year_id,
        model=settings.llm_default_model,
    )

    posts = [ThreadService.record_user_message(thread, request.text, actor=actor)]
    posts.extend(_attachment_posts(thread, request.attachments, actor))

    # Started here, answered over the stream. The worker gets its own
    # thread (and so its own SQLite connection, per `db/database.py`'s
    # thread-local model) and its own `agent_runs` row -- this request
    # neither waits for it nor shares a writer with it.
    #
    # Gated on the same global switch as the intake pass. The agent being
    # off is a *state*, not a per-message failure: §7 makes the agent mode
    # global and `GET /agent/status` is where it is shown. Writing an
    # `error` post for every message instead would fill the thread with
    # rows about a setting, which is not what §6.7's "tråden tappar aldrig
    # en tur i tysthet" is about -- no turn was attempted. The human's own
    # message is still written and still stands in the thread.
    if settings.agent_runtime_enabled:
        ThreadTurnRunner().start(thread, posts[0], request.text)
    else:
        logger.info(
            "Agent runtime disabled -- message stored in thread %s, no turn "
            "started (AGENT_RUNTIME_ENABLED=false)",
            thread.id,
        )

    return ThreadMessageResponse(
        thread_id=thread.id,
        view_key=view_key,
        fiscal_year_id=thread.fiscal_year_id,
        posts=[_post_response(post) for post in posts],
        cursor=ThreadRepository.last_seq(thread.id),
    )


def _attachment_posts(
    thread: Thread, attachment_ids: list[str], actor: str
) -> list[ThreadPost]:
    """One `user_file` post per attachment (§6.1 step 2).

    An attachment is an intake source id -- the bytes were uploaded through
    `POST /api/v1/intake`, where they have a path, a hash and an audit
    trail. The post carries the file card's metadata and that reference,
    never the content (§6.2).

    An id that resolves to nothing is a `404`: a file post pointing at a
    source that does not exist would render as a card the human cannot open.
    """
    posts: list[ThreadPost] = []
    for source_id in attachment_ids:
        source = IntakeRepository.get_source(source_id)
        if source is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail={
                    "error": f"Unknown attachment: {source_id!r}",
                    "code": "attachment_not_found",
                    "details": (
                        "Attachments are intake source ids from " "POST /api/v1/intake"
                    ),
                },
            )
        posts.append(
            ThreadService.record_user_file(
                thread,
                filename=source.original_filename,
                size_bytes=source.size_bytes,
                intake_source_id=source.id,
                actor=actor,
            )
        )
    return posts


@router.get("/{view_key}/stream")
async def stream_thread(
    view_key: str,
    request: Request,
    since: Optional[int] = Query(
        None,
        description=(
            "Replay from this `seq` before going live: a reconnecting "
            "client gets what it missed and then the live events, with "
            "nothing duplicated."
        ),
    ),
    actor: str = Depends(get_current_actor),
):
    """`text/event-stream` for one view's thread (SPEC §6.5).

    Four event types: `message.created`, `message.delta`,
    `message.completed` and `view.changed`. `StreamingResponse` and one
    `asyncio.Queue` per subscriber -- no new dependency, no `sse-starlette`
    (§3).

    `?since=<cursor>` replays the stored posts after that `seq` as
    `message.completed` frames before the live feed begins. Those are the
    same payloads the live events carry, so a reconnecting client has one
    shape to handle rather than two, and the subscription is taken out
    *before* the replay is read -- an event that lands mid-replay is queued,
    not lost.
    """
    view_key = _validate_view_key(view_key)
    fiscal_year_id = _current_fiscal_year_id()
    thread = ThreadRepository.find(view_key, fiscal_year_id) if fiscal_year_id else None
    if thread is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={
                "error": f"No thread for view {view_key!r} in this fiscal year",
                "code": "thread_not_found",
                "details": "A thread is created by its first message.",
            },
        )

    broker = get_broker()
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    broker.subscribe(thread.id, queue, loop)

    # `since is not None`, not a truth test: `since=0` is a legitimate
    # cursor meaning "from the very beginning", and `seq` starts at 1.
    missed = (
        ThreadRepository.list_posts(thread.id, since=since) if since is not None else []
    )

    async def _events() -> AsyncIterator[str]:
        try:
            for post in missed:
                yield format_sse(EVENT_MESSAGE_COMPLETED, post_event_payload(post))
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # A comment frame, not an event: it keeps proxies and
                    # browsers from closing an idle connection, and a client
                    # parsing `event:`/`data:` ignores it by the spec.
                    yield ": keep-alive\n\n"
                    continue
                yield format_sse(event, data)
        finally:
            broker.unsubscribe(thread.id, queue)

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Nginx and friends buffer `text/event-stream` by default, which
            # turns every delta into a delivery that arrives with the last
            # one. There is no reverse proxy on hubbabubba today
            # (`deploy/hubbabubba/README.md`), so this is for whoever adds
            # one.
            "X-Accel-Buffering": "no",
        },
    )


def _model_capabilities(thread: Thread) -> ThreadModelResponse:
    """What this thread's model can and cannot do (§12.4).

    Read off the adapter's own `LLMCapabilities` rather than restated here,
    so a capability cannot drift between what the adapter does and what the
    interface promises. The limitations are spelled out in Swedish because
    they are shown to a person, not consumed by a switch statement.
    """
    info = get_model_info(thread.model)
    # The adapter imports are deferred, and each one is bound to its own
    # name: `services/llm/` is the only package allowed to import
    # `anthropic`/`openai` (SPEC-agentruntime §4), so importing at module
    # level here would drag both SDKs into every request that touches a
    # thread.
    if info.protocol == "messages":
        from services.llm.messages import MessagesClient

        capabilities = MessagesClient.capabilities
    else:
        from services.llm.chat import ChatClient

        capabilities = ChatClient.capabilities

    limitations: list[str] = []
    if not capabilities.pdf_document_blocks:
        limitations.append(
            "Kan inte läsa PDF-underlag direkt — bara underlag med ett "
            "textlager. Den avstår hellre än gissar."
        )
    if not capabilities.cache_breakpoint:
        limitations.append(
            "Ingen cache-ekonomi: varje tur betalar för hela systemprompten."
        )
    if not capabilities.streaming:
        limitations.append("Strömmar inte — svaret kommer i ett stycke.")

    return ThreadModelResponse(
        thread_id=thread.id,
        view_key=thread.view_key,
        model=thread.model,
        protocol=info.protocol,
        reads_pdf_documents=capabilities.pdf_document_blocks,
        has_cache_economy=capabilities.cache_breakpoint,
        streams=capabilities.streaming,
        limitations=limitations,
    )


@router.get("/{view_key}/model", response_model=ThreadModelResponse)
async def get_thread_model(
    view_key: str,
    actor: str = Depends(get_current_actor),
):
    """This thread's model, and what it can and cannot do (§12.4)."""
    thread = _require_thread(_validate_view_key(view_key))
    return _model_capabilities(thread)


@router.put("/{view_key}/model", response_model=ThreadModelResponse)
async def set_thread_model(
    view_key: str,
    request: ThreadModelRequest,
    actor: str = Depends(get_current_actor),
):
    """Change which model this thread talks to (§12.4).

    Takes effect from the next turn; the turns already run keep their own
    `agent_runs.model`, which is exactly what makes the switch visible
    afterwards. A model with no price row is refused here rather than at the
    first turn -- SPEC-agentruntime §2: "En modell utan prisrad är ett fel,
    inte ett standardvärde", and the honest moment to say so is when it is
    chosen.
    """
    thread = _require_thread(_validate_view_key(view_key))
    try:
        get_model_info(request.model)
    except UnknownModelError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={
                "error": str(exc),
                "code": "unknown_model",
                "details": "A model without a price row cannot be budgeted.",
            },
        )
    updated = ThreadRepository.set_model(thread.id, request.model)
    assert updated is not None  # the row was just read
    return _model_capabilities(updated)


def _require_thread(view_key: str) -> Thread:
    fiscal_year_id = _current_fiscal_year_id()
    thread = ThreadRepository.find(view_key, fiscal_year_id) if fiscal_year_id else None
    if thread is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={
                "error": f"No thread for view {view_key!r} in this fiscal year",
                "code": "thread_not_found",
                "details": "A thread is created by its first message.",
            },
        )
    return thread
