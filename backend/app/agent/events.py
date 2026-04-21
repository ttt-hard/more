"""Agent SSE 事件模型。

定义所有会通过 Server-Sent Events 推给前端的事件 Pydantic 模型
（TaskStatus / MessageStart / Token / ReasoningDelta / ToolStarted /
ApprovalRequired / Done ...），用 discriminator `type` 字符串区分。
`coerce_agent_event` 把 dict 或实例归一化为 `AgentEventBase`。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class AgentEventBase(BaseModel):
    type: str

    model_config = {"extra": "allow"}


class TaskStatusEvent(AgentEventBase):
    type: Literal["task_status"] = "task_status"
    task: dict[str, Any]
    run: dict[str, Any]


class MessageStartEvent(AgentEventBase):
    type: Literal["message_start"] = "message_start"
    conversation_id: str


class TokenEvent(AgentEventBase):
    type: Literal["token"] = "token"
    text: str


class StreamRollbackEvent(AgentEventBase):
    """Tell the frontend to undo the last `len(text)` characters it appended
    to the in-progress assistant bubble via `token` events. Emitted by the
    runtime when, after streaming content deltas live for real-time UX, the
    PlanDone reveals this was a middle turn (tool_call) rather than the
    final respond: the narrative that already flowed into the bubble
    actually belongs in the thinking panel. The runtime follows this event
    with `reasoning_delta`s carrying the same text so the content moves
    cleanly from bubble to thinking without data loss."""

    type: Literal["stream_rollback"] = "stream_rollback"
    text: str


class ReasoningDeltaEvent(AgentEventBase):
    type: Literal["reasoning_delta"] = "reasoning_delta"
    text: str


class ReasoningStepEvent(AgentEventBase):
    type: Literal["reasoning_step"] = "reasoning_step"
    kind: Literal["phase", "tool", "retrieval", "fallback", "retry", "recovered", "error"]
    status: Literal["active", "done", "error"]
    title: str
    detail: str | None = None


class PhaseStatusEvent(AgentEventBase):
    type: Literal["phase_status"] = "phase_status"
    phase: Literal["planning", "tool", "answering"]
    label: str
    detail: str | None = None


class RetrievalHitsEvent(AgentEventBase):
    type: Literal["retrieval_hits"] = "retrieval_hits"
    hits: list[dict[str, Any]]


class ToolStartedEvent(AgentEventBase):
    type: Literal["tool_started"] = "tool_started"
    tool: str
    target: str | None = None
    query: str | None = None


class ToolFinishedEvent(AgentEventBase):
    type: Literal["tool_finished"] = "tool_finished"
    tool: str
    target: str | None = None
    query: str | None = None


class ToolFailedEvent(AgentEventBase):
    type: Literal["tool_failed"] = "tool_failed"
    tool: str
    detail: str
    step: int | None = None
    attempt: int | None = None


class RetryingEvent(AgentEventBase):
    type: Literal["retrying"] = "retrying"
    stage: str
    attempt: int
    detail: str | None = None


class RecoveredEvent(AgentEventBase):
    type: Literal["recovered"] = "recovered"
    stage: str
    attempt: int


class FallbackUsedEvent(AgentEventBase):
    type: Literal["fallback_used"] = "fallback_used"
    planner: str
    reason: str


class ApprovalRequiredEvent(AgentEventBase):
    type: Literal["approval_required"] = "approval_required"
    approval: dict[str, Any]


class NoteCreatedEvent(AgentEventBase):
    type: Literal["note_created"] = "note_created"
    note: dict[str, Any]


class NoteUpdatedEvent(AgentEventBase):
    type: Literal["note_updated"] = "note_updated"
    note: dict[str, Any]


class FileWrittenEvent(AgentEventBase):
    type: Literal["file_written"] = "file_written"
    path: str


class MessageDoneEvent(AgentEventBase):
    type: Literal["message_done"] = "message_done"
    message: dict[str, Any]


class ErrorEvent(AgentEventBase):
    type: Literal["error"] = "error"
    detail: str


class DoneEvent(AgentEventBase):
    type: Literal["done"] = "done"
    conversation_id: str


_EVENT_CLASSES: dict[str, type[AgentEventBase]] = {
    "task_status": TaskStatusEvent,
    "message_start": MessageStartEvent,
    "token": TokenEvent,
    "stream_rollback": StreamRollbackEvent,
    "reasoning_delta": ReasoningDeltaEvent,
    "reasoning_step": ReasoningStepEvent,
    "phase_status": PhaseStatusEvent,
    "retrieval_hits": RetrievalHitsEvent,
    "tool_started": ToolStartedEvent,
    "tool_finished": ToolFinishedEvent,
    "tool_failed": ToolFailedEvent,
    "retrying": RetryingEvent,
    "recovered": RecoveredEvent,
    "fallback_used": FallbackUsedEvent,
    "approval_required": ApprovalRequiredEvent,
    "note_created": NoteCreatedEvent,
    "note_updated": NoteUpdatedEvent,
    "file_written": FileWrittenEvent,
    "message_done": MessageDoneEvent,
    "error": ErrorEvent,
    "done": DoneEvent,
}


def coerce_agent_event(payload: AgentEventBase | dict[str, Any]) -> AgentEventBase:
    if isinstance(payload, AgentEventBase):
        return payload
    event_type = payload.get("type")
    event_class = _EVENT_CLASSES.get(event_type) if isinstance(event_type, str) else None
    if event_class is None:
        raise ValueError(f"Unsupported agent event type: {event_type}")
    return event_class.model_validate(payload)


def dump_agent_event(payload: AgentEventBase | dict[str, Any]) -> dict[str, Any]:
    return coerce_agent_event(payload).model_dump(mode="json")
