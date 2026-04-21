"""对话检查点存储。

`ConversationCheckpointStore` 把某一刻的 conversation + 最近若干
message 存成快照；每个对话的所有 checkpoint 合并存在
`.more/checkpoints/<conversation_id>.json`（一个 JSON 数组），供前端在
"意外中断后恢复"或"手动回滚"时读取。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from ..domain import ConversationCheckpoint, utc_now_iso
from ..infrastructure.file_lock import locked_path
from ..workspace_fs import WorkspaceFS


class ConversationCheckpointStore:
    def __init__(self, fs: WorkspaceFS) -> None:
        self.fs = fs
        self.checkpoints_root = self.fs.sidecar_root / "checkpoints"
        self.checkpoints_root.mkdir(parents=True, exist_ok=True)

    def create_checkpoint(
        self,
        *,
        conversation_id: str,
        label: str,
        summary: str,
        token_estimate: int,
        active_note_path: str | None,
    ) -> ConversationCheckpoint:
        checkpoint = ConversationCheckpoint(
            id=uuid4().hex[:12],
            conversation_id=conversation_id,
            label=label.strip() or "Checkpoint",
            created_at=utc_now_iso(),
            summary=summary,
            token_estimate=token_estimate,
            active_note_path=active_note_path,
        )
        path = self._path(conversation_id)
        with locked_path(path):
            checkpoints = self._read_checkpoints(conversation_id)
            checkpoints.append(asdict(checkpoint))
            self._write_checkpoints(conversation_id, checkpoints)
        return checkpoint

    def list_checkpoints(self, conversation_id: str) -> list[ConversationCheckpoint]:
        checkpoints = [self._coerce_checkpoint(payload) for payload in self._read_checkpoints(conversation_id)]
        checkpoints.sort(key=lambda checkpoint: checkpoint.created_at, reverse=True)
        return checkpoints

    def _path(self, conversation_id: str) -> Path:
        return self.checkpoints_root / f"{conversation_id}.json"

    def _read_checkpoints(self, conversation_id: str) -> list[dict[str, object]]:
        path = self._path(conversation_id)
        if not path.exists():
            return []
        with locked_path(path):
            raw = json.loads(path.read_text(encoding="utf-8") or "[]")
        if not isinstance(raw, list):
            raise ValueError("checkpoint payload must be a list")
        return [payload for payload in raw if isinstance(payload, dict)]

    def _write_checkpoints(self, conversation_id: str, checkpoints: list[dict[str, object]]) -> None:
        path = self._path(conversation_id)
        with locked_path(path):
            path.write_text(json.dumps(checkpoints, ensure_ascii=False, indent=2), encoding="utf-8")

    def _coerce_checkpoint(self, payload: dict[str, object]) -> ConversationCheckpoint:
        return ConversationCheckpoint(
            id=str(payload["id"]),
            conversation_id=str(payload.get("conversation_id") or ""),
            label=str(payload.get("label") or "Checkpoint"),
            created_at=str(payload.get("created_at") or ""),
            summary=str(payload.get("summary") or ""),
            token_estimate=int(payload.get("token_estimate") or 0),
            active_note_path=str(payload.get("active_note_path")) if payload.get("active_note_path") else None,
        )


__all__ = ["ConversationCheckpointStore"]
