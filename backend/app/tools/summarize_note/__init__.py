"""`summarize_note` tool：返回笔记当前的 summary，没有就退化为内容预览。"""

from __future__ import annotations

from pathlib import Path

from ..base import ToolContext, ToolResult

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def summarize_note(args: dict[str, object], context: ToolContext) -> ToolResult:
    path = str(args.get("path") or context.current_note_path or "").strip()
    if not path:
        return ToolResult(ok=False, tool="summarize_note", summary="", error="summarize_note requires path")
    note = context.note_service.get_note(path)
    summary = note.meta.summary or note.content[:240].strip()
    return ToolResult(
        ok=True,
        tool="summarize_note",
        summary=f"Summary for `{note.meta.title}`:\n\n{summary}",
        citations=[note.meta.relative_path],
        payload={"summary": summary},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Workspace-relative path to the note. If omitted, the current note is used.",
        },
    },
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "summarize_note",
        summarize_note,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "register", "summarize_note"]
