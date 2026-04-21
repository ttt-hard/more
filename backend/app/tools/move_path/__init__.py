"""`move_path` tool：移动 / 重命名工作区文件或目录（approval-gated）。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ..base import ToolContext, ToolResult

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def move_path(args: dict[str, object], context: ToolContext) -> ToolResult:
    source_path = str(args.get("source_path") or "").strip()
    target_path = str(args.get("target_path") or "").strip()
    overwrite = bool(args.get("overwrite", False))
    if not source_path or not target_path:
        return ToolResult(
            ok=False,
            tool="move_path",
            summary="",
            error="move_path requires source_path and target_path",
        )
    if context.approval_store.requires_move_approval(source_path, target_path, overwrite):
        approval = context.approval_store.create_request(
            action="move_path",
            targets=[source_path, target_path],
            reason="Overwriting or moving directories requires confirmation.",
            payload={
                "source_path": source_path,
                "target_path": target_path,
                "overwrite": overwrite,
            },
            source="agent",
        )
        return ToolResult(
            ok=True,
            tool="move_path",
            summary=f"Move request for `{source_path}` is awaiting approval.",
            citations=[source_path, target_path],
            events=[{"type": "approval_required", "approval": asdict(approval)}],
            requires_approval=True,
            task_state="awaiting_approval",
            run_status="awaiting_approval",
        )
    events = [{"type": "tool_started", "tool": "move_path", "target": source_path}]
    entry = context.fs.move(source_path, target_path, overwrite=overwrite)
    events.append({"type": "tool_finished", "tool": "move_path", "target": target_path})
    return ToolResult(
        ok=True,
        tool="move_path",
        summary=f"Moved `{source_path}` to `{target_path}`.",
        citations=[entry.path],
        events=events,
        payload={"entry": asdict(entry)},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "source_path": {
            "type": "string",
            "description": "Workspace-relative source path to move or rename.",
        },
        "target_path": {
            "type": "string",
            "description": "Workspace-relative destination path.",
        },
        "overwrite": {
            "type": "boolean",
            "description": "If true, allow overwriting an existing target (still approval-gated).",
        },
    },
    "required": ["source_path", "target_path"],
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "move_path",
        move_path,
        kind="approval-gated",
        approval_gated=True,
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "move_path", "register"]
