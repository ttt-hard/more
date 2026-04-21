"""技能匹配子包。

`SkillService.resolve_skills` 根据当前 note 标签 / prompt 关键字 / path 规则
从 `SkillStore` 选出若干条 `Skill` 注入到 turn context。后续 P0-C 阶段会把
持久化从 `.more/skills/skills.json` 数组改造成每技能一个 SKILL.md 目录，
并引入 `load_skill` 工具走懒加载路径。
"""

from .service import SkillService

__all__ = ["SkillService"]
