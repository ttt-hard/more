"""`read_preference` tool：读取当前用户偏好。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ..base import ToolContext, ToolResult

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def read_preference(args: dict[str, object], context: ToolContext) -> ToolResult:
    del args
    preference = context.memory_service.get_preferences()
    return ToolResult(
        ok=True,
        tool="read_preference",
        summary="Loaded current user preferences.",
        payload={"preferences": asdict(preference)},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "read_preference",
        read_preference,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "read_preference", "register"]
