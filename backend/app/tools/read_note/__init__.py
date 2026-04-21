"""`read_note` tool：读取笔记的元数据 + 正文摘要。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ..base import ToolContext, ToolResult

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def read_note(args: dict[str, object], context: ToolContext) -> ToolResult:
    path = str(args.get("path") or context.current_note_path or "").strip()
    if not path:
        return ToolResult(ok=False, tool="read_note", summary="", error="read_note requires path")
    events = [{"type": "tool_started", "tool": "read_note", "target": path}]
    note = context.note_service.get_note(path)
    events.append({"type": "tool_finished", "tool": "read_note", "target": path})
    return ToolResult(
        ok=True,
        tool="read_note",
        summary=f"Current note `{note.meta.title}` summary:\n\n{note.content[:400].strip()}",
        citations=[note.meta.relative_path],
        events=events,
        payload={"note": asdict(note.meta)},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Workspace-relative path to the note (e.g., 'Notes/foo.md'). If omitted, the current note in the active conversation is used.",
        },
    },
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "read_note",
        read_note,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "read_note", "register"]
