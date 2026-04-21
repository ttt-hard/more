"""`read_file` tool：读取工作区 UTF-8 文本文件。"""

from __future__ import annotations

from pathlib import Path

from ..base import ToolContext, ToolResult

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def read_file(args: dict[str, object], context: ToolContext) -> ToolResult:
    path = str(args.get("path") or "").strip()
    if not path:
        return ToolResult(ok=False, tool="read_file", summary="", error="read_file requires path")
    events = [{"type": "tool_started", "tool": "read_file", "target": path}]
    content = context.fs.read_text(path)
    events.append({"type": "tool_finished", "tool": "read_file", "target": path})
    return ToolResult(
        ok=True,
        tool="read_file",
        summary=f"File `{path}` contents:\n\n{content[:800].strip()}",
        citations=[path],
        events=events,
        payload={"path": path},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Workspace-relative path of a UTF-8 text file to read.",
        },
    },
    "required": ["path"],
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "read_file",
        read_file,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "read_file", "register"]
