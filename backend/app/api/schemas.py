"""API 请求 / 响应模型（Pydantic）。

集中定义所有 HTTP 接口的入参模型（CreateConversationRequest /
RenameConversationRequest / ImportFileRequest / ...），供 FastAPI 做
自动校验。返回值通常直接 `asdict(domain_dataclass)`，不在此定义。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkspaceRequest(BaseModel):
    root_path: str = Field(..., description="Absolute path to the workspace root")
    name: str | None = Field(default=None, description="Optional workspace display name")


class WriteFileRequest(BaseModel):
    path: str
    content: str
    overwrite: bool = True


class EditFileRequest(BaseModel):
    path: str
    search_text: str
    replace_text: str
    replace_all: bool = False


class MovePathRequest(BaseModel):
    source_path: str
    target_path: str
    overwrite: bool = False


class DeletePathRequest(BaseModel):
    path: str
    recursive: bool = False


class CreateNoteRequest(BaseModel):
    path: str
    content: str = ""
    title: str | None = None
    tags: list[str] = Field(default_factory=list)
    summary: str | None = None
    related: list[str] = Field(default_factory=list)
    source_type: str = "manual"


class UpdateNoteRequest(BaseModel):
    content: str | None = None
    title: str | None = None
    tags: list[str] | None = None
    summary: str | None = None
    related: list[str] | None = None
    source_type: str | None = None


class RebuildSearchRequest(BaseModel):
    pass


class ImportFileRequest(BaseModel):
    source_path: str
    destination_dir: str = "Inbox"
    title: str | None = None
    tags: list[str] = Field(default_factory=list)
    summary: str | None = None


class ImportUrlRequest(BaseModel):
    url: str
    destination_dir: str = "Inbox"
    title: str | None = None
    tags: list[str] = Field(default_factory=list)
    summary: str | None = None


class UpdatePreferencesRequest(BaseModel):
    language: str | None = None
    answer_style: str | None = None
    default_note_dir: str | None = None
    theme: str | None = None


class CreateConversationRequest(BaseModel):
    title: str | None = None


class RenameConversationRequest(BaseModel):
    title: str = Field(..., min_length=1)


class ConversationPinRequest(BaseModel):
    pinned: bool = True


class ConversationLabelsRequest(BaseModel):
    labels: list[str] = Field(default_factory=list)


class ConversationCheckpointRequest(BaseModel):
    label: str | None = None


class SkillUpsertRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    prompt_prefix: str = ""
    when_to_use: str = ""
    tool_subset: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    enabled: bool = True


class MCPToolRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    input_schema: dict[str, object] = Field(default_factory=dict)
    execution_mode: str = "builtin"
    builtin_action: str = "echo"
    enabled: bool = True


class MCPServerUpsertRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    transport: str = "builtin"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    working_directory: str | None = None
    enabled: bool = True
    tools: list[MCPToolRequest] = Field(default_factory=list)


class MCPInvokeRequest(BaseModel):
    args: dict[str, object] = Field(default_factory=dict)
    prompt: str = ""
    current_note_path: str | None = None
    default_note_dir: str = "Notes"


class ApprovalDecisionRequest(BaseModel):
    pass


class UpdateLLMSettingsRequest(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout: float | None = None
