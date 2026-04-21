"""`link_notes` tool：把目标笔记追加到源笔记的 related 列表中。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ..base import ToolContext, ToolResult
from .._utils import normalize_str_list

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def link_notes(args: dict[str, object], context: ToolContext) -> ToolResult:
    source_path = str(args.get("source_path") or context.current_note_path or "").strip()
    target_paths = normalize_str_list(args.get("target_paths")) or []
    if not source_path or not target_paths:
        return ToolResult(ok=False, tool="link_notes", summary="", error="link_notes requires source_path and target_paths")
    note = context.note_service.get_note(source_path)
    next_related = sorted(set(note.meta.related + target_paths))
    updated = context.note_service.update_note_metadata(source_path, related=next_related)
    context.search_service.refresh([source_path])
    return ToolResult(
        ok=True,
        tool="link_notes",
        summary=f"Linked `{source_path}` to {len(target_paths)} note(s).",
        citations=[source_path, *target_paths],
        events=[{"type": "note_updated", "note": asdict(updated.meta)}],
        payload={"note": asdict(updated.meta)},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "source_path": {
            "type": "string",
            "description": "Workspace-relative path of the source note. If omitted, the current note is used.",
        },
        "target_paths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "One or more workspace-relative paths to append to the source note's related list.",
        },
    },
    "required": ["target_paths"],
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "link_notes",
        link_notes,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "link_notes", "register"]
