"""活动运行注册表。

按 `conversation_id` 维护进行中的 `CancellationToken`，让 HTTP 端点
`POST /api/conversations/{id}/cancel` 能给后台流式 run 发取消信号。
SSE 路由在 run 开始时 `register`、结束在 `finally` 里 `unregister`。
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from .runtime_control import CancellationToken


@dataclass
class ActiveRunHandle:
    conversation_id: str
    token: CancellationToken


class ActiveRunRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._handles: dict[str, ActiveRunHandle] = {}

    def register(self, conversation_id: str, token: CancellationToken) -> None:
        with self._lock:
            self._handles[conversation_id] = ActiveRunHandle(conversation_id=conversation_id, token=token)

    def get(self, conversation_id: str) -> ActiveRunHandle | None:
        with self._lock:
            return self._handles.get(conversation_id)

    def cancel(self, conversation_id: str, reason: str = "") -> bool:
        with self._lock:
            handle = self._handles.get(conversation_id)
        if handle is None:
            return False
        handle.token.cancel(reason)
        return True

    def unregister(self, conversation_id: str, token: CancellationToken | None = None) -> None:
        with self._lock:
            handle = self._handles.get(conversation_id)
            if handle is None:
                return
            if token is not None and handle.token is not token:
                return
            self._handles.pop(conversation_id, None)


active_run_registry = ActiveRunRegistry()


__all__ = ["ActiveRunHandle", "ActiveRunRegistry", "active_run_registry"]
