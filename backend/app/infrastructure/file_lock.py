"""基于路径的可重入锁。

`locked_path(path)` 为同一 resolve 后的路径返回同一把 `RLock`，做为
store / search / ingest 等所有文件 RMW 场景的协调点；RLock 可重入意味
着同线程嵌套调用（`append_message` 外层锁 + 内层 `_write_metadata` 再
锁）不会死锁。
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import Lock, RLock

_REGISTRY_GUARD = Lock()
_LOCKS: dict[str, RLock] = {}


@contextmanager
def locked_path(path: str | Path):
    key = str(Path(path).resolve())
    with _REGISTRY_GUARD:
        lock = _LOCKS.setdefault(key, RLock())
    with lock:
        yield
