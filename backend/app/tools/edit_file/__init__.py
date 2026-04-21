"""`edit_file` tool：对现有文件做字符串替换。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ...notes import NoteError
from ..base import ToolContext, ToolResult

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def edit_file(args: dict[str, object], context: ToolContext) -> ToolResult:
    path = str(args.get("path") or "").strip()
    search_text = str(args.get("search_text") or "").strip()
    replace_text = str(args.get("replace_text") or "").strip()
    replace_all = bool(args.get("replace_all", False))
    if not path or not search_text:
        return ToolResult(
            ok=False,
            tool="edit_file",
            summary="",
            error="edit_file requires path and search_text",
        )
    events = [{"type": "tool_started", "tool": "edit_file", "target": path}]
    context.fs.edit_text(path, search_text, replace_text, replace_all=replace_all)
    context.search_service.refresh([path])
    if path.lower().endswith(".md"):
        try:
            note = context.note_service.get_note(path)
            events.append({"type": "note_updated", "note": asdict(note.meta)})
        except NoteError:
            # Frontmatter may be invalid; the edit itself landed on disk.
            events.append({"type": "file_written", "path": path})
    else:
        events.append({"type": "file_written", "path": path})
    events.append({"type": "tool_finished", "tool": "edit_file", "target": path})
    return ToolResult(
        ok=True,
        tool="edit_file",
        summary=f"Edited file `{path}` by replacing the requested text.",
        citations=[path],
        events=events,
        payload={"path": path},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Workspace-relative path of the file to edit.",
        },
        "search_text": {
            "type": "string",
            "description": "Literal text to find. Must match exactly (case + whitespace).",
        },
        "replace_text": {
            "type": "string",
            "description": "Replacement text (can be empty to delete the match).",
        },
        "replace_all": {
            "type": "boolean",
            "description": "If true replace every occurrence; otherwise only the first.",
        },
    },
    "required": ["path", "search_text"],
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "edit_file",
        edit_file,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "edit_file", "register"]
