"""全局异常到 HTTP 响应的映射。

`register_exception_handlers` 给 FastAPI 注册每种领域异常对应的
`JSONResponse` 状态码和 payload（WorkspaceError -> 400 / NoteError -> 422
/ AgentError -> 500 ...），保证所有接口错误以统一 JSON 格式返回。
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..agent.errors import AgentError
from ..ingest import IngestError
from ..llm import LLMError
from ..notes import NoteError, NoteFormatError
from ..providers import ProviderError
from ..search import SearchError
from ..services.memory import MemoryError
from ..stores.approvals import ApprovalError
from ..workspace_fs import (
    WorkspaceAccessError,
    WorkspaceError,
    WorkspaceNotFoundError,
    WorkspaceTextError,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(WorkspaceNotFoundError)
    async def _workspace_not_found(_: Request, exc: WorkspaceNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(WorkspaceAccessError)
    async def _workspace_access(_: Request, exc: WorkspaceAccessError):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(WorkspaceTextError)
    async def _workspace_text(_: Request, exc: WorkspaceTextError):
        return JSONResponse(status_code=415, content={"detail": str(exc)})

    @app.exception_handler(NoteFormatError)
    async def _note_format(_: Request, exc: NoteFormatError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(NoteError)
    async def _note_error(_: Request, exc: NoteError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    for error_type in (IngestError, SearchError, MemoryError, AgentError, ApprovalError, LLMError, ProviderError):
        app.add_exception_handler(error_type, _handle_bad_request)

    app.add_exception_handler(FileNotFoundError, _handle_not_found)
    app.add_exception_handler(FileExistsError, _handle_conflict)
    app.add_exception_handler(NotADirectoryError, _handle_directory_error)
    app.add_exception_handler(IsADirectoryError, _handle_directory_error)
    app.add_exception_handler(WorkspaceError, _handle_bad_request)
    app.add_exception_handler(ValueError, _handle_bad_request)


async def _handle_bad_request(_: Request, exc: Exception):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


async def _handle_not_found(_: Request, exc: FileNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def _handle_conflict(_: Request, exc: FileExistsError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


async def _handle_directory_error(_: Request, exc: Exception):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
