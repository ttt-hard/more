"""Turn 状态机。

`TurnStateService.begin_turn` 为一轮对话创建 Task + Run 并落库；
`finalize_turn` 把 assistant message 附上 token_estimate / citations /
tool_calls / reasoning 写回 `ConversationStore` 并把 task 置为 completed。
所有 task / run 状态迁移统一收敛在这里。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from ..domain import AgentRun, Message, Task, utc_now_iso
from ..observability import RunTrace
from ..runtime_control import RunConfig
from ..stores import ConversationStorePort, TaskStorePort


@dataclass(frozen=True)
class TurnState:
    task: Task
    run: AgentRun
    trace: RunTrace


@dataclass(frozen=True)
class CompletedTurn:
    message: Message
    task: Task
    run: AgentRun


@dataclass(frozen=True)
class CancelledTurn:
    task: Task
    run: AgentRun


@dataclass(frozen=True)
class FailedTurn:
    task: Task
    run: AgentRun


class TurnStateService:
    def __init__(
        self,
        conversation_store: ConversationStorePort,
        task_store: TaskStorePort,
    ) -> None:
        self.conversation_store = conversation_store
        self.task_store = task_store

    def begin_turn(
        self,
        *,
        conversation_id: str,
        prompt: str,
        current_note_path: str | None,
        mode: str,
        run_config: RunConfig,
        run_trace: RunTrace | None = None,
        token_budget: dict[str, object] | None = None,
    ) -> TurnState:
        prompt_text = prompt.strip()
        self.conversation_store.get_conversation(conversation_id)
        self.conversation_store.update_context(
            conversation_id,
            active_note_path=current_note_path,
        )
        self.conversation_store.append_message(
            conversation_id,
            Message(
                id=uuid4().hex[:12],
                role="user",
                content=prompt_text,
                created_at=utc_now_iso(),
            ),
        )
        task = self.task_store.create_task(kind="conversation_turn")
        task = self.task_store.update_task_state(task.id, "running")
        run = self.task_store.create_run(task.id, mode=mode)
        active_trace = run_trace or RunTrace(run_id=run.id, conversation_id=conversation_id, config=run_config)
        active_trace.run_id = run.id
        active_trace.conversation_id = conversation_id
        active_trace.config = run_config
        if token_budget is not None:
            active_trace.budget_snapshot = dict(token_budget)
        return TurnState(task=task, run=run, trace=active_trace)

    def complete_turn(
        self,
        *,
        conversation_id: str,
        task_id: str,
        run_id: str,
        answer: str,
        citations: list[str],
        tool_calls: list[str],
        task_state: str,
        run_status: str,
        reasoning: str = "",
    ) -> CompletedTurn:
        message = Message(
            id=uuid4().hex[:12],
            role="assistant",
            content=answer,
            citations=citations,
            tool_calls=tool_calls,
            created_at=utc_now_iso(),
            reasoning=reasoning,
        )
        self.conversation_store.append_message(conversation_id, message)
        task = self.task_store.update_task_state(task_id, task_state)
        run = self.task_store.update_run_status(run_id, run_status)
        return CompletedTurn(message=message, task=task, run=run)

    def cancel_turn(self, *, task_id: str, run_id: str) -> CancelledTurn:
        task = self.task_store.update_task_state(task_id, "cancelled")
        run = self.task_store.update_run_status(run_id, "cancelled")
        return CancelledTurn(task=task, run=run)

    def fail_turn(self, *, task_id: str, run_id: str) -> FailedTurn:
        task = self.task_store.update_task_state(task_id, "failed")
        run = self.task_store.update_run_status(run_id, "failed")
        return FailedTurn(task=task, run=run)


__all__ = ["CancelledTurn", "CompletedTurn", "FailedTurn", "TurnState", "TurnStateService"]
