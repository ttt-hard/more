"""`save_preference` tool：更新用户偏好（language / answer_style / default_note_dir / theme）。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ..base import ToolContext, ToolResult
from .._utils import as_optional_str

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def save_preference(args: dict[str, object], context: ToolContext) -> ToolResult:
    updates = {
        "language": as_optional_str(args.get("language")),
        "answer_style": as_optional_str(args.get("answer_style")),
        "default_note_dir": as_optional_str(args.get("default_note_dir")),
        "theme": as_optional_str(args.get("theme")),
    }
    preference = context.memory_service.update_preferences(**updates)
    return ToolResult(
        ok=True,
        tool="save_preference",
        summary="Updated user preferences.",
        payload={"preferences": asdict(preference)},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "language": {
            "type": "string",
            "description": "Preferred reply language (e.g., 'zh-CN', 'en').",
        },
        "answer_style": {
            "type": "string",
            "description": "Preferred answer style (e.g., 'concise', 'detailed').",
        },
        "default_note_dir": {
            "type": "string",
            "description": "Default directory for newly created notes (e.g., 'Inbox', 'Notes').",
        },
        "theme": {
            "type": "string",
            "description": "UI theme preference (e.g., 'light', 'dark').",
        },
    },
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "save_preference",
        save_preference,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "register", "save_preference"]
