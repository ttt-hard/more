export type Workspace = {
  name: string;
  root_path: string;
  config_path: string;
};

export type FileEntry = {
  path: string;
  kind: "file" | "directory";
  size: number;
  modified_at: string;
};

export type TreeEntry = {
  path: string;
  kind: "file" | "directory";
  size: number;
  modified_at: string;
  children: TreeEntry[];
};

export type NoteMeta = {
  id: string;
  title: string;
  relative_path: string;
  tags: string[];
  summary: string;
  related: string[];
  updated_at: string;
  source_type: string;
};

export type NoteDocument = {
  meta: NoteMeta;
  content: string;
};

export type SearchHit = {
  path: string;
  kind: string;
  title: string;
  score: number;
  snippet: string;
};

export type Preference = {
  language: string;
  answer_style: string;
  default_note_dir: string;
  theme: string;
};

export type WorkspaceMemoryRecord = {
  id: string;
  kind: string;
  value: string;
  confidence: number;
  source_thread_id: string;
  source_message_id: string;
  created_at: string;
  updated_at: string;
  status: string;
};

export type MemoryCandidate = {
  id: string;
  kind: string;
  value: string;
  confidence: number;
  source_thread_id: string;
  source_message_id: string;
  created_at: string;
  status: string;
};

export type SkillDefinition = {
  id: string;
  name: string;
  description: string;
  prompt_prefix: string;
  when_to_use: string;
  tool_subset: string[];
  examples: string[];
  keywords: string[];
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type SkillUpsertInput = {
  name: string;
  description: string;
  prompt_prefix: string;
  when_to_use: string;
  tool_subset: string[];
  examples: string[];
  keywords: string[];
  enabled: boolean;
};

export type MCPToolDefinition = {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  execution_mode: string;
  builtin_action: string;
  enabled: boolean;
  action_name?: string;
};

export type MCPServerDefinition = {
  id: string;
  name: string;
  description: string;
  transport: string;
  command: string;
  args: string[];
  env: Record<string, string>;
  working_directory: string | null;
  enabled: boolean;
  tools: MCPToolDefinition[];
  created_at: string;
  updated_at: string;
};

export type MCPServerUpsertInput = {
  name: string;
  description: string;
  transport: string;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  working_directory?: string | null;
  enabled: boolean;
  tools: MCPToolDefinition[];
};

export type MCPToolCatalogItem = {
  name: string;
  server_id: string;
  tool_name: string;
  description: string;
  kind: string;
  approval_gated: boolean;
  input_schema: Record<string, unknown>;
  transport: string;
  execution_mode: string;
};

export type MCPInvokeInput = {
  args: Record<string, unknown>;
  prompt?: string;
  current_note_path?: string | null;
  default_note_dir?: string;
};

export type MCPInvokeResult = {
  ok: boolean;
  tool: string;
  summary: string;
  citations: string[];
  events: Record<string, unknown>[];
  payload: Record<string, unknown>;
  requires_approval: boolean;
  task_state: string;
  run_status: string;
  error?: string | null;
};

export type ApprovalRequest = {
  id: string;
  action: string;
  targets: string[];
  reason: string;
  status: string;
  created_at: string;
  payload: Record<string, unknown>;
  source: string;
};

export type ImportJob = {
  id: string;
  source_type: string;
  source_ref: string;
  status: string;
  output_path: string;
  created_at: string;
};

export type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at?: string;
  status?: string;
  archived_at?: string | null;
  active_note_path?: string | null;
  summary?: string;
  token_estimate?: number;
  compacted_token_estimate?: number;
  compression_state?: string;
  compression_count?: number;
  last_compacted_at?: string | null;
  labels?: string[];
  pinned?: boolean;
};

export type ConversationCheckpoint = {
  id: string;
  conversation_id: string;
  label: string;
  summary: string;
  token_estimate: number;
  active_note_path: string | null;
  created_at: string;
};

export type MessageRole = "user" | "assistant" | "system" | "tool";

export type Message = {
  id: string;
  role: MessageRole;
  content: string;
  citations: string[];
  tool_calls: string[];
  created_at: string;
  // Transcript of the reasoning/thinking stream produced while this message
  // was being generated (reasoning_delta chunks concatenated). Persisted on
  // the backend so we can rehydrate the thought panel when the user reopens
  // an older conversation. Optional for backward compatibility with messages
  // written before the field was added.
  reasoning?: string;
};

export type ResumeContext = {
  conversation: Conversation;
  budget: Record<string, unknown>;
  recent_messages: Message[];
  active_note: NoteMeta | null;
  workspace_memory_refs: WorkspaceMemoryRecord[];
  checkpoints: ConversationCheckpoint[];
};

export type ConversationSummary = {
  conversation: Conversation;
  budget: Record<string, unknown>;
  summary_state: string;
  active_note: NoteMeta | null;
  workspace_memory_refs: WorkspaceMemoryRecord[];
};

export type AgentEvent =
  | { type: "task_status"; task: Record<string, unknown>; run: Record<string, unknown> }
  | { type: "retrieval_hits"; hits: SearchHit[] }
  | { type: "message_start"; conversation_id: string }
  | {
      type: "reasoning_step";
      kind: "phase" | "tool" | "retrieval" | "fallback" | "retry" | "recovered" | "error";
      status: "active" | "done" | "error";
      title: string;
      detail?: string;
    }
  | { type: "phase_status"; phase: "planning" | "tool" | "answering"; label: string; detail?: string }
  | { type: "tool_started"; tool: string; target?: string; query?: string }
  | { type: "tool_finished"; tool: string; target?: string; query?: string }
  | { type: "tool_failed"; tool: string; detail: string; step?: number; attempt?: number }
  | { type: "retrying"; stage: string; attempt: number; detail?: string }
  | { type: "recovered"; stage: string; attempt: number }
  | { type: "fallback_used"; planner: string; reason: string }
  | { type: "file_written"; path: string }
  | { type: "note_created"; note: NoteMeta }
  | { type: "note_updated"; note: NoteMeta }
  | { type: "approval_required"; approval: ApprovalRequest }
  | { type: "token"; text: string }
  | { type: "stream_rollback"; text: string }
  | { type: "reasoning_delta"; text: string }
  | { type: "message_done"; message: Message }
  | { type: "done"; conversation_id: string }
  | { type: "error"; detail: string };

export type LLMSettings = {
  base_url: string;
  api_key_set: boolean;
  api_key_preview: string;
  model: string;
  timeout: number;
  is_configured: boolean;
};

export type LLMTestResult = {
  ok: boolean;
  error?: string;
  model?: string;
  provider?: string;
  latency_ms?: number;
  status_code?: number;
};
