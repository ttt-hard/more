"""工作区变更监听接口。

`WorkspaceWatcher` 是文件系统变更事件的 Protocol，用于未来接入
watchdog 触发索引自动更新；当前实现只有 `NoopWorkspaceWatcher`，由
`api/deps` 默认装配，保持接口占位。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WorkspaceChange:
    path: str
    change_type: str


class WorkspaceWatcher(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def poll(self) -> list[WorkspaceChange]: ...


class NoopWorkspaceWatcher:
    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def poll(self) -> list[WorkspaceChange]:
        return []
