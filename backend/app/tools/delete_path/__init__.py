"""`delete_path` tool：删除工作区文件 / 目录（强制 approval）。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ..base import ToolContext, ToolResult

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def delete_path(args: dict[str, object], context: ToolContext) -> ToolResult:
    path = str(args.get("path") or "").strip()
    recursive = bool(args.get("recursive", False))
    if not path:
        return ToolResult(ok=False, tool="delete_path", summary="", error="delete_path requires path")
    approval = context.approval_store.create_request(
        action="delete_path",
        targets=[path],
        reason="Deleting files requires confirmation.",
        payload={"path": path, "recursive": recursive},
        source="agent",
    )
    return ToolResult(
        ok=True,
        tool="delete_path",
        summary=f"Delete request for `{path}` is awaiting approval.",
        citations=[path],
        events=[{"type": "approval_required", "approval": asdict(approval)}],
        requires_approval=True,
        task_state="awaiting_approval",
        run_status="awaiting_approval",
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Workspace-relative path of the file or directory to delete.",
        },
        "recursive": {
            "type": "boolean",
            "description": "If true, allow deleting a non-empty directory. Approval is always required regardless.",
        },
    },
    "required": ["path"],
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "delete_path",
        delete_path,
        kind="approval-gated",
        approval_gated=True,
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "delete_path", "register"]
