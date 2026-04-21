"""审批请求存储。

`ApprovalStore` 把 agent 的 approval-gated 工具调用（move / delete）
落成 JSON 文件（`.more/approvals/<id>.json`），支持列 / 批准 / 拒绝 /
执行（真正调 `WorkspaceFS` 改文件）。所有请求在 `list_requests` 里按
updated_at 降序返回，单条坏文件会被跳过并 warning。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

from ..domain import ApprovalRequest, utc_now_iso
from ..infrastructure.file_lock import locked_path
from ..workspace_fs import WorkspaceFS

logger = logging.getLogger(__name__)


class ApprovalError(Exception):
    """Base error for approval operations."""


class ApprovalStore:
    def __init__(self, fs: WorkspaceFS) -> None:
        self.fs = fs
        self.approvals_root = self.fs.sidecar_root / "approvals"
        self.approvals_root.mkdir(parents=True, exist_ok=True)

    def create_request(
        self,
        *,
        action: str,
        targets: list[str],
        reason: str,
        payload: dict[str, object],
        source: str = "api",
    ) -> ApprovalRequest:
        approval = ApprovalRequest(
            id=uuid4().hex[:12],
            action=action,
            targets=targets,
            reason=reason,
            status="pending",
            created_at=utc_now_iso(),
            payload=payload,
            source=source,
        )
        self._persist(approval)
        return approval

    def get_request(self, approval_id: str) -> ApprovalRequest:
        path = self._request_path(approval_id)
        if not path.exists():
            raise ApprovalError(f"Approval request not found: {approval_id}")
        with locked_path(path):
            return ApprovalRequest(**json.loads(path.read_text(encoding="utf-8")))

    def list_requests(self) -> list[ApprovalRequest]:
        requests: list[ApprovalRequest] = []
        for path in sorted(self.approvals_root.glob("*.json")):
            try:
                with locked_path(path):
                    payload = json.loads(path.read_text(encoding="utf-8"))
                requests.append(ApprovalRequest(**payload))
            except (json.JSONDecodeError, TypeError, KeyError, ValueError) as exc:
                logger.warning("Skipping corrupt approval payload %s: %s", path.name, exc)
                continue
        return sorted(requests, key=lambda request: request.created_at, reverse=True)

    def approve(self, approval_id: str) -> tuple[ApprovalRequest, dict[str, object]]:
        path = self._request_path(approval_id)
        with locked_path(path):
            approval = self.get_request(approval_id)
            if approval.status != "pending":
                raise ApprovalError(f"Approval request is already {approval.status}")
            result = self._execute(approval)
            updated = replace(approval, status="approved")
            self._persist(updated)
        return updated, result

    def reject(self, approval_id: str) -> ApprovalRequest:
        path = self._request_path(approval_id)
        with locked_path(path):
            approval = self.get_request(approval_id)
            if approval.status != "pending":
                raise ApprovalError(f"Approval request is already {approval.status}")
            updated = replace(approval, status="rejected")
            self._persist(updated)
        return updated

    def requires_move_approval(self, source_path: str, target_path: str, overwrite: bool) -> bool:
        source = self.fs.resolve_path(source_path)
        target = self.fs.resolve_path(target_path)
        return source.is_dir() or overwrite or target.exists()

    def requires_delete_approval(self, path: str, recursive: bool) -> bool:
        del recursive
        self.fs.resolve_path(path)
        return True

    def _execute(self, approval: ApprovalRequest) -> dict[str, object]:
        if approval.action == "delete_path":
            path = str(approval.payload["path"])
            recursive = bool(approval.payload.get("recursive", False))
            self.fs.delete(path, recursive=recursive)
            return {"deleted": path}
        if approval.action == "move_path":
            source_path = str(approval.payload["source_path"])
            target_path = str(approval.payload["target_path"])
            overwrite = bool(approval.payload.get("overwrite", False))
            entry = self.fs.move(source_path, target_path, overwrite=overwrite)
            return {"entry": asdict(entry)}
        raise ApprovalError(f"Unsupported approval action: {approval.action}")

    def _persist(self, approval: ApprovalRequest) -> None:
        path = self._request_path(approval.id)
        with locked_path(path):
            path.write_text(
                json.dumps(asdict(approval), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def _request_path(self, approval_id: str) -> Path:
        return self.approvals_root / f"{approval_id}.json"
