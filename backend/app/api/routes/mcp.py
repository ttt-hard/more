"""MCP server 管理端点。

列 / 增 / 改 / 删 MCP 服务器配置，触发 `MCPService.sync_server` 拉取其
工具清单并在运行时热注册到 agent 工具表。
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from ...ingest import IngestService
from ...mcp.service import MCPService
from ...tools.base import ToolContext
from ...services.memory import MemoryService
from ...notes import NoteService
from ...services.search import SearchService
from ...stores import ApprovalStorePort
from ...workspace_fs import WorkspaceFS
from ..deps import (
    get_approval_store,
    get_ingest_service,
    get_mcp_service,
    get_memory_service,
    get_note_service,
    get_search_service,
    get_workspace_fs,
)
from ..schemas import MCPInvokeRequest, MCPServerUpsertRequest

router = APIRouter(prefix="/api/mcp")


@router.get("/catalog")
def list_mcp_catalog(
    mcp_service: MCPService = Depends(get_mcp_service),
) -> dict[str, object]:
    return {"tools": mcp_service.list_tool_catalog()}


@router.get("/servers")
def list_mcp_servers(
    include_disabled: bool = Query(default=False),
    mcp_service: MCPService = Depends(get_mcp_service),
) -> dict[str, object]:
    servers = mcp_service.list_servers(include_disabled=include_disabled)
    return {"servers": [asdict(server) for server in servers]}


@router.put("/servers/{server_id}")
def upsert_mcp_server(
    server_id: str,
    request: MCPServerUpsertRequest,
    mcp_service: MCPService = Depends(get_mcp_service),
) -> dict[str, object]:
    server = mcp_service.upsert_server(
        server_id,
        name=request.name,
        description=request.description,
        transport=request.transport,
        command=request.command,
        args=request.args,
        env=request.env,
        working_directory=request.working_directory,
        enabled=request.enabled,
        tools=[tool.model_dump() for tool in request.tools],
    )
    return {"server": asdict(server)}


@router.delete("/servers/{server_id}")
def delete_mcp_server(
    server_id: str,
    mcp_service: MCPService = Depends(get_mcp_service),
) -> dict[str, object]:
    mcp_service.delete_server(server_id)
    return {"deleted": True, "server_id": server_id}


@router.post("/servers/{server_id}/sync")
def sync_mcp_server(
    server_id: str,
    mcp_service: MCPService = Depends(get_mcp_service),
) -> dict[str, object]:
    server = mcp_service.sync_server(server_id)
    return {"server": asdict(server), "tools": mcp_service.list_server_tools(server_id)}


@router.get("/servers/{server_id}/tools")
def list_mcp_server_tools(
    server_id: str,
    mcp_service: MCPService = Depends(get_mcp_service),
) -> dict[str, object]:
    return {"tools": mcp_service.list_server_tools(server_id)}


@router.post("/servers/{server_id}/tools/{tool_name}/invoke")
def invoke_mcp_tool(
    server_id: str,
    tool_name: str,
    request: MCPInvokeRequest,
    fs: WorkspaceFS = Depends(get_workspace_fs),
    note_service: NoteService = Depends(get_note_service),
    search_service: SearchService = Depends(get_search_service),
    ingest_service: IngestService = Depends(get_ingest_service),
    memory_service: MemoryService = Depends(get_memory_service),
    approval_store: ApprovalStorePort = Depends(get_approval_store),
    mcp_service: MCPService = Depends(get_mcp_service),
) -> dict[str, object]:
    result = mcp_service.execute_tool(
        server_id,
        tool_name,
        request.args,
        ToolContext(
            fs=fs,
            note_service=note_service,
            search_service=search_service,
            ingest_service=ingest_service,
            memory_service=memory_service,
            approval_store=approval_store,
            prompt=request.prompt,
            current_note_path=request.current_note_path,
            default_note_dir=request.default_note_dir,
        ),
    )
    return {"result": asdict(result)}
