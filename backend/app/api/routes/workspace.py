"""工作区激活端点。

`POST /api/workspace/activate` 用给定的根路径构造 `WorkspaceFS`、bootstrap
默认目录结构，并把它存进 `AppState` 作为后续请求共享的工作区。
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Query

from ...workspace_fs import WorkspaceFS
from ..deps import state
from ..schemas import WorkspaceRequest

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/workspaces/create")
def create_workspace(request: WorkspaceRequest) -> dict[str, object]:
    root = Path(request.root_path).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    fs = WorkspaceFS(root)
    workspace = fs.bootstrap(name=request.name)
    state.workspace_fs = fs
    return {"workspace": asdict(workspace)}


@router.post("/workspaces/open")
def open_workspace(request: WorkspaceRequest) -> dict[str, object]:
    fs = WorkspaceFS(request.root_path)
    workspace = fs.bootstrap(name=request.name)
    state.workspace_fs = fs
    return {"workspace": asdict(workspace)}


@router.get("/workspaces/tree")
def get_workspace_tree(include_hidden: bool = False, max_depth: int = Query(default=4, ge=1, le=8)) -> dict[str, object]:
    fs = state.require_workspace()
    return {"tree": asdict(fs.get_tree(include_hidden=include_hidden, max_depth=max_depth))}
