"""Agent 调用请求 DTO。

`TurnRequest` 是一次用户 turn 的完整输入（conversation_id / prompt /
current_note_path / cancellation_token / thread_summary / ...）；
`RuntimeRequest` 是 coordinator 传给 runtime 的内部请求（已经带好
memory_context 和 preflight 信息）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..domain import MemoryContext
from ..observability import RunTrace
from ..runtime_control import CancellationToken, RunConfig
from .events import AgentEventBase


@dataclass(frozen=True)
class TurnRequest:
    conversation_id: str
    prompt: str
    current_note_path: str | None = None
    mode: str = "chat"
    thread_summary: str = ""
    token_budget: dict[str, object] | None = None
    run_config: RunConfig | None = None
    cancellation_token: CancellationToken | None = None
    run_trace: RunTrace | None = None


@dataclass(frozen=True)
class RuntimeRequest:
    prompt: str
    memory_context: MemoryContext
    current_note_path: str | None = None
    thread_summary: str = ""
    token_budget: dict[str, object] | None = None
    run_trace: RunTrace | None = None
    cancellation_token: CancellationToken | None = None
    run_config: RunConfig | None = None
    # When set, AgentRuntime invokes this callback synchronously on every
    # `emit(...)` from inside its planner/tool loop, BEFORE buffering the
    # event on the returned RuntimeOutcome. The coordinator uses this hook
    # to bridge the sync runtime onto a streaming SSE response: it runs the
    # runtime in a worker thread and pipes each event through a thread-safe
    # queue, so TokenEvents reach the browser at the actual LLM cadence
    # rather than at the end of the whole react loop.
    on_event: Callable[[AgentEventBase], None] | None = None


__all__ = ["RuntimeRequest", "TurnRequest"]
