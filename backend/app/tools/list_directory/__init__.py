"""`list_directory` tool：列出工作区目录。"""

from __future__ import annotations

from pathlib import Path

from ..base import ToolContext, ToolResult

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def list_directory(args: dict[str, object], context: ToolContext) -> ToolResult:
    path = str(args.get("path") or ".").strip() or "."
    events = [{"type": "tool_started", "tool": "list_directory", "target": path}]
    entries = context.fs.list_dir("" if path == "." else path)
    events.append({"type": "tool_finished", "tool": "list_directory", "target": path})
    lines = [f"Directory `{path}` contains {len(entries)} item(s):"]
    lines.extend(f"- {entry.kind}: {entry.path}" for entry in entries[:20])
    return ToolResult(
        ok=True,
        tool="list_directory",
        summary="\n".join(lines),
        citations=[path],
        events=events,
        payload={"path": path},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Workspace-relative directory path. Use '.' (or omit) for the workspace root.",
        },
    },
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "list_directory",
        list_directory,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "list_directory", "register"]
