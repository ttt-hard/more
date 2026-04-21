"""技能库端点。

列 / 增 / 改 / 删 Skill（prompt_prefix / when_to_use / tool_subset /
examples），agent 在一次 turn 开始时由 `SkillService.resolve_skills`
根据当前 note / prompt 选出最匹配的若干条注入提示词。
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from ...skills.service import SkillService
from ..deps import get_skill_service
from ..schemas import SkillUpsertRequest

router = APIRouter(prefix="/api/skills")


@router.get("")
def list_skills(
    include_disabled: bool = Query(default=False),
    skill_service: SkillService = Depends(get_skill_service),
) -> dict[str, object]:
    skills = skill_service.list_skills(include_disabled=include_disabled, include_content=True)
    return {"skills": [asdict(skill) for skill in skills]}


@router.get("/resolve")
def resolve_skills(
    prompt: str = Query(..., min_length=1),
    current_note_path: str | None = None,
    active_tags: list[str] | None = Query(default=None),
    limit: int = Query(default=3, ge=1, le=10),
    skill_service: SkillService = Depends(get_skill_service),
) -> dict[str, object]:
    skills = skill_service.resolve_skills(
        prompt=prompt,
        current_note_path=current_note_path,
        active_tags=active_tags or [],
        limit=limit,
    )
    return {"skills": [asdict(skill) for skill in skills]}


@router.put("/{skill_id}")
def upsert_skill(
    skill_id: str,
    request: SkillUpsertRequest,
    skill_service: SkillService = Depends(get_skill_service),
) -> dict[str, object]:
    skill = skill_service.upsert_skill(
        skill_id,
        name=request.name,
        description=request.description,
        prompt_prefix=request.prompt_prefix,
        when_to_use=request.when_to_use,
        tool_subset=request.tool_subset,
        examples=request.examples,
        keywords=request.keywords,
        enabled=request.enabled,
    )
    return {"skill": asdict(skill)}


@router.delete("/{skill_id}")
def delete_skill(
    skill_id: str,
    skill_service: SkillService = Depends(get_skill_service),
) -> dict[str, object]:
    skill_service.delete_skill(skill_id)
    return {"deleted": True, "skill_id": skill_id}
