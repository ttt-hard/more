"""工作区文件端点。

面向前端文件树 / 编辑器暴露 `WorkspaceFS` 的能力：列目录 / 读文本 /
写文本 / 编辑 / glob / grep / move / delete（后两者会在需要时转给
ApprovalStore 创建审批请求）。
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from ...stores.approvals import ApprovalStore
from ...workspace_fs import WorkspaceFS
from ..deps import get_approval_store, get_workspace_fs
from ..schemas import DeletePathRequest, EditFileRequest, MovePathRequest, WriteFileRequest

router = APIRouter(prefix="/api/files")


@router.get("")
def list_files(path: str = "", include_hidden: bool = False, fs: WorkspaceFS = Depends(get_workspace_fs)) -> dict[str, object]:
    return {"entries": [asdict(entry) for entry in fs.list_dir(path, include_hidden=include_hidden)]}


@router.get("/content")
def get_file_content(path: str, fs: WorkspaceFS = Depends(get_workspace_fs)) -> dict[str, str]:
    return {"path": path, "content": fs.read_text(path)}


@router.post("/write")
def write_file(request: WriteFileRequest, fs: WorkspaceFS = Depends(get_workspace_fs)) -> dict[str, object]:
    entry = fs.write_text(request.path, request.content, overwrite=request.overwrite)
    return {"entry": asdict(entry)}


@router.post("/edit")
def edit_file(request: EditFileRequest, fs: WorkspaceFS = Depends(get_workspace_fs)) -> dict[str, object]:
    entry = fs.edit_text(
        request.path,
        request.search_text,
        request.replace_text,
        replace_all=request.replace_all,
    )
    return {"entry": asdict(entry)}


@router.post("/move")
def move_file(
    request: MovePathRequest,
    fs: WorkspaceFS = Depends(get_workspace_fs),
    approval_store: ApprovalStore = Depends(get_approval_store),
) -> dict[str, object]:
    if approval_store.requires_move_approval(
        request.source_path,
        request.target_path,
        request.overwrite,
    ):
        approval = approval_store.create_request(
            action="move_path",
            targets=[request.source_path, request.target_path],
            reason="Overwriting or moving directories requires confirmation.",
            payload={
                "source_path": request.source_path,
                "target_path": request.target_path,
                "overwrite": request.overwrite,
            },
            source="api",
        )
        return {"requires_approval": True, "approval": asdict(approval)}
    entry = fs.move(request.source_path, request.target_path, overwrite=request.overwrite)
    return {"entry": asdict(entry)}


@router.post("/delete")
def delete_file(
    request: DeletePathRequest,
    fs: WorkspaceFS = Depends(get_workspace_fs),
    approval_store: ApprovalStore = Depends(get_approval_store),
) -> dict[str, object]:
    if approval_store.requires_delete_approval(request.path, request.recursive):
        approval = approval_store.create_request(
            action="delete_path",
            targets=[request.path],
            reason="Deleting files requires confirmation.",
            payload={"path": request.path, "recursive": request.recursive},
            source="api",
        )
        return {"requires_approval": True, "approval": asdict(approval)}
    fs.delete(request.path, recursive=request.recursive)
    return {"deleted": request.path}


@router.get("/glob")
def glob_files(pattern: str, include_hidden: bool = False, fs: WorkspaceFS = Depends(get_workspace_fs)) -> dict[str, object]:
    return {"entries": [asdict(entry) for entry in fs.glob(pattern, include_hidden=include_hidden)]}


@router.get("/grep")
def grep_files(pattern: str, include_hidden: bool = False, fs: WorkspaceFS = Depends(get_workspace_fs)) -> dict[str, object]:
    return {"hits": fs.grep(pattern, include_hidden=include_hidden)}
