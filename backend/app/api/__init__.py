"""API 子包公开入口。

只暴露 `AppState` 单例（`state`），其余 router / schema / deps 由
`main.create_app` 按需组装。
"""

from .deps import state

__all__ = ["state"]
