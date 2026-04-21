"""技能库存储。目录 + SKILL.md 版本。

每个 skill 存为 `.more/skills/<id>/SKILL.md`，文件头部是 YAML
frontmatter（id / name / description / when_to_use / tool_subset /
examples / keywords / enabled / created_at / updated_at），`---` 之后
的 markdown 正文对应 `SkillDefinition.prompt_prefix`（skill 的 procedure
文本）。这一格式与 claude-code / openclaw 的 skills 规范对齐；正文可按
需懒加载以控制 prompt token 预算。

`list_skills(include_content=False)` 默认只读 frontmatter，返回 空
`prompt_prefix` 的骨架；传 `include_content=True` 才会读正文并填充，
供 REST API、`get_skill` 和 `load_skill` 工具使用。`resolve_skills` 的
调用路径走默认分支，避免把所有正文塞进 planner prompt。

首次访问时若发现旧版 `.more/skills/skills.json`（JSON 数组）而目录里
没有 `<id>/SKILL.md`，会一次性迁移为新结构并把 json 改名为
`skills.json.bak`；下次启动就走纯目录路径。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

import yaml

from ..domain import SkillDefinition, utc_now_iso
from ..infrastructure.file_lock import locked_path
from ..workspace_fs import WorkspaceFS

SKILL_FILENAME = "SKILL.md"
_FRONTMATTER_RE = re.compile(r"^---\s*\n(?P<frontmatter>.*?)\n---\s*\n?(?P<body>.*)$", re.DOTALL)


DEFAULT_SKILLS = [
    {
        "id": "drafting",
        "name": "Drafting",
        "description": "Turn grounded evidence into structured draft output.",
        "prompt_prefix": "When the user asks for a draft, prefer headings, concise bullets, and evidence-grounded conclusions.",
        "when_to_use": "Use for drafting, summarization, or outline generation.",
        "tool_subset": ["read_note", "search_notes", "search_workspace", "create_note", "update_note_metadata"],
        "examples": ["生成一份 AI 草稿", "整理当前笔记为提纲"],
        "keywords": ["草稿", "draft", "提纲", "outline", "总结", "summary"],
        "enabled": True,
    },
    {
        "id": "interview",
        "name": "Interview Prep",
        "description": "Extract interview-relevant concepts, questions, and takeaways.",
        "prompt_prefix": "Emphasize interview questions, key concepts, tradeoffs, and concise takeaway bullets.",
        "when_to_use": "Use for interview preparation and concept extraction.",
        "tool_subset": ["search_notes", "search_workspace", "summarize_note", "read_note"],
        "examples": ["提取可能的面试问题", "基于资料生成面试结论"],
        "keywords": ["面试", "interview", "问题", "question", "概念", "takeaway"],
        "enabled": True,
    },
    {
        "id": "research",
        "name": "Research",
        "description": "Investigate workspace evidence before answering or editing.",
        "prompt_prefix": "Prefer retrieval and note inspection before making claims; surface uncertainty when evidence is incomplete.",
        "when_to_use": "Use for exploratory QA and workspace investigation.",
        "tool_subset": ["search_notes", "search_workspace", "read_note", "read_file", "glob_search", "grep_search"],
        "examples": ["当前工作区里有哪些相关资料", "先检索再回答"],
        "keywords": ["研究", "research", "检索", "search", "资料", "evidence"],
        "enabled": True,
    },
]


class SkillStore:
    def __init__(self, fs: WorkspaceFS) -> None:
        self.fs = fs
        self.skills_root = self.fs.sidecar_root / "skills"
        self.skills_root.mkdir(parents=True, exist_ok=True)
        self._legacy_json_path = self.skills_root / "skills.json"
        self._migrate_legacy_if_needed()
        self._seed_defaults_if_empty()

    # -- Public API -----------------------------------------------------------

    def list_skills(
        self,
        *,
        include_disabled: bool = False,
        include_content: bool = False,
    ) -> list[SkillDefinition]:
        skills: list[SkillDefinition] = []
        for skill_dir in sorted(p for p in self.skills_root.iterdir() if p.is_dir()):
            skill_file = skill_dir / SKILL_FILENAME
            if not skill_file.is_file():
                continue
            try:
                skill = self._read_skill_file(skill_file, include_content=include_content)
            except (OSError, ValueError, yaml.YAMLError):
                continue
            if not include_disabled and not skill.enabled:
                continue
            skills.append(skill)
        skills.sort(key=lambda item: item.name.casefold())
        return skills

    def get_skill(self, skill_id: str) -> SkillDefinition | None:
        skill_file = self.skills_root / skill_id / SKILL_FILENAME
        if not skill_file.is_file():
            return None
        try:
            return self._read_skill_file(skill_file, include_content=True)
        except (OSError, ValueError, yaml.YAMLError):
            return None

    def upsert_skill(self, skill: SkillDefinition) -> SkillDefinition:
        if not skill.id:
            raise ValueError("SkillDefinition.id is required")
        skill_dir = self.skills_root / skill.id
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / SKILL_FILENAME
        with locked_path(skill_file):
            skill_file.write_text(self._render_skill_file(skill), encoding="utf-8")
        return skill

    def delete_skill(self, skill_id: str) -> None:
        skill_dir = self.skills_root / skill_id
        if not skill_dir.exists():
            return
        skill_file = skill_dir / SKILL_FILENAME
        with locked_path(skill_file):
            if skill_file.exists():
                skill_file.unlink()
            # Only remove the directory if it is now empty; leave any user-added
            # artifacts (e.g., supporting notes next to the SKILL.md) alone.
            try:
                skill_dir.rmdir()
            except OSError:
                pass

    # -- Internal: file IO ----------------------------------------------------

    def _read_skill_file(self, skill_file: Path, *, include_content: bool) -> SkillDefinition:
        raw = skill_file.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(raw)
        if match is None:
            # No frontmatter block. Treat the file as a plain body under the
            # directory name; leave other metadata empty.
            skill_id = skill_file.parent.name
            return SkillDefinition(
                id=skill_id,
                name=skill_id,
                description="",
                prompt_prefix=(raw.strip() if include_content else ""),
            )
        frontmatter_str = match.group("frontmatter") or ""
        body = match.group("body") or ""
        data = yaml.safe_load(frontmatter_str) or {}
        if not isinstance(data, dict):
            data = {}
        skill_id = str(data.get("id") or skill_file.parent.name)
        return SkillDefinition(
            id=skill_id,
            name=str(data.get("name") or skill_id),
            description=str(data.get("description") or ""),
            prompt_prefix=(body.strip() if include_content else ""),
            when_to_use=str(data.get("when_to_use") or ""),
            tool_subset=[str(item) for item in (data.get("tool_subset") or [])],
            examples=[str(item) for item in (data.get("examples") or [])],
            keywords=[str(item) for item in (data.get("keywords") or [])],
            enabled=bool(data.get("enabled", True)),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or data.get("created_at") or ""),
        )

    def _render_skill_file(self, skill: SkillDefinition) -> str:
        frontmatter = {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "when_to_use": skill.when_to_use,
            "tool_subset": list(skill.tool_subset),
            "examples": list(skill.examples),
            "keywords": list(skill.keywords),
            "enabled": skill.enabled,
            "created_at": skill.created_at,
            "updated_at": skill.updated_at,
        }
        frontmatter_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
        body = skill.prompt_prefix.strip()
        return f"---\n{frontmatter_yaml}---\n\n{body}\n"

    # -- Internal: bootstrap / migration -------------------------------------

    def _has_any_skill_files(self) -> bool:
        for skill_dir in self.skills_root.iterdir():
            if skill_dir.is_dir() and (skill_dir / SKILL_FILENAME).is_file():
                return True
        return False

    def _seed_defaults_if_empty(self) -> None:
        if self._has_any_skill_files():
            return
        now = utc_now_iso()
        for payload in DEFAULT_SKILLS:
            merged = dict(payload)
            merged.setdefault("created_at", now)
            merged.setdefault("updated_at", now)
            skill = self._coerce_default(merged)
            self.upsert_skill(skill)

    def _migrate_legacy_if_needed(self) -> None:
        if not self._legacy_json_path.is_file():
            return
        if self._has_any_skill_files():
            # Directory structure already populated; keep the legacy file as a
            # backup by renaming to `.bak` if not already.
            backup = self._legacy_json_path.with_suffix(".json.bak")
            if not backup.exists():
                try:
                    self._legacy_json_path.rename(backup)
                except OSError:
                    pass
            return
        try:
            raw = json.loads(self._legacy_json_path.read_text(encoding="utf-8") or "[]")
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, list):
            return
        for payload in raw:
            if not isinstance(payload, dict):
                continue
            skill_id = str(payload.get("id") or "").strip()
            if not skill_id:
                continue
            try:
                self.upsert_skill(self._coerce_default(payload))
            except (ValueError, OSError, yaml.YAMLError):
                continue
        backup = self._legacy_json_path.with_suffix(".json.bak")
        try:
            self._legacy_json_path.rename(backup)
        except OSError:
            pass

    def _coerce_default(self, payload: dict[str, object]) -> SkillDefinition:
        return SkillDefinition(
            id=str(payload.get("id") or ""),
            name=str(payload.get("name") or payload.get("id") or "Unnamed Skill"),
            description=str(payload.get("description") or ""),
            prompt_prefix=str(payload.get("prompt_prefix") or ""),
            when_to_use=str(payload.get("when_to_use") or ""),
            tool_subset=[str(item) for item in (payload.get("tool_subset") or [])],
            examples=[str(item) for item in (payload.get("examples") or [])],
            keywords=[str(item) for item in (payload.get("keywords") or [])],
            enabled=bool(payload.get("enabled", True)),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or payload.get("created_at") or ""),
        )


__all__ = ["SKILL_FILENAME", "SkillStore"]
