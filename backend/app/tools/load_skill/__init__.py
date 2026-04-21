"""`load_skill` tool：按需读取指定 skill 的完整 SKILL.md 正文。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ...skills.service import SkillService
from ..base import ToolContext, ToolResult

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def load_skill(args: dict[str, object], context: ToolContext) -> ToolResult:
    skill_id = str(
        args.get("skill_id")
        or args.get("id")
        or args.get("name")
        or ""
    ).strip()
    if not skill_id:
        return ToolResult(
            ok=False,
            tool="load_skill",
            summary="",
            error="load_skill requires skill_id",
        )

    service = SkillService(context.fs)
    skill = service.get_skill(skill_id)
    if skill is None:
        return ToolResult(
            ok=False,
            tool="load_skill",
            summary=f"Skill `{skill_id}` is not available in this workspace.",
            error="skill_not_found",
            payload={"skill_id": skill_id},
        )
    if not skill.enabled:
        return ToolResult(
            ok=False,
            tool="load_skill",
            summary=f"Skill `{skill_id}` is disabled.",
            error="skill_disabled",
            payload={"skill_id": skill_id, "skill": asdict(skill)},
        )
    body = skill.prompt_prefix.strip()
    summary_lines = [f"Loaded skill `{skill.name}` ({skill.id})."]
    if skill.when_to_use:
        summary_lines.append(f"When to use: {skill.when_to_use}")
    if skill.tool_subset:
        summary_lines.append("Preferred tools: " + ", ".join(skill.tool_subset))
    if body:
        summary_lines.append("")
        summary_lines.append(body)
    citation = f".more/skills/{skill.id}/SKILL.md"
    return ToolResult(
        ok=True,
        tool="load_skill",
        summary="\n".join(summary_lines),
        citations=[citation],
        payload={"skill": asdict(skill)},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "skill_id": {
            "type": "string",
            "description": "The id of the skill to load, as shown in <active_skills>.",
        },
    },
    "required": ["skill_id"],
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "load_skill",
        load_skill,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "load_skill", "register"]
