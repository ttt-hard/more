"""会话压缩服务。

`ConversationCompressionService` 维护对话摘要与压缩 state：
`apply_policy` 看 `TokenBudgetManager` 的 state 决定是否触发
`summarize`（重写 `conversation.summary`），`build_resume_context` 打包
恢复视图供前端 resume。`create_checkpoint` 写历史快照。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..domain import Conversation, Message, ResumeContext, utc_now_iso
from ..notes import NoteError, NoteService
from ..observability import RunTrace
from ..stores import ConversationCheckpointStorePort, ConversationStorePort, WorkspaceMemoryStorePort
from ..workspace_fs import WorkspaceError, WorkspaceTextError
from .token_budget import TokenBudgetManager


@dataclass(frozen=True)
class CompressionPolicyResult:
    conversation: Conversation
    budget: dict[str, object]
    compacted: bool


@dataclass(frozen=True)
class CompressionSummaryInput:
    messages: list[Message]


class ConversationSummaryStrategy:
    def __init__(self, *, message_limit: int = 8, preview_length: int = 120) -> None:
        self.message_limit = message_limit
        self.preview_length = preview_length

    def build_summary(self, summary_input: CompressionSummaryInput) -> str:
        if not summary_input.messages:
            return ""
        relevant_messages = summary_input.messages[-self.message_limit :]
        lines = []
        for message in relevant_messages:
            role = "User" if message.role == "user" else "Assistant"
            content = " ".join(message.content.split())
            if len(content) > self.preview_length:
                content = f"{content[: self.preview_length - 3]}..."
            if content:
                lines.append(f"- {role}: {content}")
        return "\n".join(lines)


class ConversationCompressionService:
    def __init__(
        self,
        conversation_store: ConversationStorePort,
        *,
        warning_threshold: int = 1200,
        compact_threshold: int = 1800,
        force_threshold: int = 2400,
        summary_message_limit: int = 8,
        summary_strategy: ConversationSummaryStrategy | None = None,
        note_service: NoteService | None = None,
        workspace_memory_store: WorkspaceMemoryStorePort | None = None,
        checkpoint_store: ConversationCheckpointStorePort | None = None,
    ) -> None:
        self.conversation_store = conversation_store
        self.budget_manager = TokenBudgetManager(
            warning_threshold=warning_threshold,
            compact_threshold=compact_threshold,
            force_threshold=force_threshold,
        )
        self.summary_strategy = summary_strategy or ConversationSummaryStrategy(message_limit=summary_message_limit)
        self.note_service = note_service
        self.workspace_memory_store = workspace_memory_store
        self.checkpoint_store = checkpoint_store

    def summarize(self, conversation_id: str, *, run_trace: RunTrace | None = None) -> Conversation:
        updated = self.refresh_summary(conversation_id)
        updated = self.conversation_store.update_context(
            conversation_id,
            compacted_token_estimate=updated.token_estimate,
            compression_state="ok",
            compression_count=updated.compression_count + 1,
            last_compacted_at=utc_now_iso(),
        )
        if run_trace is not None:
            run_trace.increment_metric("compression_count")
            run_trace.set_metric("compression_state", "ok")
            run_trace.observe_metric("thread_summary_chars", len(updated.summary))
        return updated

    def apply_policy(self, conversation_id: str, *, run_trace: RunTrace | None = None) -> CompressionPolicyResult:
        conversation = self.conversation_store.get_conversation(conversation_id)
        budget = self.budget_manager.snapshot(conversation)
        if run_trace is not None:
            run_trace.observe_metric("token_budget_utilization", budget.utilization)
            run_trace.observe_metric("pending_token_count", budget.pending_tokens)
            run_trace.set_metric("compression_state", budget.state)
            run_trace.observe_metric("compression_trigger_correctness", 1)
        if budget.should_compact:
            compacted_conversation = self.summarize(conversation_id, run_trace=run_trace)
            if run_trace is not None:
                run_trace.increment_metric("compression_trigger_count")
            return self._build_policy_result(compacted_conversation, compacted=True)
        refreshed = self.refresh_summary(conversation_id)
        if refreshed.compression_state != budget.state:
            refreshed = self.conversation_store.update_context(
                conversation_id,
                compression_state=budget.state,
            )
        return self._build_policy_result(refreshed, compacted=False)

    def maybe_compact(self, conversation_id: str, *, run_trace: RunTrace | None = None) -> Conversation:
        return self.apply_policy(conversation_id, run_trace=run_trace).conversation

    def refresh_summary(self, conversation_id: str) -> Conversation:
        conversation = self.conversation_store.get_conversation(conversation_id)
        messages = self.conversation_store.list_messages(conversation_id)
        summary = self.summary_strategy.build_summary(CompressionSummaryInput(messages=messages))
        if summary == conversation.summary:
            return conversation
        return self.conversation_store.update_context(conversation_id, summary=summary)

    def conversation_status(self, conversation_id: str) -> dict[str, object]:
        conversation = self.conversation_store.get_conversation(conversation_id)
        active_note = None
        if self.note_service is not None and conversation.active_note_path:
            try:
                active_note = asdict(self.note_service.get_note(conversation.active_note_path).meta)
            except (FileNotFoundError, NoteError, WorkspaceError, WorkspaceTextError, UnicodeDecodeError):
                active_note = None
        workspace_memory_refs = []
        if self.workspace_memory_store is not None:
            workspace_memory_refs = [asdict(record) for record in self.workspace_memory_store.search_records(conversation.summary)]
        return {
            "conversation": asdict(conversation),
            "budget": self.budget_manager.dump_snapshot(conversation),
            "summary_state": conversation.compression_state,
            "active_note": active_note,
            "workspace_memory_refs": workspace_memory_refs,
        }

    def create_checkpoint(self, conversation_id: str, *, label: str | None = None):
        if self.checkpoint_store is None:
            raise RuntimeError("Checkpoint store is not configured")
        conversation = self.conversation_store.get_conversation(conversation_id)
        return self.checkpoint_store.create_checkpoint(
            conversation_id=conversation_id,
            label=label or conversation.title,
            summary=conversation.summary,
            token_estimate=conversation.token_estimate,
            active_note_path=conversation.active_note_path,
        )

    def build_resume_context(self, conversation_id: str, *, message_limit: int = 8) -> ResumeContext:
        conversation = self.refresh_summary(conversation_id)
        recent_messages = self.conversation_store.list_messages(conversation_id)[-message_limit:]
        active_note = None
        if self.note_service is not None and conversation.active_note_path:
            try:
                active_note = self.note_service.get_note(conversation.active_note_path).meta
            except (FileNotFoundError, NoteError, WorkspaceError, WorkspaceTextError, UnicodeDecodeError):
                active_note = None
        workspace_memory_refs = []
        if self.workspace_memory_store is not None:
            workspace_memory_refs = self.workspace_memory_store.search_records(conversation.summary)
        checkpoints = []
        if self.checkpoint_store is not None:
            checkpoints = self.checkpoint_store.list_checkpoints(conversation_id)
        return ResumeContext(
            conversation=conversation,
            budget=self.budget_manager.dump_snapshot(conversation),
            recent_messages=recent_messages,
            active_note=active_note,
            workspace_memory_refs=workspace_memory_refs,
            checkpoints=checkpoints,
        )

    def _build_policy_result(self, conversation: Conversation, *, compacted: bool) -> CompressionPolicyResult:
        return CompressionPolicyResult(
            conversation=conversation,
            budget=self.budget_manager.dump_snapshot(conversation),
            compacted=compacted,
        )


__all__ = [
    "CompressionPolicyResult",
    "CompressionSummaryInput",
    "ConversationCompressionService",
    "ConversationSummaryStrategy",
]
