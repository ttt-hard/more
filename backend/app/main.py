"""FastAPI 应用入口。

`create_app()` 组装 CORS、全局异常处理、以及所有路由（workspace / files /
notes / ingest / search / memory / conversations / approvals / settings /
skills / mcp）。顶层 `app = create_app()` 直接供 uvicorn 启动。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# CRITICAL: `init_langfuse()` must run BEFORE any other app module is
# imported. The `@observe(...)` decorators in coordinator / runtime /
# memory / litellm_provider are evaluated at *import time* — if
# `_LANGFUSE_ACTIVE` is still False when `from .api.routes import ...`
# executes, every decorator resolves to the no-op identity shim and stays
# that way for the rest of the process lifetime. Calling it later inside
# `create_app()` would activate the SDK but by then the damage is done:
# decorators are already bound, `update_current_trace` can't find a span,
# and the Langfuse UI stays empty while the error log fills with
# "No active span in current context".
from .observability_langfuse import init_langfuse

init_langfuse()

# Now it's safe to pull in modules that host `@observe`-decorated code.
from .api.deps import state  # noqa: E402
from .api.errors import register_exception_handlers  # noqa: E402
from .api.routes import (  # noqa: E402
    approvals_router,
    conversations_router,
    files_router,
    ingest_router,
    mcp_router,
    memory_router,
    notes_router,
    search_router,
    settings_router,
    skills_router,
    workspace_router,
)


def create_app() -> FastAPI:
    # Guard against a dev tool re-importing app.main after env changed;
    # the first successful init flips the module-level flag so this is
    # a cheap no-op.
    init_langfuse()

    app = FastAPI(title="more backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(workspace_router)
    app.include_router(files_router)
    app.include_router(notes_router)
    app.include_router(ingest_router)
    app.include_router(search_router)
    app.include_router(memory_router)
    app.include_router(conversations_router)
    app.include_router(approvals_router)
    app.include_router(settings_router)
    app.include_router(skills_router)
    app.include_router(mcp_router)
    return app


app = create_app()

__all__ = ["app", "create_app", "state"]
