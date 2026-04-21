"""`import_url` tool：抓取 URL 内容并导入为笔记。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ..base import ToolContext, ToolResult

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def import_url(args: dict[str, object], context: ToolContext) -> ToolResult:
    url = str(args.get("url") or "").strip()
    destination_dir = str(args.get("destination_dir") or "Inbox").strip() or "Inbox"
    if not url:
        return ToolResult(ok=False, tool="import_url", summary="", error="import_url requires url")
    events = [{"type": "tool_started", "tool": "import_url", "target": url}]
    job, note = context.ingest_service.import_url(url, destination_dir=destination_dir)
    context.search_service.refresh([note.meta.relative_path])
    events.append({"type": "note_created", "note": asdict(note.meta)})
    events.append({"type": "tool_finished", "tool": "import_url", "target": note.meta.relative_path})
    return ToolResult(
        ok=True,
        tool="import_url",
        summary=f"Imported URL `{url}` into `{note.meta.relative_path}`.",
        citations=[note.meta.relative_path, job.source_ref],
        events=events,
        payload={"job": asdict(job), "note": asdict(note.meta)},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "Full URL to fetch and import (http:// or https://).",
        },
        "destination_dir": {
            "type": "string",
            "description": "Workspace-relative directory to land the imported note (defaults to 'Inbox').",
        },
    },
    "required": ["url"],
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "import_url",
        import_url,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "import_url", "register"]
