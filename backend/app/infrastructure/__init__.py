"""后端横切基础设施。

这个包对外集中暴露底层构件（文件锁、工作区 I/O 原语、MCP 传输层、
文件变更监听接口）作为统一 import 入口。它刻意从 `app.workspace_fs`
和 `app.stores.preferences` 重新导出那些跨层通用的类型，让调用方始终
通过 `app.infrastructure.*` 拿到稳定路径，避免复制实现。
"""

from ..stores.preferences import LLMSettingsStore, PreferenceStore
from ..workspace_fs import (
    WorkspaceAccessError,
    WorkspaceError,
    WorkspaceFS,
    WorkspaceNotFoundError,
    WorkspaceTextError,
    utc_now_iso_from_epoch,
)
from .file_lock import locked_path
from .watcher import NoopWorkspaceWatcher, WorkspaceChange, WorkspaceWatcher

__all__ = [
    "LLMSettingsStore",
    "NoopWorkspaceWatcher",
    "PreferenceStore",
    "WorkspaceAccessError",
    "WorkspaceChange",
    "WorkspaceError",
    "WorkspaceFS",
    "WorkspaceNotFoundError",
    "WorkspaceTextError",
    "WorkspaceWatcher",
    "locked_path",
    "utc_now_iso_from_epoch",
]
