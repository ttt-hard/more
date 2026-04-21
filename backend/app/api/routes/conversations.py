"""对话端点（含 SSE 流）。

涵盖对话增删改查、Resume 上下文、手动 compact / checkpoint、memory
candidate 的 accept / reject、以及核心的 `GET .../stream` SSE 流式
推理接口和 `POST .../cancel` 取消接口；所有业务走 coordinator。
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import queue
import threading
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from ...agent import SingleAgentCoordinator, TurnRequest
from ...agent.events import ErrorEvent, dump_agent_event
from ...runtime_control import CancellationToken
from ...runtime_registry import active_run_registry
from ..deps import get_agent_coordinator
from ..schemas import (
    ConversationCheckpointRequest,
    ConversationLabelsRequest,
    ConversationPinRequest,
    CreateConversationRequest,
    RenameConversationRequest,
)

router = APIRouter(prefix="/api/conversations")


@router.get("")
def list_conversations(
    include_archived: bool = Query(default=False),
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> dict[str, object]:
    conversations = coordinator.list_conversations(include_archived=include_archived)
    return {"conversations": [asdict(conversation) for conversation in conversations]}


@router.post("")
def create_conversation(
    request: CreateConversationRequest,
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> dict[str, object]:
    conversation = coordinator.create_conversation(title=request.title)
    return {"conversation": asdict(conversation)}


@router.get("/{conversation_id}/messages")
def list_conversation_messages(
    conversation_id: str,
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> dict[str, object]:
    messages = coordinator.list_messages(conversation_id)
    return {"messages": [asdict(message) for message in messages]}


@router.post("/{conversation_id}/rename")
def rename_conversation(
    conversation_id: str,
    request: RenameConversationRequest,
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> dict[str, object]:
    conversation = coordinator.rename_conversation(conversation_id, request.title)
    return {"conversation": asdict(conversation)}


@router.post("/{conversation_id}/archive")
def archive_conversation(
    conversation_id: str,
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> dict[str, object]:
    conversation = coordinator.archive_conversation(conversation_id)
    return {"conversation": asdict(conversation)}


@router.post("/{conversation_id}/resume")
def resume_conversation(
    conversation_id: str,
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> dict[str, object]:
    conversation = coordinator.resume_conversation(conversation_id)
    return {"conversation": asdict(conversation), "resume_context": asdict(coordinator.build_resume_context(conversation_id))}


@router.get("/{conversation_id}/summary")
def get_conversation_summary(
    conversation_id: str,
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> dict[str, object]:
    return {"summary": coordinator.get_conversation_summary(conversation_id)}


@router.get("/{conversation_id}/resume-context")
def get_conversation_resume_context(
    conversation_id: str,
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> dict[str, object]:
    return {"resume_context": asdict(coordinator.build_resume_context(conversation_id))}


@router.post("/{conversation_id}/compact")
def compact_conversation(
    conversation_id: str,
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> dict[str, object]:
    conversation = coordinator.compact_conversation(conversation_id)
    return {"conversation": asdict(conversation)}


@router.post("/{conversation_id}/checkpoint")
def checkpoint_conversation(
    conversation_id: str,
    request: ConversationCheckpointRequest,
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> dict[str, object]:
    checkpoint = coordinator.create_checkpoint(conversation_id, label=request.label)
    return {"checkpoint": asdict(checkpoint)}


@router.post("/{conversation_id}/pin")
def pin_conversation(
    conversation_id: str,
    request: ConversationPinRequest,
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> dict[str, object]:
    conversation = coordinator.set_conversation_pin(conversation_id, pinned=request.pinned)
    return {"conversation": asdict(conversation)}


@router.post("/{conversation_id}/labels")
def update_conversation_labels(
    conversation_id: str,
    request: ConversationLabelsRequest,
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> dict[str, object]:
    conversation = coordinator.update_conversation_labels(conversation_id, request.labels)
    return {"conversation": asdict(conversation)}


@router.get("/{conversation_id}/memory-candidates")
def list_memory_candidates(
    conversation_id: str,
    include_resolved: bool = Query(default=False),
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> dict[str, object]:
    candidates = coordinator.list_memory_candidates(conversation_id, include_resolved=include_resolved)
    return {"candidates": [asdict(candidate) for candidate in candidates]}


@router.post("/{conversation_id}/memory-candidates/{candidate_id}/accept")
def accept_memory_candidate(
    conversation_id: str,
    candidate_id: str,
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> dict[str, object]:
    candidate, record = coordinator.accept_memory_candidate(conversation_id, candidate_id)
    return {"candidate": asdict(candidate), "record": asdict(record)}


@router.post("/{conversation_id}/memory-candidates/{candidate_id}/reject")
def reject_memory_candidate(
    conversation_id: str,
    candidate_id: str,
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> dict[str, object]:
    candidate = coordinator.reject_memory_candidate(conversation_id, candidate_id)
    return {"candidate": asdict(candidate)}


@router.post("/{conversation_id}/cancel")
def cancel_conversation_stream(conversation_id: str) -> dict[str, object]:
    cancelled = active_run_registry.cancel(conversation_id, "Run cancelled by user")
    return {"cancelled": cancelled}


@router.get("/{conversation_id}/stream")
async def stream_conversation(
    conversation_id: str,
    prompt: str = Query(..., min_length=1),
    current_note_path: str | None = None,
    coordinator: SingleAgentCoordinator = Depends(get_agent_coordinator),
) -> StreamingResponse:
    """SSE endpoint pinning the agent turn's sync generator to ONE thread.

    Why a dedicated thread instead of the usual `def` endpoint + plain
    `StreamingResponse(sync_gen)` pattern:

    FastAPI's default plumbing for sync iterables is `iterate_in_threadpool`,
    which invokes `next(gen)` via `anyio.to_thread.run_sync` on every pull.
    That helper pulls an *arbitrary* worker out of the thread pool each
    call, so successive resumes of the same generator can land on
    *different* threads. Everything stored in `contextvars` (Langfuse /
    OpenTelemetry span stack, ...) is thread-local, so the span context
    opened by `@observe(conversation.turn)` on the first `next()` is
    silently lost when a later `next()` happens on a sibling thread.
    Visible symptoms we hit:
      - Langfuse Sessions view empty (sessionId never got stamped because
        `update_current_trace` couldn't find the active span).
      - Every nested `@observe` (memory.build_context, agent.run, ...)
        showed up as its own root trace instead of children of the turn.

    Fix: iterate the sync generator on a single, stable background thread
    and bridge each yielded item back to the async consumer via a
    thread-safe `queue.Queue`. `contextvars.copy_context().run(...)` on
    that thread seeds it with the caller's context so OTEL / Langfuse
    start in the right state.
    """

    cancellation_token = CancellationToken()
    active_run_registry.register(conversation_id, cancellation_token)
    request = TurnRequest(
        conversation_id=conversation_id,
        prompt=prompt,
        current_note_path=current_note_path,
        cancellation_token=cancellation_token,
    )

    # `queue.Queue` rather than `asyncio.Queue` because the producer is a
    # plain thread; the consumer side bridges via `run_in_executor` for
    # each `get()`. An unbounded queue is fine here: each agent turn
    # emits O(100) events max, and back-pressure is implicitly applied
    # by the consumer's HTTP write cadence.
    bridge_q: queue.Queue = queue.Queue()
    done_sentinel: object = object()

    def producer() -> None:
        try:
            for event in coordinator.run_stream(request):
                bridge_q.put(
                    f"data: {json.dumps(dump_agent_event(event), ensure_ascii=False)}\n\n"
                )
        except Exception as error:  # noqa: BLE001
            bridge_q.put(
                f"data: {json.dumps(dump_agent_event(ErrorEvent(detail=str(error))), ensure_ascii=False)}\n\n"
            )
        finally:
            bridge_q.put("data: [DONE]\n\n")
            bridge_q.put(done_sentinel)

    # Seed the worker with a copy of OUR context so any contextvar the
    # request handler has set up (future: request IDs, tenant, ...) is
    # visible to the sync generator. The sync generator itself then runs
    # its full lifetime on this single thread — no hopping.
    producer_ctx = contextvars.copy_context()
    producer_thread = threading.Thread(
        target=lambda: producer_ctx.run(producer),
        name=f"sse-turn-{conversation_id[:8]}",
        daemon=True,
    )
    producer_thread.start()

    async def bridge() -> object:
        loop = asyncio.get_running_loop()
        try:
            while True:
                # Blocking `queue.get()` off the event loop so we don't
                # freeze other requests while waiting for the next event.
                item = await loop.run_in_executor(None, bridge_q.get)
                if item is done_sentinel:
                    break
                yield item
        finally:
            active_run_registry.unregister(conversation_id, cancellation_token)
            # Cooperative shutdown: if the client disconnected mid-stream
            # the producer may still be blocked on its next yield. The
            # cancellation token was already signalled by the SSE close
            # path; joining with a short timeout prevents zombie threads.
            producer_thread.join(timeout=5.0)

    return StreamingResponse(bridge(), media_type="text/event-stream")
