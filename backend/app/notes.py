"""笔记（Markdown + YAML frontmatter）服务。

`NoteService` 读写工作区里的 .md 笔记，解析前置 `---` frontmatter 成
`NoteMeta`、正文作为 `content`，并负责创建 / 更新 / 元数据补丁。frontmatter
YAML 解析错误会被封装成 `NoteFormatError`（继承 `NoteError`），方便上层
在 get_note 时统一降级处理。
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import yaml

from .domain import NoteDocument, NoteMeta, utc_now_iso
from .workspace_fs import WorkspaceFS, utc_now_iso_from_epoch


class NoteError(Exception):
    """Base error for note operations."""


class NoteFormatError(NoteError):
    """Raised when note frontmatter is invalid."""


class NoteService:
    def __init__(self, fs: WorkspaceFS) -> None:
        self.fs = fs

    def list_notes(self, base_path: str = "") -> list[NoteMeta]:
        notes: list[NoteMeta] = []
        for item in self.fs.iter_paths(base_path):
            if not item.is_file() or item.suffix.lower() != ".md":
                continue
            notes.append(self.get_note(item.relative_to(self.fs.root).as_posix()).meta)
        return sorted(notes, key=lambda note: (note.updated_at, note.relative_path), reverse=True)

    def get_note(self, relative_path: str) -> NoteDocument:
        normalized_path = self._normalize_note_path(relative_path, append_suffix=False)
        raw_content = self.fs.read_text(normalized_path)
        return self._parse_note(raw_content, normalized_path)

    def create_note(
        self,
        relative_path: str,
        content: str,
        title: str | None = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        related: list[str] | None = None,
        source_type: str = "manual",
    ) -> NoteDocument:
        note_path = self._normalize_note_path(relative_path)
        now = utc_now_iso()
        meta = NoteMeta(
            id=uuid4().hex[:12],
            title=title or self._derive_title(content, note_path),
            relative_path=note_path,
            tags=self._normalize_list(tags),
            summary=(summary or "").strip(),
            related=self._normalize_list(related),
            updated_at=now,
            source_type=source_type,
        )
        document = NoteDocument(meta=meta, content=content.rstrip())
        self.fs.write_text(note_path, self._render_note(document), overwrite=False)
        return document

    def update_note(
        self,
        relative_path: str,
        content: str | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        related: list[str] | None = None,
        source_type: str | None = None,
    ) -> NoteDocument:
        current = self.get_note(relative_path)
        note_path = current.meta.relative_path
        next_content = current.content if content is None else content.rstrip()
        next_meta = NoteMeta(
            id=current.meta.id,
            title=title if title is not None else self._derive_title(next_content, note_path, fallback=current.meta.title),
            relative_path=note_path,
            tags=current.meta.tags if tags is None else self._normalize_list(tags),
            summary=current.meta.summary if summary is None else summary.strip(),
            related=current.meta.related if related is None else self._normalize_list(related),
            updated_at=utc_now_iso(),
            source_type=current.meta.source_type if source_type is None else source_type,
        )
        updated = NoteDocument(meta=next_meta, content=next_content)
        self.fs.write_text(note_path, self._render_note(updated), overwrite=True)
        return updated

    def update_note_metadata(
        self,
        relative_path: str,
        *,
        title: str | None = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        related: list[str] | None = None,
        source_type: str | None = None,
    ) -> NoteDocument:
        return self.update_note(
            relative_path,
            title=title,
            tags=tags,
            summary=summary,
            related=related,
            source_type=source_type,
        )

    def _normalize_note_path(self, relative_path: str, append_suffix: bool = True) -> str:
        note_path = relative_path.strip().replace("\\", "/")
        if not note_path:
            raise NoteError("Note path must not be empty")
        if append_suffix and not note_path.lower().endswith(".md"):
            note_path = f"{note_path}.md"
        return note_path

    def _parse_note(self, raw_content: str, relative_path: str) -> NoteDocument:
        frontmatter: dict[str, object] = {}
        body = raw_content
        resolved_path = self.fs.resolve_path(relative_path)
        lines = raw_content.splitlines()
        if lines and lines[0].strip() == "---":
            closing_index = None
            for index in range(1, len(lines)):
                if lines[index].strip() == "---":
                    closing_index = index
                    break
            if closing_index is None:
                raise NoteFormatError(f"Unclosed frontmatter in {relative_path}")
            frontmatter_text = "\n".join(lines[1:closing_index])
            try:
                frontmatter = yaml.safe_load(frontmatter_text) or {}
            except yaml.YAMLError as exc:
                raise NoteFormatError(f"Invalid YAML frontmatter in {relative_path}: {exc}") from exc
            if not isinstance(frontmatter, dict):
                raise NoteFormatError(f"Frontmatter must be a mapping in {relative_path}")
            body = "\n".join(lines[closing_index + 1 :]).strip()
        title = str(frontmatter.get("title") or self._derive_title(body, relative_path))
        note_meta = NoteMeta(
            id=str(frontmatter.get("id") or self._default_note_id(relative_path)),
            title=title,
            relative_path=relative_path,
            tags=self._normalize_list(frontmatter.get("tags")),
            summary=str(frontmatter.get("summary") or "").strip(),
            related=self._normalize_list(frontmatter.get("related")),
            updated_at=str(
                frontmatter.get("updated_at") or utc_now_iso_from_epoch(resolved_path.stat().st_mtime)
            ),
            source_type=str(frontmatter.get("source_type") or "manual"),
        )
        return NoteDocument(meta=note_meta, content=body)

    def _render_note(self, document: NoteDocument) -> str:
        frontmatter = {
            "id": document.meta.id,
            "title": document.meta.title,
            "tags": document.meta.tags,
            "summary": document.meta.summary,
            "related": document.meta.related,
            "updated_at": document.meta.updated_at,
            "source_type": document.meta.source_type,
        }
        rendered_meta = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
        body = document.content.rstrip()
        return f"---\n{rendered_meta}\n---\n\n{body}\n"

    def _derive_title(self, content: str, relative_path: str, fallback: str | None = None) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                if title:
                    return title
            return stripped[:80]
        if fallback:
            return fallback
        return Path(relative_path).stem.replace("-", " ").replace("_", " ").strip() or "Untitled"

    def _normalize_list(self, values: object) -> list[str]:
        if values is None:
            return []
        if isinstance(values, str):
            return [values] if values.strip() else []
        if isinstance(values, list):
            cleaned = [str(item).strip() for item in values if str(item).strip()]
            return cleaned
        raise NoteError("Expected a list of strings")

    def _default_note_id(self, relative_path: str) -> str:
        return hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:12]
