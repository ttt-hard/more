"""上下文打包策略。

`ContextPackingPolicy.pack` 根据当前压缩 state（ok / warning / compact /
force）裁剪：最近 turn 数、retrieval 条数、workspace_memory 条数、note 摘录
字符上限都有相应阈值。产出的 `ContextPack` 供 turn_context 注入 agent。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain import MemoryContext, NoteMeta, ResumeContext, SearchHit, WorkspaceMemoryRecord
from ..notes import NoteDocument


@dataclass(frozen=True)
class ContextPack:
    thread_summary: str
    recent_turns: list[dict[str, object]]
    retrieval_evidence: list[dict[str, object]]
    workspace_memory_refs: list[dict[str, object]]
    current_note_excerpt: str
    context_allocation: dict[str, object]
    checkpoints: list[dict[str, object]]


class ContextPackingPolicy:
    def __init__(
        self,
        *,
        max_recent_turns: int = 6,
        max_retrieval_hits: int = 6,
        max_workspace_refs: int = 4,
        note_excerpt_length: int = 900,
    ) -> None:
        self.max_recent_turns = max_recent_turns
        self.max_retrieval_hits = max_retrieval_hits
        self.max_workspace_refs = max_workspace_refs
        self.note_excerpt_length = note_excerpt_length

    def pack(
        self,
        *,
        memory_context: MemoryContext,
        resume_context: ResumeContext,
        token_budget: dict[str, object] | None,
        note_document: NoteDocument | None,
    ) -> ContextPack:
        budget_state = str((token_budget or {}).get("state") or "ok")
        turn_limit, retrieval_limit, workspace_limit, excerpt_length = self._limits_for_state(budget_state)
        return ContextPack(
            thread_summary=resume_context.conversation.summary.strip(),
            recent_turns=self._recent_turns(resume_context, limit=turn_limit),
            retrieval_evidence=self._retrieval_evidence(memory_context.related_hits, limit=retrieval_limit),
            workspace_memory_refs=self._workspace_memory_refs(
                memory_context.workspace_memory or resume_context.workspace_memory_refs,
                limit=workspace_limit,
            ),
            current_note_excerpt=self._current_note_excerpt(
                memory_context.current_note,
                note_document,
                limit=excerpt_length,
            ),
            context_allocation=self._allocation_for_state(budget_state),
            checkpoints=self._checkpoints(resume_context, limit=3),
        )

    def _limits_for_state(self, state: str) -> tuple[int, int, int, int]:
        if state == "force":
            return 2, 4, 2, 450
        if state == "compact":
            return 3, 4, 2, 600
        if state == "warning":
            return 4, 5, 3, 750
        return self.max_recent_turns, self.max_retrieval_hits, self.max_workspace_refs, self.note_excerpt_length

    def _allocation_for_state(self, state: str) -> dict[str, object]:
        return {
            "state": state,
            "system_and_tools_pct": 15,
            "thread_summary_pct": 20,
            "recent_turns_pct": 20,
            "retrieval_evidence_pct": 35,
            "current_note_excerpt_pct": 10,
        }

    def _recent_turns(self, resume_context: ResumeContext, *, limit: int) -> list[dict[str, object]]:
        turns = []
        for message in resume_context.recent_messages[-limit:]:
            turns.append(
                {
                    "role": message.role,
                    "content": message.content[:320],
                    "citations": message.citations[:4],
                    "tool_calls": message.tool_calls[:4],
                    "created_at": message.created_at,
                }
            )
        return turns

    def _retrieval_evidence(self, hits: list[SearchHit], *, limit: int) -> list[dict[str, object]]:
        return [
            {
                "path": hit.path,
                "title": hit.title,
                "snippet": hit.snippet[:280],
                "kind": hit.kind,
                "score": hit.score,
                "chunk_id": hit.chunk_id,
                "section": hit.section,
                "token_count": hit.token_count,
                "start_offset": hit.start_offset,
            }
            for hit in hits[:limit]
        ]

    def _workspace_memory_refs(
        self,
        refs: list[WorkspaceMemoryRecord],
        *,
        limit: int,
    ) -> list[dict[str, object]]:
        return [
            {
                "id": record.id,
                "kind": record.kind,
                "value": record.value,
                "confidence": record.confidence,
                "updated_at": record.updated_at,
            }
            for record in refs[:limit]
        ]

    def _current_note_excerpt(
        self,
        note_meta: NoteMeta | None,
        note_document: NoteDocument | None,
        *,
        limit: int,
    ) -> str:
        if note_meta is None or note_document is None:
            return ""
        content = " ".join(note_document.content.split())
        return content[:limit]

    def _checkpoints(self, resume_context: ResumeContext, *, limit: int) -> list[dict[str, object]]:
        return [
            {
                "id": checkpoint.id,
                "label": checkpoint.label,
                "summary": checkpoint.summary[:220],
                "active_note_path": checkpoint.active_note_path,
                "created_at": checkpoint.created_at,
            }
            for checkpoint in resume_context.checkpoints[:limit]
        ]


__all__ = ["ContextPack", "ContextPackingPolicy"]
