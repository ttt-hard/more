"""Turn 前置上下文服务。

`TurnContextService.prepare_preflight` 在 turn 开始阶段跑压缩策略 +
构造 resume_context；`build_turn_context` 进一步把 memory_context 和
resume_context 送进 `ContextPackingPolicy.pack` 做"按预算裁剪"，再把
结果合并回 `MemoryContext.thread_memory` 供 runtime / answer 消费。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..domain import MemoryContext, ResumeContext
from ..notes import NoteError
from ..observability import RunTrace
from ..workspace_fs import WorkspaceError, WorkspaceTextError
from .conversations import CompressionPolicyResult, ConversationCompressionService
from .context_packing import ContextPackingPolicy
from .memory import MemoryService


@dataclass(frozen=True)
class TurnPreflight:
    thread_summary: str
    token_budget: dict[str, object] | None
    resume_context: ResumeContext | None


@dataclass(frozen=True)
class PreparedTurnContext:
    memory_context: MemoryContext
    thread_summary: str
    token_budget: dict[str, object] | None


class TurnContextService:
    def __init__(
        self,
        compression_service: ConversationCompressionService,
        memory_service: MemoryService,
        context_packing_policy: ContextPackingPolicy | None = None,
    ) -> None:
        self.compression_service = compression_service
        self.memory_service = memory_service
        self.context_packing_policy = context_packing_policy or ContextPackingPolicy()

    def prepare_preflight(
        self,
        *,
        conversation_id: str,
        thread_summary: str = "",
        token_budget: dict[str, object] | None = None,
        run_trace: RunTrace | None = None,
    ) -> TurnPreflight:
        policy_result = self.compression_service.apply_policy(conversation_id, run_trace=run_trace)
        effective_thread_summary = thread_summary or policy_result.conversation.summary
        effective_token_budget = token_budget
        if effective_token_budget is None:
            effective_token_budget = dict(policy_result.budget)
        resume_context = self.compression_service.build_resume_context(conversation_id)
        if run_trace is not None and effective_token_budget is not None:
            run_trace.budget_snapshot = dict(effective_token_budget)
            run_trace.observe_metric("token_budget_utilization", float(effective_token_budget.get("utilization", 0.0)))
            run_trace.observe_metric("pending_token_count", int(effective_token_budget.get("pending_tokens", 0)))
            run_trace.set_metric("compression_state", str(policy_result.conversation.compression_state))
            run_trace.observe_metric("thread_resume_message_count", len(resume_context.recent_messages))
            run_trace.observe_metric("thread_checkpoint_count", len(resume_context.checkpoints))
        return TurnPreflight(
            thread_summary=effective_thread_summary,
            token_budget=effective_token_budget,
            resume_context=resume_context,
        )

    def refresh_post_turn(self, *, conversation_id: str, run_trace: RunTrace | None = None) -> CompressionPolicyResult:
        return self.compression_service.apply_policy(conversation_id, run_trace=run_trace)

    def build_memory_context(
        self,
        *,
        current_note_path: str | None,
        prompt: str,
        limit: int = 5,
    ) -> MemoryContext:
        return self.memory_service.build_context(
            current_note_path=current_note_path,
            query=prompt,
            limit=limit,
        )

    def build_turn_context(
        self,
        *,
        current_note_path: str | None,
        prompt: str,
        preflight: TurnPreflight,
        run_trace: RunTrace | None = None,
        limit: int = 5,
    ) -> PreparedTurnContext:
        packed_memory_context = self._pack_memory_context(
            current_note_path=current_note_path,
            prompt=prompt,
            limit=limit,
            preflight=preflight,
        )
        if run_trace is not None:
            run_trace.observe_metric("retrieval_hit_count", len(packed_memory_context.related_hits))
            run_trace.observe_metric(
                "packed_retrieval_evidence_count",
                len(packed_memory_context.thread_memory.get("retrieval_evidence") or []),
            )
            run_trace.observe_metric(
                "workspace_memory_ref_count",
                len(packed_memory_context.thread_memory.get("workspace_memory_refs") or []),
            )
            run_trace.observe_metric(
                "recent_turn_count",
                len(packed_memory_context.thread_memory.get("recent_turns") or []),
            )
            run_trace.observe_metric(
                "current_note_excerpt_chars",
                len(str(packed_memory_context.thread_memory.get("current_note_excerpt") or "")),
            )
            run_trace.set_metric("retrieval_used", len(packed_memory_context.related_hits) > 0)
        return PreparedTurnContext(
            memory_context=packed_memory_context,
            thread_summary=preflight.thread_summary,
            token_budget=preflight.token_budget,
        )

    def _pack_memory_context(
        self,
        *,
        current_note_path: str | None,
        prompt: str,
        limit: int,
        preflight: TurnPreflight,
    ) -> MemoryContext:
        memory_context = self.build_memory_context(
            current_note_path=current_note_path,
            prompt=prompt,
            limit=limit,
        )
        resume_context = preflight.resume_context
        if resume_context is None:
            raise RuntimeError("Turn preflight is missing resume context")
        note_document = None
        if current_note_path:
            try:
                note_document = self.memory_service.note_service.get_note(current_note_path)
            except (FileNotFoundError, NoteError, WorkspaceError, WorkspaceTextError, UnicodeDecodeError):
                note_document = None
        packed = self.context_packing_policy.pack(
            memory_context=memory_context,
            resume_context=resume_context,
            token_budget=preflight.token_budget,
            note_document=note_document,
        )
        thread_memory = dict(memory_context.thread_memory)
        thread_memory.update(
            {
                "thread_summary": packed.thread_summary,
                "recent_turns": packed.recent_turns,
                "retrieval_evidence": packed.retrieval_evidence,
                "workspace_memory_refs": packed.workspace_memory_refs,
                "current_note_excerpt": packed.current_note_excerpt,
                "context_allocation": packed.context_allocation,
                "checkpoints": packed.checkpoints,
            }
        )
        return replace(memory_context, thread_memory=thread_memory)


__all__ = ["PreparedTurnContext", "TurnContextService", "TurnPreflight"]
