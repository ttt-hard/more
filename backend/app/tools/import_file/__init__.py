"""`import_file` tool：把本地文件通过 IngestService 导入为笔记。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ..base import ToolContext, ToolResult

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def import_file(args: dict[str, object], context: ToolContext) -> ToolResult:
    source_path = str(args.get("source_path") or "").strip()
    destination_dir = str(args.get("destination_dir") or "Inbox").strip() or "Inbox"
    if not source_path:
        return ToolResult(ok=False, tool="import_file", summary="", error="import_file requires source_path")
    events = [{"type": "tool_started", "tool": "import_file", "target": source_path}]
    job, note = context.ingest_service.import_file(source_path, destination_dir=destination_dir)
    context.search_service.refresh([note.meta.relative_path])
    events.append({"type": "note_created", "note": asdict(note.meta)})
    events.append({"type": "tool_finished", "tool": "import_file", "target": note.meta.relative_path})
    return ToolResult(
        ok=True,
        tool="import_file",
        summary=f"Imported file `{source_path}` into `{note.meta.relative_path}`.",
        citations=[note.meta.relative_path, job.source_ref],
        events=events,
        payload={"job": asdict(job), "note": asdict(note.meta)},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "source_path": {
            "type": "string",
            "description": "Absolute path on the local filesystem to the file to import.",
        },
        "destination_dir": {
            "type": "string",
            "description": "Workspace-relative directory to land the imported note (defaults to 'Inbox').",
        },
    },
    "required": ["source_path"],
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "import_file",
        import_file,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "import_file", "register"]
