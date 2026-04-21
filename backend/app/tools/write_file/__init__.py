"""`write_file` tool：创建或覆盖工作区文件。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ...notes import NoteError
from ..base import ToolContext, ToolResult

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def write_file(args: dict[str, object], context: ToolContext) -> ToolResult:
    path = str(args.get("path") or "").strip()
    content = str(args.get("content") or "").strip()
    if not path:
        return ToolResult(ok=False, tool="write_file", summary="", error="write_file requires path")
    existed = context.fs.resolve_path(path).exists()
    events = [{"type": "tool_started", "tool": "write_file", "target": path}]
    context.fs.write_text(path, content, overwrite=True)
    context.search_service.refresh([path])
    if path.lower().endswith(".md"):
        try:
            note = context.note_service.get_note(path)
            events.append({"type": "note_updated", "note": asdict(note.meta)})
        except NoteError:
            # Frontmatter may be invalid; the file itself was written successfully.
            events.append({"type": "file_written", "path": path})
    else:
        events.append({"type": "file_written", "path": path})
    events.append({"type": "tool_finished", "tool": "write_file", "target": path})
    verb = "Updated" if existed else "Created"
    return ToolResult(
        ok=True,
        tool="write_file",
        summary=f"{verb} file `{path}`.",
        citations=[path],
        events=events,
        payload={"path": path},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Workspace-relative path of the file to create or overwrite.",
        },
        "content": {
            "type": "string",
            "description": "Full file contents. Empty string produces an empty file.",
        },
    },
    "required": ["path"],
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "write_file",
        write_file,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "write_file", "register"]
