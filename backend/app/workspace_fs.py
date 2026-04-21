"""工作区文件系统适配层。

`WorkspaceFS` 把所有对工作区根目录下文件的读写封装起来，统一做路径归一化、
越界校验（`WorkspaceAccessError`）、二进制 / UTF-8 校验（`WorkspaceTextError`）
和工作区初始化（默认目录 + 侧车目录 `.more/`）。上层所有 service、store、
agent 工具都通过 `WorkspaceFS` 访问磁盘，保证工作区沙箱边界。
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable

import yaml

from .domain import FileEntry, TreeEntry, Workspace, utc_now_iso


DEFAULT_WORKSPACE_DIRS = ("Notes", "Inbox", "Archive", "Assets")
DEFAULT_SIDECAR_DIRS = ("sessions", "tasks", "index", "approvals", "imports", "memory", "checkpoints", "skills", "mcp")
TEXT_FILE_SIZE_LIMIT = 2 * 1024 * 1024


class WorkspaceError(Exception):
    """Base error for workspace operations."""


class WorkspaceNotFoundError(WorkspaceError):
    """Raised when a workspace path does not exist."""


class WorkspaceAccessError(WorkspaceError):
    """Raised when a path escapes the workspace root."""


class WorkspaceTextError(WorkspaceError):
    """Raised when a file cannot be treated as text."""


class WorkspaceFS:
    def __init__(self, root_path: str | Path) -> None:
        self.root = Path(root_path).expanduser()
        if not self.root.exists():
            raise WorkspaceNotFoundError(f"Workspace does not exist: {self.root}")
        self.root = self.root.resolve()
        self.sidecar_root = self.root / ".more"

    def bootstrap(self, name: str | None = None) -> Workspace:
        for directory in DEFAULT_WORKSPACE_DIRS:
            (self.root / directory).mkdir(parents=True, exist_ok=True)

        self.sidecar_root.mkdir(parents=True, exist_ok=True)
        for directory in DEFAULT_SIDECAR_DIRS:
            (self.sidecar_root / directory).mkdir(parents=True, exist_ok=True)

        config_path = self.sidecar_root / "config.yaml"
        if not config_path.exists():
            config_path.write_text(
                yaml.safe_dump(
                    {
                        "name": name or self.root.name,
                        "root_path": str(self.root),
                        "created_at": utc_now_iso(),
                    },
                    sort_keys=False,
                    allow_unicode=True,
                ),
                encoding="utf-8",
            )

        preferences_path = self.sidecar_root / "preferences.yaml"
        if not preferences_path.exists():
            preferences_path.write_text(
                yaml.safe_dump(
                    {
                        "language": "zh-CN",
                        "answer_style": "concise",
                        "default_note_dir": "Notes",
                    },
                    sort_keys=False,
                    allow_unicode=True,
                ),
                encoding="utf-8",
            )

        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return Workspace(
            name=config.get("name", self.root.name),
            root_path=str(self.root),
            config_path=str(config_path),
        )

    def resolve_path(self, relative_path: str | Path) -> Path:
        raw = Path(relative_path)
        if raw.is_absolute():
            raise WorkspaceAccessError("Absolute paths are not allowed")
        candidate = (self.root / raw).resolve(strict=False)
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceAccessError(
                f"Path escapes workspace root: {relative_path}"
            ) from exc
        return candidate

    def list_dir(self, relative_path: str = "", include_hidden: bool = False) -> list[FileEntry]:
        directory = self.resolve_path(relative_path)
        if not directory.exists():
            raise FileNotFoundError(relative_path or ".")
        if not directory.is_dir():
            raise NotADirectoryError(relative_path)

        entries: list[FileEntry] = []
        for child in sorted(
            directory.iterdir(),
            key=lambda item: (not item.is_dir(), item.name.lower()),
        ):
            if not include_hidden and child.name.startswith("."):
                continue
            stat = child.stat()
            rel = child.relative_to(self.root).as_posix()
            entries.append(
                FileEntry(
                    path=rel,
                    kind="directory" if child.is_dir() else "file",
                    size=stat.st_size,
                    modified_at=utc_now_iso_from_epoch(stat.st_mtime),
                )
            )
        return entries

    def get_tree(self, relative_path: str = "", include_hidden: bool = False, max_depth: int = 4) -> TreeEntry:
        root = self.resolve_path(relative_path)
        if not root.exists():
            raise FileNotFoundError(relative_path or ".")
        return self._build_tree(root, include_hidden=include_hidden, max_depth=max_depth)

    def read_text(self, relative_path: str) -> str:
        target = self.resolve_path(relative_path)
        if not target.exists():
            raise FileNotFoundError(relative_path)
        if target.is_dir():
            raise IsADirectoryError(relative_path)
        if target.stat().st_size > TEXT_FILE_SIZE_LIMIT:
            raise WorkspaceTextError("File is too large to read as text")
        raw = target.read_bytes()
        if b"\x00" in raw:
            raise WorkspaceTextError("Binary files are not supported by read_text")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceTextError("File is not valid UTF-8 text") from exc

    def write_text(self, relative_path: str, content: str, overwrite: bool = True) -> FileEntry:
        target = self.resolve_path(relative_path)
        if target.exists() and target.is_dir():
            raise IsADirectoryError(relative_path)
        if target.exists() and not overwrite:
            raise FileExistsError(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return self._entry_for(target)

    def edit_text(
        self,
        relative_path: str,
        search_text: str,
        replace_text: str,
        replace_all: bool = False,
    ) -> FileEntry:
        content = self.read_text(relative_path)
        if search_text not in content:
            raise ValueError("search_text was not found")
        updated = (
            content.replace(search_text, replace_text)
            if replace_all
            else content.replace(search_text, replace_text, 1)
        )
        return self.write_text(relative_path, updated, overwrite=True)

    def move(self, source_path: str, target_path: str, overwrite: bool = False) -> FileEntry:
        source = self.resolve_path(source_path)
        target = self.resolve_path(target_path)
        if not source.exists():
            raise FileNotFoundError(source_path)
        if target.exists() and not overwrite:
            raise FileExistsError(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)
        return self._entry_for(target)

    def delete(self, relative_path: str, recursive: bool = False) -> None:
        target = self.resolve_path(relative_path)
        if not target.exists():
            raise FileNotFoundError(relative_path)
        if target.is_dir():
            if not recursive and any(target.iterdir()):
                raise WorkspaceError("Directory is not empty; pass recursive=True")
            for child in sorted(target.iterdir(), reverse=True):
                child_rel = child.relative_to(self.root).as_posix()
                self.delete(child_rel, recursive=True)
            target.rmdir()
            return
        target.unlink()

    def glob(self, pattern: str, include_hidden: bool = False) -> list[FileEntry]:
        results: list[FileEntry] = []
        for item in self.iter_paths(include_hidden=include_hidden):
            if item.is_dir():
                continue
            rel = item.relative_to(self.root).as_posix()
            if fnmatch(rel, pattern):
                results.append(self._entry_for(item))
        return results

    def grep(self, pattern: str, include_hidden: bool = False) -> list[dict[str, str | int]]:
        hits: list[dict[str, str | int]] = []
        needle = pattern.casefold()
        for item in self.iter_paths(include_hidden=include_hidden):
            if item.is_dir():
                continue
            rel = item.relative_to(self.root).as_posix()
            try:
                content = self.read_text(rel)
            except (UnicodeDecodeError, WorkspaceTextError):
                continue
            for line_number, line in enumerate(content.splitlines(), start=1):
                if needle in line.casefold():
                    hits.append({"path": rel, "line_number": line_number, "line": line})
        return hits

    def iter_paths(self, base_path: str = "", include_hidden: bool = False) -> Iterable[Path]:
        base = self.resolve_path(base_path)
        if not base.exists():
            raise FileNotFoundError(base_path or ".")
        if base.is_file():
            if include_hidden or not any(part.startswith(".") for part in base.relative_to(self.root).parts):
                yield base
            return
        for item in base.rglob("*"):
            rel = item.relative_to(self.root)
            if not include_hidden and any(part.startswith(".") for part in rel.parts):
                continue
            yield item

    def _build_tree(self, root: Path, include_hidden: bool, max_depth: int) -> TreeEntry:
        stat = root.stat()
        children: list[TreeEntry] = []
        if root.is_dir() and max_depth > 0:
            for child in sorted(
                root.iterdir(),
                key=lambda item: (not item.is_dir(), item.name.lower()),
            ):
                if not include_hidden and child.name.startswith("."):
                    continue
                children.append(
                    self._build_tree(child, include_hidden=include_hidden, max_depth=max_depth - 1)
                )
        rel_path = "." if root == self.root else root.relative_to(self.root).as_posix()
        return TreeEntry(
            path=rel_path,
            kind="directory" if root.is_dir() else "file",
            size=stat.st_size,
            modified_at=utc_now_iso_from_epoch(stat.st_mtime),
            children=children,
        )

    def _entry_for(self, path: Path) -> FileEntry:
        stat = path.stat()
        return FileEntry(
            path=path.relative_to(self.root).as_posix(),
            kind="directory" if path.is_dir() else "file",
            size=stat.st_size,
            modified_at=utc_now_iso_from_epoch(stat.st_mtime),
        )


def utc_now_iso_from_epoch(epoch_seconds: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(epoch_seconds, tz=UTC).isoformat()
