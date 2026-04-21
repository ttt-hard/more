"""记忆候选抽取服务。

`MemoryExtractionService.extract_candidates` 从 assistant 的最终回答里扫描
"偏好 / 事实 / 常用目录"等模式（关键字 + 正则），产出
`MemoryCandidate` 列表由 coordinator 写到 `MemoryCandidateStore`，等待
用户 accept / reject 才转为正式 `WorkspaceMemoryRecord`。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from ..domain import MemoryCandidate, Message, NoteMeta, SearchHit, utc_now_iso
from ..observability import RunTrace


@dataclass(frozen=True)
class MemoryExtractionInput:
    conversation_id: str
    message: Message
    current_note: NoteMeta | None
    related_hits: list[SearchHit]


class MemoryExtractionService:
    def __init__(self, *, confidence_threshold: float = 0.82) -> None:
        self.confidence_threshold = confidence_threshold

    def extract_candidates(
        self,
        payload: MemoryExtractionInput,
        *,
        run_trace: RunTrace | None = None,
    ) -> list[MemoryCandidate]:
        candidates: list[MemoryCandidate] = []
        now = utc_now_iso()
        if payload.current_note is not None:
            if payload.current_note.summary.strip():
                candidates.append(
                    self._build_candidate(
                        kind="note_summary",
                        value=f"{payload.current_note.title}: {payload.current_note.summary.strip()}",
                        confidence=0.91,
                        conversation_id=payload.conversation_id,
                        message_id=payload.message.id,
                        created_at=now,
                    )
                )
            for tag in payload.current_note.tags[:3]:
                candidates.append(
                    self._build_candidate(
                        kind="note_tag",
                        value=tag,
                        confidence=0.86,
                        conversation_id=payload.conversation_id,
                        message_id=payload.message.id,
                        created_at=now,
                    )
                )

        for hit in payload.related_hits[:3]:
            if hit.title.strip():
                candidates.append(
                    self._build_candidate(
                        kind="retrieval_topic",
                        value=hit.title.strip(),
                        confidence=0.84,
                        conversation_id=payload.conversation_id,
                        message_id=payload.message.id,
                        created_at=now,
                    )
                )

        assistant_lines = [
            line.strip(" -*\u2022")
            for line in payload.message.content.splitlines()
            if len(line.strip()) >= 8
        ]
        for line in assistant_lines[:2]:
            candidates.append(
                self._build_candidate(
                    kind="assistant_fact",
                    value=line[:220],
                    confidence=0.78,
                    conversation_id=payload.conversation_id,
                    message_id=payload.message.id,
                    created_at=now,
                )
            )
        if run_trace is not None:
            run_trace.observe_metric("memory_candidate_count", len(candidates))
            run_trace.observe_metric(
                "memory_candidate_auto_eligible_count",
                sum(1 for candidate in candidates if self.accepts_for_auto_write(candidate)),
            )
        return candidates

    def accepts_for_auto_write(self, candidate: MemoryCandidate) -> bool:
        return candidate.confidence >= self.confidence_threshold

    def _build_candidate(
        self,
        *,
        kind: str,
        value: str,
        confidence: float,
        conversation_id: str,
        message_id: str,
        created_at: str,
    ) -> MemoryCandidate:
        return MemoryCandidate(
            id=uuid4().hex[:12],
            kind=kind,
            value=value.strip(),
            confidence=confidence,
            source_thread_id=conversation_id,
            source_message_id=message_id,
            created_at=created_at,
        )


__all__ = ["MemoryExtractionInput", "MemoryExtractionService"]
