"""所有 HTTP 路由的聚合导出。

按资源拆成独立文件，每个模块暴露一个 `router: APIRouter`，`main.py`
逐一 `app.include_router(...)` 挂载。
"""

from .approvals import router as approvals_router
from .conversations import router as conversations_router
from .files import router as files_router
from .ingest import router as ingest_router
from .mcp import router as mcp_router
from .memory import router as memory_router
from .notes import router as notes_router
from .search import router as search_router
from .settings import router as settings_router
from .skills import router as skills_router
from .workspace import router as workspace_router

__all__ = [
    "approvals_router",
    "conversations_router",
    "files_router",
    "ingest_router",
    "mcp_router",
    "memory_router",
    "notes_router",
    "search_router",
    "settings_router",
    "skills_router",
    "workspace_router",
]
