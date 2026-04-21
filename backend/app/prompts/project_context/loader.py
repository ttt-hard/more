"""项目上下文文件加载器。

查找 `AGENTS.md / CLAUDE.md / CONTEXT.md` 中第一个存在的项目规范文件。
查找顺序：如果给了 `current_note_path`，从其父目录开始向上逐层扫描到
workspace root（最靠近 note 的规范优先）；否则只看 workspace root。
文件名优先级按 `PROJECT_CONTEXT_FILENAMES` 顺序（AGENTS.md > CLAUDE.md >
CONTEXT.md）。"首个命中即停止"避免把 monorepo 里所有子项目的规范全部
塞进 prompt。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...workspace_fs import WorkspaceError, WorkspaceFS

PROJECT_CONTEXT_FILENAMES: tuple[str, ...] = ("AGENTS.md", "CLAUDE.md", "CONTEXT.md")


@dataclass(frozen=True)
class ProjectContextEntry:
    filepath: str
    content: str
    scope: str = "project"


def _iter_ancestors(start: Path, stop: Path) -> list[Path]:
    """返回从 start 到 stop（含 stop）的目录链。

    要求 start 位于 stop 的子树内或等于 stop；否则直接退化为 `[stop]`，
    避免越出 workspace 根。
    """
    start_resolved = start.resolve()
    stop_resolved = stop.resolve()

    if start_resolved != stop_resolved and stop_resolved not in start_resolved.parents:
        return [stop_resolved]

    dirs: list[Path] = []
    current = start_resolved
    while True:
        dirs.append(current)
        if current == stop_resolved:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    return dirs


def load_project_context(
    fs: WorkspaceFS,
    *,
    current_note_path: str | None = None,
) -> list[ProjectContextEntry]:
    """扫描 workspace，返回命中的项目约定文件条目列表。

    - `current_note_path`：可选，workspace 相对路径。给定后以该文件所在
      目录为起点向上查找；否则从 workspace root 开始。
    - 返回：找到即返回**单条**（首个命中），否则空列表。
    """
    workspace_root = fs.root

    start: Path = workspace_root
    if current_note_path:
        try:
            note_abs = fs.resolve_path(current_note_path)
        except WorkspaceError:
            note_abs = None
        if note_abs is not None and note_abs.exists():
            start = note_abs.parent if note_abs.is_file() else note_abs

    for directory in _iter_ancestors(start, workspace_root):
        for filename in PROJECT_CONTEXT_FILENAMES:
            candidate = directory / filename
            if not candidate.is_file():
                continue
            try:
                content = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            relative = candidate.relative_to(workspace_root).as_posix()
            return [
                ProjectContextEntry(
                    filepath=relative,
                    content=content,
                    scope="project",
                )
            ]

    return []


__all__ = ["PROJECT_CONTEXT_FILENAMES", "ProjectContextEntry", "load_project_context"]
