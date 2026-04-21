import type {
  AgentEvent,
  ApprovalRequest,
  ConversationCheckpoint,
  ConversationSummary,
  Conversation,
  FileEntry,
  ImportJob,
  MCPInvokeInput,
  MCPInvokeResult,
  MCPServerDefinition,
  MCPServerUpsertInput,
  MCPToolDefinition,
  MCPToolCatalogItem,
  MemoryCandidate,
  LLMSettings,
  LLMTestResult,
  Message,
  NoteDocument,
  NoteMeta,
  Preference,
  ResumeContext,
  SearchHit,
  SkillDefinition,
  SkillUpsertInput,
  TreeEntry,
  WorkspaceMemoryRecord,
  Workspace,
} from "./types";

const API_BASE = "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({ detail: "Request failed" }))) as {
      detail?: string;
    };
    throw new Error(payload.detail ?? `Request failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function createWorkspace(rootPath: string, name?: string): Promise<Workspace> {
  const payload = await request<{ workspace: Workspace }>("/api/workspaces/create", {
    method: "POST",
    body: JSON.stringify({ root_path: rootPath, name }),
  });
  return payload.workspace;
}

export async function openWorkspace(rootPath: string, name?: string): Promise<Workspace> {
  const payload = await request<{ workspace: Workspace }>("/api/workspaces/open", {
    method: "POST",
    body: JSON.stringify({ root_path: rootPath, name }),
  });
  return payload.workspace;
}

export async function getTree(): Promise<TreeEntry> {
  const payload = await request<{ tree: TreeEntry }>("/api/workspaces/tree");
  return payload.tree;
}

export async function listFiles(path = ""): Promise<FileEntry[]> {
  const query = path ? `?path=${encodeURIComponent(path)}` : "";
  const payload = await request<{ entries: FileEntry[] }>(`/api/files${query}`);
  return payload.entries;
}

export async function getFileContent(path: string): Promise<string> {
  const payload = await request<{ content: string }>(
    `/api/files/content?path=${encodeURIComponent(path)}`
  );
  return payload.content;
}

export async function writeFile(path: string, content: string): Promise<void> {
  await request("/api/files/write", {
    method: "POST",
    body: JSON.stringify({ path, content, overwrite: true }),
  });
}

export async function listNotes(path = ""): Promise<NoteMeta[]> {
  const query = path ? `?path=${encodeURIComponent(path)}` : "";
  const payload = await request<{ notes: NoteMeta[] }>(`/api/notes${query}`);
  return payload.notes;
}

export async function getNote(path: string): Promise<NoteDocument> {
  const payload = await request<{ note: NoteDocument }>(
    `/api/notes/${encodeURIComponent(path).replace(/%2F/g, "/")}`
  );
  return payload.note;
}

export async function createNote(
  path: string,
  content: string,
  options: { title?: string; tags?: string[]; summary?: string; related?: string[]; source_type?: string } = {}
): Promise<NoteDocument> {
  const payload = await request<{ note: NoteDocument }>("/api/notes", {
    method: "POST",
    body: JSON.stringify({ path, content, ...options }),
  });
  return payload.note;
}

export async function updateNote(path: string, content: string): Promise<NoteDocument> {
  const payload = await request<{ note: NoteDocument }>(
    `/api/notes/${encodeURIComponent(path).replace(/%2F/g, "/")}`,
    {
      method: "PUT",
      body: JSON.stringify({ content }),
    }
  );
  return payload.note;
}

export async function importFile(
  sourcePath: string,
  destinationDir: string,
  tags: string[] = []
): Promise<{ job: ImportJob; note: NoteDocument }> {
  const payload = await request<{ job: ImportJob; note: NoteDocument }>(
    "/api/imports/file",
    {
      method: "POST",
      body: JSON.stringify({
        source_path: sourcePath,
        destination_dir: destinationDir,
        tags,
      }),
    }
  );
  return payload;
}

export async function importUrl(
  url: string,
  destinationDir: string,
  tags: string[] = []
): Promise<{ job: ImportJob; note: NoteDocument }> {
  const payload = await request<{ job: ImportJob; note: NoteDocument }>(
    "/api/imports/url",
    {
      method: "POST",
      body: JSON.stringify({
        url,
        destination_dir: destinationDir,
        tags,
      }),
    }
  );
  return payload;
}

export async function rebuildSearch(): Promise<void> {
  await request("/api/search/rebuild", { method: "POST", body: JSON.stringify({}) });
}

export async function searchWorkspace(query: string): Promise<SearchHit[]> {
  const payload = await request<{ hits: SearchHit[] }>(
    `/api/search?query=${encodeURIComponent(query)}`
  );
  return payload.hits;
}

export async function getPreferences(): Promise<Preference> {
  const payload = await request<{ preferences: Preference }>("/api/preferences");
  return payload.preferences;
}

export async function updatePreferences(preferences: Partial<Preference>): Promise<Preference> {
  const payload = await request<{ preferences: Preference }>("/api/preferences", {
    method: "PUT",
    body: JSON.stringify(preferences),
  });
  return payload.preferences;
}

export async function listApprovals(): Promise<ApprovalRequest[]> {
  const payload = await request<{ approvals: ApprovalRequest[] }>("/api/approvals");
  return payload.approvals;
}

export async function approveRequest(id: string): Promise<void> {
  await request(`/api/approvals/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function rejectRequest(id: string): Promise<void> {
  await request(`/api/approvals/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function createConversation(title?: string): Promise<Conversation> {
  const payload = await request<{ conversation: Conversation }>("/api/conversations", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
  return payload.conversation;
}

export async function listConversations(includeArchived = false): Promise<Conversation[]> {
  const query = includeArchived ? "?include_archived=true" : "";
  const payload = await request<{ conversations: Conversation[] }>(`/api/conversations${query}`);
  return payload.conversations;
}

export async function listConversationMessages(id: string): Promise<Message[]> {
  const payload = await request<{ messages: Message[] }>(`/api/conversations/${id}/messages`);
  return payload.messages;
}

export async function renameConversation(id: string, title: string): Promise<Conversation> {
  const payload = await request<{ conversation: Conversation }>(`/api/conversations/${id}/rename`, {
    method: "POST",
    body: JSON.stringify({ title }),
  });
  return payload.conversation;
}

export async function archiveConversation(id: string): Promise<Conversation> {
  const payload = await request<{ conversation: Conversation }>(`/api/conversations/${id}/archive`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return payload.conversation;
}

export async function resumeConversation(id: string): Promise<Conversation> {
  const payload = await request<{ conversation: Conversation }>(`/api/conversations/${id}/resume`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return payload.conversation;
}

export async function getConversationSummary(id: string): Promise<ConversationSummary> {
  const payload = await request<{ summary: ConversationSummary }>(`/api/conversations/${id}/summary`);
  return payload.summary;
}

export async function getConversationResumeContext(id: string): Promise<ResumeContext> {
  const payload = await request<{ resume_context: ResumeContext }>(`/api/conversations/${id}/resume-context`);
  return payload.resume_context;
}

export async function compactConversation(id: string): Promise<Conversation> {
  const payload = await request<{ conversation: Conversation }>(`/api/conversations/${id}/compact`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return payload.conversation;
}

export async function createConversationCheckpoint(
  id: string,
  label?: string
): Promise<ConversationCheckpoint> {
  const payload = await request<{ checkpoint: ConversationCheckpoint }>(`/api/conversations/${id}/checkpoint`, {
    method: "POST",
    body: JSON.stringify({ label }),
  });
  return payload.checkpoint;
}

export async function listMemoryCandidates(
  conversationId: string,
  includeResolved = false
): Promise<MemoryCandidate[]> {
  const query = includeResolved ? "?include_resolved=true" : "";
  const payload = await request<{ candidates: MemoryCandidate[] }>(
    `/api/conversations/${conversationId}/memory-candidates${query}`
  );
  return payload.candidates;
}

export async function acceptMemoryCandidate(
  conversationId: string,
  candidateId: string
): Promise<{ candidate: MemoryCandidate; record: WorkspaceMemoryRecord }> {
  return request<{ candidate: MemoryCandidate; record: WorkspaceMemoryRecord }>(
    `/api/conversations/${conversationId}/memory-candidates/${candidateId}/accept`,
    {
      method: "POST",
      body: JSON.stringify({}),
    }
  );
}

export async function rejectMemoryCandidate(
  conversationId: string,
  candidateId: string
): Promise<MemoryCandidate> {
  const payload = await request<{ candidate: MemoryCandidate }>(
    `/api/conversations/${conversationId}/memory-candidates/${candidateId}/reject`,
    {
      method: "POST",
      body: JSON.stringify({}),
    }
  );
  return payload.candidate;
}

export async function listSkills(includeDisabled = false): Promise<SkillDefinition[]> {
  const query = includeDisabled ? "?include_disabled=true" : "";
  const payload = await request<{ skills: SkillDefinition[] }>(`/api/skills${query}`);
  return payload.skills;
}

export async function resolveSkills(input: {
  prompt: string;
  currentNotePath?: string | null;
  activeTags?: string[];
  limit?: number;
}): Promise<SkillDefinition[]> {
  const params = new URLSearchParams();
  params.set("prompt", input.prompt);
  if (input.currentNotePath) {
    params.set("current_note_path", input.currentNotePath);
  }
  for (const tag of input.activeTags ?? []) {
    if (tag.trim()) {
      params.append("active_tags", tag.trim());
    }
  }
  if (typeof input.limit === "number") {
    params.set("limit", String(input.limit));
  }
  const payload = await request<{ skills: SkillDefinition[] }>(`/api/skills/resolve?${params.toString()}`);
  return payload.skills;
}

export async function upsertSkill(skillId: string, input: SkillUpsertInput): Promise<SkillDefinition> {
  const payload = await request<{ skill: SkillDefinition }>(`/api/skills/${encodeURIComponent(skillId)}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
  return payload.skill;
}

export async function deleteSkill(skillId: string): Promise<void> {
  await request(`/api/skills/${encodeURIComponent(skillId)}`, {
    method: "DELETE",
  });
}

export async function listMcpCatalog(): Promise<MCPToolCatalogItem[]> {
  const payload = await request<{ tools: MCPToolCatalogItem[] }>("/api/mcp/catalog");
  return payload.tools;
}

export async function listMcpServers(includeDisabled = false): Promise<MCPServerDefinition[]> {
  const query = includeDisabled ? "?include_disabled=true" : "";
  const payload = await request<{ servers: MCPServerDefinition[] }>(`/api/mcp/servers${query}`);
  return payload.servers;
}

export async function listMcpServerTools(serverId: string): Promise<MCPToolDefinition[]> {
  const payload = await request<{ tools: MCPToolDefinition[] }>(
    `/api/mcp/servers/${encodeURIComponent(serverId)}/tools`
  );
  return payload.tools;
}

export async function upsertMcpServer(
  serverId: string,
  input: MCPServerUpsertInput
): Promise<MCPServerDefinition> {
  const payload = await request<{ server: MCPServerDefinition }>(
    `/api/mcp/servers/${encodeURIComponent(serverId)}`,
    {
      method: "PUT",
      body: JSON.stringify(input),
    }
  );
  return payload.server;
}

export async function deleteMcpServer(serverId: string): Promise<void> {
  await request(`/api/mcp/servers/${encodeURIComponent(serverId)}`, {
    method: "DELETE",
  });
}

export async function invokeMcpTool(
  serverId: string,
  toolName: string,
  input: MCPInvokeInput
): Promise<MCPInvokeResult> {
  const payload = await request<{ result: MCPInvokeResult }>(
    `/api/mcp/servers/${encodeURIComponent(serverId)}/tools/${encodeURIComponent(toolName)}/invoke`,
    {
      method: "POST",
      body: JSON.stringify(input),
    }
  );
  return payload.result;
}

export async function cancelConversationStream(conversationId: string): Promise<boolean> {
  const payload = await request<{ cancelled: boolean }>(`/api/conversations/${conversationId}/cancel`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return payload.cancelled;
}

export async function streamConversation(
  conversationId: string,
  prompt: string,
  currentNotePath: string | null,
  onEvent: (event: AgentEvent) => void | Promise<void>,
  options?: { signal?: AbortSignal }
): Promise<void> {
  const params = new URLSearchParams({ prompt });
  if (currentNotePath) {
    params.set("current_note_path", currentNotePath);
  }
  const response = await fetch(
    `${API_BASE}/api/conversations/${conversationId}/stream?${params.toString()}`,
    { signal: options?.signal }
  );
  if (!response.ok || !response.body) {
    let detail = "";
    try {
      detail = await response.text();
    } catch {
      // ignore body read errors on failure path
    }
    throw new Error(
      `Failed to open SSE stream (status ${response.status})${detail ? `: ${detail.slice(0, 240)}` : ""}`
    );
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const eventChunk of events) {
      const lines = eventChunk
        .split("\n")
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6));
      for (const raw of lines) {
        if (raw === "[DONE]") {
          return;
        }
        let parsed: AgentEvent;
        try {
          parsed = JSON.parse(raw) as AgentEvent;
        } catch (err) {
          console.warn("[sse] dropping malformed frame", err, raw.slice(0, 160));
          continue;
        }
        await onEvent(parsed);
      }
    }
  }
}

export async function getLLMSettings(): Promise<LLMSettings> {
  const payload = await request<{ settings: LLMSettings }>("/api/settings/llm");
  return payload.settings;
}

export async function updateLLMSettings(
  settings: Partial<{ base_url: string; api_key: string; model: string; timeout: number }>
): Promise<LLMSettings> {
  const payload = await request<{ settings: LLMSettings }>("/api/settings/llm", {
    method: "PUT",
    body: JSON.stringify(settings),
  });
  return payload.settings;
}

export async function testLLMConnection(): Promise<LLMTestResult> {
  const payload = await request<{ result: LLMTestResult }>("/api/settings/llm/test", {
    method: "POST",
    body: JSON.stringify({}),
  });
  return payload.result;
}
