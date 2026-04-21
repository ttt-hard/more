"""记忆候选存储。

`MemoryCandidateStore` 把 `MemoryExtractionService` 提取出的
`MemoryCandidate` 按对话维度归档：每个对话一个文件
`.more/memory/candidates/<conversation_id>.json`（内部是一个 JSON 数组），
直到用户在前端 accept（转正式记忆）或 reject（丢弃）。状态机：
pending → accepted / rejected。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..domain import MemoryCandidate
from ..infrastructure.file_lock import locked_path
from ..workspace_fs import WorkspaceFS


class MemoryCandidateStore:
    def __init__(self, fs: WorkspaceFS) -> None:
        self.fs = fs
        self.memory_root = self.fs.sidecar_root / "memory" / "candidates"
        self.memory_root.mkdir(parents=True, exist_ok=True)

    def list_candidates(self, conversation_id: str, *, include_resolved: bool = False) -> list[MemoryCandidate]:
        candidates = [self._coerce_candidate(payload) for payload in self._read_candidates(conversation_id)]
        if not include_resolved:
            candidates = [candidate for candidate in candidates if candidate.status == "pending"]
        candidates.sort(key=lambda candidate: candidate.created_at, reverse=True)
        return candidates

    def create_candidates(self, conversation_id: str, candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
        path = self._path(conversation_id)
        with locked_path(path):
            existing = self._read_candidates(conversation_id)
            existing_keys = {
                (
                    str(payload.get("kind") or ""),
                    str(payload.get("value") or "").strip().casefold(),
                    str(payload.get("source_message_id") or ""),
                )
                for payload in existing
            }
            created: list[MemoryCandidate] = []
            for candidate in candidates:
                key = (candidate.kind, candidate.value.strip().casefold(), candidate.source_message_id)
                if key in existing_keys:
                    continue
                existing.append(asdict(candidate))
                existing_keys.add(key)
                created.append(candidate)
            self._write_candidates(conversation_id, existing)
        return created

    def update_candidate_status(
        self,
        conversation_id: str,
        candidate_id: str,
        *,
        status: str,
    ) -> MemoryCandidate:
        path = self._path(conversation_id)
        with locked_path(path):
            raw_candidates = self._read_candidates(conversation_id)
            updated_candidate: MemoryCandidate | None = None
            for index, payload in enumerate(raw_candidates):
                if str(payload.get("id") or "") != candidate_id:
                    continue
                payload = dict(payload)
                payload["status"] = status
                raw_candidates[index] = payload
                updated_candidate = self._coerce_candidate(payload)
                break
            if updated_candidate is None:
                raise FileNotFoundError(f"Memory candidate not found: {candidate_id}")
            self._write_candidates(conversation_id, raw_candidates)
        return updated_candidate

    def _path(self, conversation_id: str) -> Path:
        return self.memory_root / f"{conversation_id}.json"

    def _read_candidates(self, conversation_id: str) -> list[dict[str, object]]:
        path = self._path(conversation_id)
        if not path.exists():
            return []
        with locked_path(path):
            raw = json.loads(path.read_text(encoding="utf-8") or "[]")
        if not isinstance(raw, list):
            raise ValueError("memory candidate payload must be a list")
        return [payload for payload in raw if isinstance(payload, dict)]

    def _write_candidates(self, conversation_id: str, candidates: list[dict[str, object]]) -> None:
        path = self._path(conversation_id)
        with locked_path(path):
            path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")

    def _coerce_candidate(self, payload: dict[str, object]) -> MemoryCandidate:
        return MemoryCandidate(
            id=str(payload["id"]),
            kind=str(payload.get("kind") or "fact"),
            value=str(payload.get("value") or ""),
            confidence=float(payload.get("confidence") or 0.0),
            source_thread_id=str(payload.get("source_thread_id") or ""),
            source_message_id=str(payload.get("source_message_id") or ""),
            created_at=str(payload.get("created_at") or ""),
            status=str(payload.get("status") or "pending"),
        )


__all__ = ["MemoryCandidateStore"]
