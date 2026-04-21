"""技能匹配服务。

`SkillService.resolve_skills` 根据当前 note 标签 / prompt 关键字 /
path 规则从 `SkillStore` 选出若干条 `Skill`，coordinator 会把它们注入
planner 的 prompt（`active_skills`）并限制可用工具（`tool_subset`）。
"""

from __future__ import annotations

from ..domain import SkillDefinition, utc_now_iso
from ..stores import SkillStore, SkillStorePort
from ..workspace_fs import WorkspaceFS


class SkillService:
    def __init__(self, fs: WorkspaceFS, *, skill_store: SkillStorePort | None = None) -> None:
        self.fs = fs
        self.skill_store = skill_store or SkillStore(fs)

    def list_skills(
        self,
        *,
        include_disabled: bool = False,
        include_content: bool = False,
    ) -> list[SkillDefinition]:
        return self.skill_store.list_skills(
            include_disabled=include_disabled,
            include_content=include_content,
        )

    def get_skill(self, skill_id: str) -> SkillDefinition | None:
        return self.skill_store.get_skill(skill_id)

    def upsert_skill(
        self,
        skill_id: str,
        *,
        name: str,
        description: str,
        prompt_prefix: str,
        when_to_use: str = "",
        tool_subset: list[str] | None = None,
        examples: list[str] | None = None,
        keywords: list[str] | None = None,
        enabled: bool = True,
    ) -> SkillDefinition:
        existing = {skill.id: skill for skill in self.skill_store.list_skills(include_disabled=True)}
        current = existing.get(skill_id)
        now = utc_now_iso()
        skill = SkillDefinition(
            id=skill_id,
            name=name.strip() or skill_id,
            description=description.strip(),
            prompt_prefix=prompt_prefix.strip(),
            when_to_use=when_to_use.strip(),
            tool_subset=sorted({item.strip() for item in (tool_subset or []) if item.strip()}),
            examples=[item.strip() for item in (examples or []) if item.strip()],
            keywords=[item.strip() for item in (keywords or []) if item.strip()],
            enabled=enabled,
            created_at=current.created_at if current is not None else now,
            updated_at=now,
        )
        return self.skill_store.upsert_skill(skill)

    def delete_skill(self, skill_id: str) -> None:
        self.skill_store.delete_skill(skill_id)

    def resolve_skills(
        self,
        *,
        prompt: str,
        current_note_path: str | None = None,
        active_tags: list[str] | None = None,
        limit: int = 3,
    ) -> list[SkillDefinition]:
        normalized_prompt = prompt.casefold()
        explicit_hits = []
        scored_hits: list[tuple[int, SkillDefinition]] = []
        tags = {tag.casefold() for tag in (active_tags or [])}

        for skill in self.list_skills():
            explicit = f"@{skill.id.casefold()}" in normalized_prompt or skill.name.casefold() in normalized_prompt
            if explicit:
                explicit_hits.append(skill)
                continue

            score = 0
            for keyword in skill.keywords:
                normalized = keyword.casefold()
                if normalized and normalized in normalized_prompt:
                    score += 2
                if normalized and normalized in tags:
                    score += 1
            if current_note_path and any(segment in current_note_path.casefold() for segment in skill.keywords):
                score += 1
            if score > 0:
                scored_hits.append((score, skill))

        explicit_map = {skill.id: skill for skill in explicit_hits}
        scored_hits.sort(key=lambda item: (-item[0], item[1].name.casefold()))
        resolved = list(explicit_map.values())
        for _, skill in scored_hits:
            if skill.id in explicit_map:
                continue
            resolved.append(skill)
            if len(resolved) >= limit:
                break
        return resolved[:limit]


__all__ = ["SkillService"]
