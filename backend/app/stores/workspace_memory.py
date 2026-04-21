"""工作区记忆存储。

`WorkspaceMemoryStore` 把已被用户接受的 `WorkspaceMemoryRecord`（kind /
key / value / tags / updated_at / source）集中存在
`.more/memory/workspace_memory.json` 这一个 JSON 数组里。`list_records`
按 updated_at 降序返回；`search_records` 按关键字做轻量 lexical 过滤
再统一降序（避免早前按字符串升序导致"越旧越靠前"的 bug）。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..domain import WorkspaceMemoryRecord
from ..infrastructure.file_lock import locked_path
from ..workspace_fs import WorkspaceFS


class WorkspaceMemoryStore:
    def __init__(self, fs: WorkspaceFS) -> None:
        self.fs = fs
        self.memory_root = self.fs.sidecar_root / "memory"
        self.memory_root.mkdir(parents=True, exist_ok=True)
        self.records_path = self.memory_root / "workspace_memory.json"

    def list_records(self, *, include_inactive: bool = False) -> list[WorkspaceMemoryRecord]:
        records = [self._coerce_record(payload) for payload in self._read_records()]
        if not include_inactive:
            records = [record for record in records if record.status == "active"]
        records.sort(key=lambda record: (record.updated_at, record.created_at), reverse=True)
        return records

    def upsert_record(self, record: WorkspaceMemoryRecord) -> WorkspaceMemoryRecord:
        with locked_path(self.records_path):
            records = self._read_records()
            updated = False
            for index, payload in enumerate(records):
                if str(payload.get("id") or "") == record.id:
                    records[index] = asdict(record)
                    updated = True
                    break
            if not updated:
                records.append(asdict(record))
            self._write_records(records)
        return record

    def search_records(self, query: str, *, limit: int = 5) -> list[WorkspaceMemoryRecord]:
        normalized_terms = {term.casefold() for term in query.split() if term.strip()}
        if not normalized_terms:
            return self.list_records()[:limit]

        scored: list[tuple[int, WorkspaceMemoryRecord]] = []
        for record in self.list_records():
            haystack = f"{record.kind} {record.value}".casefold()
            score = sum(1 for term in normalized_terms if term in haystack)
            if score <= 0:
                continue
            scored.append((score, record))
        # All three keys should sort descending: higher score first, higher confidence
        # first, then most recently updated first. The ISO-8601 ``updated_at`` string is
        # lexicographically monotonic, so ``reverse=True`` on the plain tuple is correct.
        scored.sort(key=lambda item: (item[0], item[1].confidence, item[1].updated_at), reverse=True)
        return [record for _, record in scored[:limit]]

    def _read_records(self) -> list[dict[str, object]]:
        if not self.records_path.exists():
            return []
        with locked_path(self.records_path):
            raw = json.loads(self.records_path.read_text(encoding="utf-8") or "[]")
        if not isinstance(raw, list):
            raise ValueError("workspace_memory.json must contain a list")
        return [payload for payload in raw if isinstance(payload, dict)]

    def _write_records(self, records: list[dict[str, object]]) -> None:
        with locked_path(self.records_path):
            self.records_path.write_text(
                json.dumps(records, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _coerce_record(self, payload: dict[str, object]) -> WorkspaceMemoryRecord:
        return WorkspaceMemoryRecord(
            id=str(payload["id"]),
            kind=str(payload.get("kind") or "fact"),
            value=str(payload.get("value") or ""),
            confidence=float(payload.get("confidence") or 0.0),
            source_thread_id=str(payload.get("source_thread_id") or ""),
            source_message_id=str(payload.get("source_message_id") or ""),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or payload.get("created_at") or ""),
            status=str(payload.get("status") or "active"),
        )


__all__ = ["WorkspaceMemoryStore"]
