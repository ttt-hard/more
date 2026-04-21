"""`update_note_metadata` tool：更新 note frontmatter 的结构化字段。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ..base import ToolContext, ToolResult
from .._utils import as_optional_str, normalize_str_list

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def update_note_metadata(args: dict[str, object], context: ToolContext) -> ToolResult:
    path = str(args.get("path") or context.current_note_path or "").strip()
    if not path:
        return ToolResult(
            ok=False,
            tool="update_note_metadata",
            summary="",
            error="update_note_metadata requires path",
        )
    title = as_optional_str(args.get("title"))
    summary = as_optional_str(args.get("summary"))
    source_type = as_optional_str(args.get("source_type"))
    tags = normalize_str_list(args.get("tags"))
    related = normalize_str_list(args.get("related"))
    events = [{"type": "tool_started", "tool": "update_note_metadata", "target": path}]
    note = context.note_service.update_note_metadata(
        path,
        title=title,
        tags=tags,
        summary=summary,
        related=related,
        source_type=source_type,
    )
    context.search_service.refresh([path])
    events.append({"type": "note_updated", "note": asdict(note.meta)})
    events.append({"type": "tool_finished", "tool": "update_note_metadata", "target": path})
    return ToolResult(
        ok=True,
        tool="update_note_metadata",
        summary=f"Updated metadata for `{note.meta.relative_path}`.",
        citations=[note.meta.relative_path],
        events=events,
        payload={"note": asdict(note.meta)},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Workspace-relative path to the note. If omitted, the current note is used.",
        },
        "title": {
            "type": "string",
            "description": "Optional new title; leave empty to keep existing.",
        },
        "summary": {
            "type": "string",
            "description": "Optional summary paragraph for the frontmatter.",
        },
        "source_type": {
            "type": "string",
            "description": "Optional source_type tag (e.g., 'agent', 'user', 'import').",
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Full replacement list of tag strings.",
        },
        "related": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Full replacement list of related note paths.",
        },
    },
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "update_note_metadata",
        update_note_metadata,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "register", "update_note_metadata"]
