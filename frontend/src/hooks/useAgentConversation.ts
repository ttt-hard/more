import { create } from "zustand";

import {
  acceptMemoryCandidate,
  archiveConversation as archiveConversationApi,
  cancelConversationStream,
  compactConversation,
  createConversation,
  createConversationCheckpoint,
  getConversationResumeContext,
  getConversationSummary,
  listConversationMessages,
  listConversations,
  listMemoryCandidates,
  rejectMemoryCandidate,
  renameConversation as renameConversationApi,
  streamConversation,
} from "../api";
import { GLOBAL_DRAFT_KEY, messageFromError } from "../lib/more";
import { useUiStore } from "../stores/uiStore";
import { useWorkspaceStore } from "../stores/workspaceStore";
import type {
  AgentEvent,
  Conversation,
  ConversationSummary,
  MemoryCandidate,
  Message,
  MessageRole,
  ResumeContext,
  Workspace,
} from "../types";

type StreamStatus = "idle" | "streaming" | "error";

export type ReasoningStep = {
  id: string;
  kind: "phase" | "tool" | "retrieval" | "fallback" | "retry" | "recovered" | "error";
  status: "active" | "done" | "error";
  title: string;
  detail?: string;
};

export type ThinkingState = {
  content: string;
  startedAt: number | null;
  durationMs: number | null;
  active: boolean;
  expanded: boolean;
};

export type MessageTrace = {
  reasoningSteps: ReasoningStep[];
  reasoningExpanded: boolean;
  thinking: ThinkingState;
};

type AgentConversationState = {
  conversation: Conversation | null;
  conversations: Conversation[];
  messages: Message[];
  prompt: string;
  streamStatus: StreamStatus;
  conversationSummary: ConversationSummary | null;
  resumeContext: ResumeContext | null;
  memoryCandidates: MemoryCandidate[];
  reasoningSteps: ReasoningStep[];
  reasoningExpanded: boolean;
  thinking: ThinkingState;
  messageTraces: Record<string, MessageTrace>;
  streamingMessageId: string | null;
  pendingDraftCapture: boolean;
  threadLoading: boolean;
  threadBusyAction: string;
  checkpointLabel: string;
  setPrompt: (value: string) => void;
  setReasoningExpanded: (value: boolean) => void;
  setThinkingExpanded: (value: boolean) => void;
  setMessageReasoningExpanded: (messageId: string, expanded: boolean) => void;
  setMessageThinkingExpanded: (messageId: string, expanded: boolean) => void;
  setCheckpointLabel: (value: string) => void;
  cancelStream: () => Promise<void>;
  resetForWorkspace: (workspace: Workspace) => Promise<Conversation>;
  refreshConversations: () => Promise<Conversation[]>;
  createNewConversation: (title?: string) => Promise<Conversation | null>;
  switchConversation: (conversationId: string) => Promise<void>;
  renameConversation: (conversationId: string, title: string) => Promise<void>;
  archiveConversation: (conversationId: string) => Promise<void>;
  sendPrompt: (prompt: string, options?: { captureDraft?: boolean }) => Promise<void>;
  generateDraft: () => Promise<void>;
  refreshThreadArtifacts: () => Promise<void>;
  compactThread: () => Promise<void>;
  createCheckpoint: () => Promise<void>;
  acceptMemoryCandidate: (candidateId: string) => Promise<void>;
  rejectMemoryCandidate: (candidateId: string) => Promise<void>;
};

const EMPTY_THINKING: ThinkingState = {
  content: "",
  startedAt: null,
  durationMs: null,
  active: false,
  expanded: false,
};

// Rebuild per-message traces from a freshly fetched list of messages so that
// when the user reopens a conversation, each assistant bubble can still show
// its "thinking" panel. The live-streaming machinery writes into
// `state.thinking` on the store during a turn and snapshots it into
// `messageTraces[id]` when the turn ends, but those snapshots are purely
// in-memory: they evaporate when the user navigates away or refreshes. The
// backend now persists the concatenated reasoning text on each Message, so
// we map that back into a trace here. We leave `reasoningSteps` empty on
// rehydrated traces because the per-step metadata (kind/status/timing) is
// not persisted — only the narrative is — and showing a phantom empty step
// list would be worse than simply not rendering the "reasoning steps" chip
// for historical messages.
function buildHistoricalMessageTraces(messages: Message[]): Record<string, MessageTrace> {
  const traces: Record<string, MessageTrace> = {};
  for (const message of messages) {
    if (message.role !== "assistant") continue;
    const reasoning = message.reasoning ?? "";
    if (!reasoning) continue;
    traces[message.id] = {
      reasoningSteps: [],
      reasoningExpanded: false,
      thinking: {
        content: reasoning,
        startedAt: null,
        durationMs: null,
        active: false,
        // Collapsed by default: historical thinking is auxiliary, the final
        // answer is what the user came back for. The user can click the
        // header to expand if they want to re-read the reasoning.
        expanded: false,
      },
    };
  }
  return traces;
}

let activeStreamAbortController: AbortController | null = null;

function buildLocalMessage(role: MessageRole, content: string): Message {
  const id =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `local-${Date.now()}`;
  return {
    id,
    role,
    content,
    citations: [],
    tool_calls: [],
    created_at: new Date().toISOString(),
  };
}

type StreamBufferState = {
  buffer: string;
  frameId: number | null;
};

const streamMessageState: StreamBufferState = {
  buffer: "",
  frameId: null,
};

function buildReasoningStep(
  kind: ReasoningStep["kind"],
  status: ReasoningStep["status"],
  title: string,
  detail?: string
): ReasoningStep {
  const id =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `reasoning-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  return {
    id,
    kind,
    status,
    title,
    detail,
  };
}

function appendReasoningStep(step: ReasoningStep): void {
  useAgentConversationStore.setState((state) => ({
    reasoningSteps: [...state.reasoningSteps, step].slice(-10),
  }));
}

// Snapshot the current live reasoning + thinking onto the supplied message id
// (or the store's current streamingMessageId) and clear the live globals so the
// next turn starts with a clean slate. Returns the produced trace for callers
// that need further work.
function snapshotCurrentTraceIntoStore(options?: {
  targetMessageId?: string | null;
  deletePreviousId?: string | null;
}): void {
  useAgentConversationStore.setState((state) => {
    const target = options?.targetMessageId ?? state.streamingMessageId;
    const nextTraces = { ...state.messageTraces };
    if (options?.deletePreviousId && options.deletePreviousId !== target) {
      delete nextTraces[options.deletePreviousId];
    }
    if (target) {
      const resolvedDuration =
        state.thinking.durationMs !== null
          ? state.thinking.durationMs
          : state.thinking.startedAt !== null
          ? Date.now() - state.thinking.startedAt
          : null;
      nextTraces[target] = {
        reasoningSteps: state.reasoningSteps,
        reasoningExpanded: false,
        thinking: {
          ...state.thinking,
          active: false,
          durationMs: resolvedDuration,
          expanded: false,
        },
      };
    }
    return {
      messageTraces: nextTraces,
      streamingMessageId: null,
      reasoningSteps: [],
      reasoningExpanded: false,
      thinking: { ...EMPTY_THINKING },
    };
  });
}

async function loadConversationArtifacts(
  conversationId: string,
  options?: { reportError?: boolean; includeMessages?: boolean }
): Promise<void> {
  useAgentConversationStore.setState((state) =>
    state.conversation?.id === conversationId ? { threadLoading: true } : state
  );
  try {
    const tasks = [
      getConversationSummary(conversationId),
      getConversationResumeContext(conversationId),
      listMemoryCandidates(conversationId),
      options?.includeMessages ? listConversationMessages(conversationId) : Promise.resolve(null),
    ] as const;
    const [conversationSummary, resumeContext, memoryCandidates, messages] = await Promise.all(tasks);
    useAgentConversationStore.setState((state) => {
      if (state.conversation?.id !== conversationId) {
        return state;
      }
      const patch: Partial<AgentConversationState> = {
        conversation: {
          ...state.conversation,
          ...conversationSummary.conversation,
        },
        conversationSummary,
        resumeContext,
        memoryCandidates,
        threadLoading: false,
      };
      if (messages) {
        patch.messages = messages;
        // When artifacts were loaded with includeMessages, rebuild the
        // per-message thought panels from the persisted `reasoning` field.
        // Only overwrite traces for messages we actually received so we
        // don't clobber any live-turn trace the stream handler just wrote
        // (new messages get a trace snapshotted at turn end).
        const rehydrated = buildHistoricalMessageTraces(messages);
        patch.messageTraces = { ...state.messageTraces, ...rehydrated };
      }
      return patch as AgentConversationState;
    });
  } catch (error) {
    useAgentConversationStore.setState((state) =>
      state.conversation?.id === conversationId ? { threadLoading: false } : state
    );
    if (options?.reportError) {
      useWorkspaceStore.getState().setError(messageFromError(error));
    }
  }
}

function refreshCurrentConversationArtifacts(options?: { reportError?: boolean }): Promise<void> {
  const conversationId = useAgentConversationStore.getState().conversation?.id;
  if (!conversationId) {
    return Promise.resolve();
  }
  return loadConversationArtifacts(conversationId, options);
}

function clearQueuedStreamMessage(): void {
  if (typeof window !== "undefined" && streamMessageState.frameId !== null) {
    window.cancelAnimationFrame(streamMessageState.frameId);
  }
  streamMessageState.buffer = "";
  streamMessageState.frameId = null;
}

function flushStreamMessageBuffer(): void {
  // Apply whatever is still sitting in the rAF-throttled buffer immediately.
  // Used before a stream_rollback so the rollback subtracts from a content
  // string that reflects every token the backend has sent so far.
  if (typeof window !== "undefined" && streamMessageState.frameId !== null) {
    window.cancelAnimationFrame(streamMessageState.frameId);
    streamMessageState.frameId = null;
  }
  const pending = streamMessageState.buffer;
  streamMessageState.buffer = "";
  if (pending) {
    applyStreamChunk(pending);
  }
}

function rollbackStreamMessageTail(length: number): void {
  if (length <= 0) {
    return;
  }
  // Flush any pending rAF buffer first so the rollback operates on the
  // authoritative committed content (otherwise we'd trim text that hasn't
  // even rendered yet).
  flushStreamMessageBuffer();
  useAgentConversationStore.setState((state) => {
    const messageId = state.streamingMessageId;
    if (!messageId) return state;
    return {
      messages: state.messages.map((message) => {
        if (message.id !== messageId) return message;
        const current = message.content;
        // JS string length counts UTF-16 code units; the backend uses
        // Python's `len(str)` which counts code points. For BMP characters
        // (all of modern CJK + ASCII) these agree. Non-BMP emoji would
        // require a Unicode-aware trim, but they're extremely rare in
        // chat content, and truncating too little is harmless (the
        // thinking replay still lands as reasoning_delta).
        const trimmed = current.length >= length
          ? current.slice(0, current.length - length)
          : "";
        return { ...message, content: trimmed };
      }),
    };
  });
}

function applyStreamChunk(pending: string): void {
  if (!pending) {
    return;
  }
  useAgentConversationStore.setState((state) => {
    const messageId = state.streamingMessageId;
    if (!messageId) {
      // No active placeholder (stream already ended or was never started).
      // Drop the chunk rather than silently conjuring a rogue message bubble.
      return state;
    }
    return {
      messages: state.messages.map((message) =>
        message.id === messageId ? { ...message, content: message.content + pending } : message
      ),
    };
  });
}

function queueStreamMessageChunk(text: string): void {
  if (!text) {
    return;
  }
  streamMessageState.buffer += text;
  if (streamMessageState.frameId !== null) {
    return;
  }
  if (typeof window === "undefined") {
    const pending = streamMessageState.buffer;
    streamMessageState.buffer = "";
    applyStreamChunk(pending);
    return;
  }
  streamMessageState.frameId = window.requestAnimationFrame(() => {
    const pending = streamMessageState.buffer;
    streamMessageState.buffer = "";
    streamMessageState.frameId = null;
    if (!pending) {
      return;
    }
    applyStreamChunk(pending);
  });
}

type ThinkingStreamState = {
  buffer: string;
  frameId: number | null;
};

const thinkingStreamState: ThinkingStreamState = {
  buffer: "",
  frameId: null,
};

function applyThinkingChunk(pending: string): void {
  if (!pending) {
    return;
  }
  useAgentConversationStore.setState((state) => {
    const now = Date.now();
    const startedAt = state.thinking.startedAt ?? now;
    return {
      thinking: {
        ...state.thinking,
        content: state.thinking.content + pending,
        startedAt,
        active: true,
        expanded: state.thinking.expanded || state.thinking.content.length === 0,
        durationMs: null,
      },
    };
  });
}

function queueThinkingChunk(text: string): void {
  if (!text) {
    return;
  }
  thinkingStreamState.buffer += text;
  if (thinkingStreamState.frameId !== null) {
    return;
  }
  if (typeof window === "undefined") {
    const pending = thinkingStreamState.buffer;
    thinkingStreamState.buffer = "";
    applyThinkingChunk(pending);
    return;
  }
  thinkingStreamState.frameId = window.requestAnimationFrame(() => {
    const pending = thinkingStreamState.buffer;
    thinkingStreamState.buffer = "";
    thinkingStreamState.frameId = null;
    if (!pending) {
      return;
    }
    applyThinkingChunk(pending);
  });
}

function flushThinkingBuffer(): void {
  if (typeof window !== "undefined" && thinkingStreamState.frameId !== null) {
    window.cancelAnimationFrame(thinkingStreamState.frameId);
    thinkingStreamState.frameId = null;
  }
  const pending = thinkingStreamState.buffer;
  thinkingStreamState.buffer = "";
  if (pending) {
    applyThinkingChunk(pending);
  }
}

function clearThinkingBuffer(): void {
  if (typeof window !== "undefined" && thinkingStreamState.frameId !== null) {
    window.cancelAnimationFrame(thinkingStreamState.frameId);
  }
  thinkingStreamState.buffer = "";
  thinkingStreamState.frameId = null;
}

function finalizeThinking(options?: { collapse?: boolean }): void {
  const state = useAgentConversationStore.getState();
  const alreadyFinalized = !state.thinking.active && state.thinking.durationMs !== null;
  const shouldCollapse = Boolean(options?.collapse) && state.thinking.expanded && state.thinking.content.length > 0;
  if (alreadyFinalized && !shouldCollapse && thinkingStreamState.buffer.length === 0) {
    return;
  }
  flushThinkingBuffer();
  useAgentConversationStore.setState((current) => {
    const hasContent = current.thinking.content.length > 0;
    const startedAt = current.thinking.startedAt;
    const durationMs =
      current.thinking.durationMs !== null
        ? current.thinking.durationMs
        : startedAt !== null
        ? Date.now() - startedAt
        : null;
    const nextExpanded = options?.collapse && hasContent ? false : current.thinking.expanded;
    if (
      !current.thinking.active &&
      current.thinking.durationMs === durationMs &&
      current.thinking.expanded === nextExpanded
    ) {
      return current;
    }
    return {
      thinking: {
        ...current.thinking,
        active: false,
        durationMs,
        expanded: nextExpanded,
      },
    };
  });
}

const useAgentConversationStore = create<AgentConversationState>((set, get) => ({
  conversation: null,
  conversations: [],
  messages: [],
  prompt: "",
  streamStatus: "idle",
  conversationSummary: null,
  resumeContext: null,
  memoryCandidates: [],
  reasoningSteps: [],
  reasoningExpanded: false,
  thinking: { ...EMPTY_THINKING },
  messageTraces: {},
  streamingMessageId: null,
  pendingDraftCapture: false,
  threadLoading: false,
  threadBusyAction: "",
  checkpointLabel: "",
  setPrompt: (value) => set((state) => (state.prompt === value ? state : { prompt: value })),
  setReasoningExpanded: (value) =>
    set((state) => (state.reasoningExpanded === value ? state : { reasoningExpanded: value })),
  setThinkingExpanded: (value) =>
    set((state) =>
      state.thinking.expanded === value ? state : { thinking: { ...state.thinking, expanded: value } }
    ),
  setMessageReasoningExpanded: (messageId, expanded) =>
    set((state) => {
      const trace = state.messageTraces[messageId];
      if (!trace || trace.reasoningExpanded === expanded) {
        return state;
      }
      return {
        messageTraces: {
          ...state.messageTraces,
          [messageId]: { ...trace, reasoningExpanded: expanded },
        },
      };
    }),
  setMessageThinkingExpanded: (messageId, expanded) =>
    set((state) => {
      const trace = state.messageTraces[messageId];
      if (!trace || trace.thinking.expanded === expanded) {
        return state;
      }
      return {
        messageTraces: {
          ...state.messageTraces,
          [messageId]: {
            ...trace,
            thinking: { ...trace.thinking, expanded },
          },
        },
      };
    }),
  setCheckpointLabel: (value) => set((state) => (state.checkpointLabel === value ? state : { checkpointLabel: value })),
  cancelStream: async () => {
    const conversation = get().conversation;
    if (!conversation || get().streamStatus !== "streaming") {
      return;
    }

    try {
      await cancelConversationStream(conversation.id);
    } catch {
      // ignore cancel request failures and still abort the local stream
    }

    activeStreamAbortController?.abort();
    activeStreamAbortController = null;
    clearQueuedStreamMessage();
    clearThinkingBuffer();
    useUiStore.getState().setAgentPhaseStatus(null);
    appendReasoningStep(buildReasoningStep("phase", "done", "已停止生成", "本轮回答已手动中止。"));
    snapshotCurrentTraceIntoStore();
    set({ streamStatus: "idle", pendingDraftCapture: false });
  },
  refreshThreadArtifacts: async () => {
    await refreshCurrentConversationArtifacts({ reportError: true });
  },
  compactThread: async () => {
    const conversation = get().conversation;
    if (!conversation) {
      return;
    }
    set({ threadBusyAction: "compact" });
    try {
      const updatedConversation = await compactConversation(conversation.id);
      set((state) => ({
        conversation: state.conversation?.id === conversation.id ? { ...state.conversation, ...updatedConversation } : state.conversation,
      }));
      await loadConversationArtifacts(conversation.id, { reportError: true });
    } catch (error) {
      useWorkspaceStore.getState().setError(messageFromError(error));
    } finally {
      set({ threadBusyAction: "" });
    }
  },
  createCheckpoint: async () => {
    const conversation = get().conversation;
    if (!conversation) {
      return;
    }
    set({ threadBusyAction: "checkpoint" });
    try {
      await createConversationCheckpoint(conversation.id, get().checkpointLabel.trim() || undefined);
      set({ checkpointLabel: "" });
      await loadConversationArtifacts(conversation.id, { reportError: true });
    } catch (error) {
      useWorkspaceStore.getState().setError(messageFromError(error));
    } finally {
      set({ threadBusyAction: "" });
    }
  },
  acceptMemoryCandidate: async (candidateId) => {
    const conversation = get().conversation;
    if (!conversation) {
      return;
    }
    set({ threadBusyAction: `accept:${candidateId}` });
    try {
      await acceptMemoryCandidate(conversation.id, candidateId);
      await loadConversationArtifacts(conversation.id, { reportError: true });
    } catch (error) {
      useWorkspaceStore.getState().setError(messageFromError(error));
    } finally {
      set({ threadBusyAction: "" });
    }
  },
  rejectMemoryCandidate: async (candidateId) => {
    const conversation = get().conversation;
    if (!conversation) {
      return;
    }
    set({ threadBusyAction: `reject:${candidateId}` });
    try {
      await rejectMemoryCandidate(conversation.id, candidateId);
      await loadConversationArtifacts(conversation.id, { reportError: true });
    } catch (error) {
      useWorkspaceStore.getState().setError(messageFromError(error));
    } finally {
      set({ threadBusyAction: "" });
    }
  },
  resetForWorkspace: async (workspace) => {
    activeStreamAbortController?.abort();
    activeStreamAbortController = null;
    clearQueuedStreamMessage();
    clearThinkingBuffer();
    useUiStore.getState().setAgentPhaseStatus(null);

    let conversation: Conversation | null = null;
    let messages: Message[] = [];
    let conversationList: Conversation[] = [];
    try {
      conversationList = await listConversations(false);
      if (conversationList.length > 0) {
        conversation = conversationList[0];
        try {
          messages = await listConversationMessages(conversation.id);
        } catch {
          messages = [];
        }
      }
    } catch {
      conversation = null;
    }
    if (!conversation) {
      conversation = await createConversation(`${workspace.name} 对话`);
      messages = [];
      conversationList = [conversation, ...conversationList];
    }

    set({
      conversation,
      conversations: conversationList,
      messages,
      prompt: "",
      streamStatus: "idle",
      conversationSummary: null,
      resumeContext: null,
      memoryCandidates: [],
      reasoningSteps: [],
      thinking: { ...EMPTY_THINKING },
      // Same rehydration as switchConversation: when the workspace opens to
      // a pre-existing first conversation, pull each assistant message's
      // persisted `reasoning` back into a MessageTrace so the thought
      // panels aren't blank until the user sends another prompt.
      messageTraces: buildHistoricalMessageTraces(messages),
      streamingMessageId: null,
      pendingDraftCapture: false,
      threadLoading: false,
      threadBusyAction: "",
      checkpointLabel: "",
    });
    void loadConversationArtifacts(conversation.id);
    return conversation;
  },
  refreshConversations: async () => {
    try {
      const list = await listConversations(false);
      set({ conversations: list });
      return list;
    } catch (error) {
      useWorkspaceStore.getState().setError(messageFromError(error));
      return [];
    }
  },
  createNewConversation: async (title) => {
    const workspaceStore = useWorkspaceStore.getState();
    const workspace = workspaceStore.workspace;
    if (!workspace) {
      workspaceStore.setError("请先打开工作区，再启动智能助手。");
      return null;
    }
    activeStreamAbortController?.abort();
    activeStreamAbortController = null;
    clearQueuedStreamMessage();
    clearThinkingBuffer();
    useUiStore.getState().setAgentPhaseStatus(null);
    try {
      const stamp = new Date().toLocaleString("zh-CN", { hour12: false });
      const conversation = await createConversation(title?.trim() || `新会话 · ${stamp}`);
      set((state) => ({
        conversation,
        conversations: [conversation, ...state.conversations.filter((item) => item.id !== conversation.id)],
        messages: [],
        prompt: "",
        streamStatus: "idle",
        conversationSummary: null,
        resumeContext: null,
        memoryCandidates: [],
        reasoningSteps: [],
        thinking: { ...EMPTY_THINKING },
        messageTraces: {},
        streamingMessageId: null,
        pendingDraftCapture: false,
      }));
      void loadConversationArtifacts(conversation.id);
      return conversation;
    } catch (error) {
      useWorkspaceStore.getState().setError(messageFromError(error));
      return null;
    }
  },
  switchConversation: async (conversationId) => {
    const state = get();
    if (state.conversation?.id === conversationId) {
      return;
    }
    activeStreamAbortController?.abort();
    activeStreamAbortController = null;
    clearQueuedStreamMessage();
    clearThinkingBuffer();
    useUiStore.getState().setAgentPhaseStatus(null);

    const known = state.conversations.find((item) => item.id === conversationId);
    try {
      const conversation = known ?? (await listConversations(false)).find((item) => item.id === conversationId);
      if (!conversation) {
        throw new Error("未找到该会话");
      }
      let messages: Message[] = [];
      try {
        messages = await listConversationMessages(conversation.id);
      } catch {
        messages = [];
      }
      set({
        conversation,
        messages,
        prompt: "",
        streamStatus: "idle",
        conversationSummary: null,
        resumeContext: null,
        memoryCandidates: [],
        reasoningSteps: [],
        thinking: { ...EMPTY_THINKING },
        // Rehydrate per-message thinking panels from the persisted
        // `reasoning` field instead of starting with an empty map.
        // Without this, every reopened conversation loses its thought
        // transcript even though the backend still has it on disk.
        messageTraces: buildHistoricalMessageTraces(messages),
        streamingMessageId: null,
        pendingDraftCapture: false,
      });
      void loadConversationArtifacts(conversation.id);
    } catch (error) {
      useWorkspaceStore.getState().setError(messageFromError(error));
    }
  },
  renameConversation: async (conversationId, title) => {
    try {
      const updated = await renameConversationApi(conversationId, title.trim() || "未命名会话");
      set((state) => ({
        conversation: state.conversation?.id === conversationId ? updated : state.conversation,
        conversations: state.conversations.map((item) => (item.id === conversationId ? updated : item)),
      }));
    } catch (error) {
      useWorkspaceStore.getState().setError(messageFromError(error));
    }
  },
  archiveConversation: async (conversationId) => {
    try {
      await archiveConversationApi(conversationId);
      const state = get();
      const remaining = state.conversations.filter((item) => item.id !== conversationId);
      set({ conversations: remaining });
      if (state.conversation?.id === conversationId) {
        if (remaining.length > 0) {
          await get().switchConversation(remaining[0].id);
        } else {
          const workspace = useWorkspaceStore.getState().workspace;
          if (workspace) {
            await get().createNewConversation(`${workspace.name} 对话`);
          } else {
            set({ conversation: null, messages: [] });
          }
        }
      }
    } catch (error) {
      useWorkspaceStore.getState().setError(messageFromError(error));
    }
  },
  sendPrompt: async (prompt, options) => {
    const workspaceStore = useWorkspaceStore.getState();
    const uiStore = useUiStore.getState();
    const workspace = workspaceStore.workspace;
    const trimmedPrompt = prompt.trim();

    if (!workspace) {
      workspaceStore.setError("请先打开工作区，再启动智能助手。");
      return;
    }
    if (get().streamStatus === "streaming") {
      return;
    }
    if (!trimmedPrompt) {
      workspaceStore.setError("请输入提问内容。");
      return;
    }

    workspaceStore.clearError();

    let conversation = get().conversation;
    try {
      if (!conversation) {
        conversation = await get().resetForWorkspace(workspace);
      }

      const userMessage = buildLocalMessage("user", trimmedPrompt);
      clearQueuedStreamMessage();
      clearThinkingBuffer();
      uiStore.setAgentPhaseStatus({
        phase: "planning",
        label: "正在连接模型",
        detail: "请求已经发出，正在等待模型开始规划。",
      });
      const assistantPlaceholder = buildLocalMessage("assistant", "");
      set((state) => ({
        messages: [...state.messages, userMessage, assistantPlaceholder],
        prompt: "",
        streamStatus: "streaming",
        streamingMessageId: assistantPlaceholder.id,
        reasoningSteps: [
          buildReasoningStep("phase", "active", "连接模型", "请求已经发出，正在等待模型开始规划。"),
        ],
        // Expanded by default during a live turn so the user can watch
        // planning/tool steps roll in. `snapshotCurrentTraceIntoStore`
        // collapses the per-message trace once the turn completes.
        reasoningExpanded: true,
        thinking: { ...EMPTY_THINKING },
        pendingDraftCapture: Boolean(options?.captureDraft),
      }));

      activeStreamAbortController?.abort();
      activeStreamAbortController = new AbortController();

      await streamConversation(
        conversation.id,
        trimmedPrompt,
        workspaceStore.selectedKind === "note" ? workspaceStore.selectedPath : null,
        handleAgentEvent,
        { signal: activeStreamAbortController.signal }
      );

      const currentState = get();
      if (currentState.streamStatus === "streaming") {
        clearQueuedStreamMessage();
        uiStore.setAgentPhaseStatus(null);
        activeStreamAbortController = null;
        snapshotCurrentTraceIntoStore();
        set({ streamStatus: "idle", pendingDraftCapture: false });
      }
    } catch (error) {
      activeStreamAbortController = null;
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      clearQueuedStreamMessage();
      uiStore.setAgentPhaseStatus(null);
      workspaceStore.setError(messageFromError(error));
      snapshotCurrentTraceIntoStore();
      set({ streamStatus: "error", pendingDraftCapture: false });
    }
  },
  generateDraft: async () => {
    const workspaceStore = useWorkspaceStore.getState();
    const selectedPath = workspaceStore.selectedPath;
    const prompt = selectedPath
      ? `请阅读当前文档 ${selectedPath}，生成一份结构清晰的 AI 草稿，包含标题、小节、关键要点和面试结论。`
      : "请基于当前工作区生成一份结构清晰的 AI 草稿，包含标题、小节和关键结论。";
    await get().sendPrompt(prompt, { captureDraft: true });
  },
}));

async function handleAgentEvent(event: AgentEvent): Promise<void> {
  const workspaceStore = useWorkspaceStore.getState();
  const uiStore = useUiStore.getState();
  const draftKey = workspaceStore.selectedPath ?? GLOBAL_DRAFT_KEY;

  switch (event.type) {
    case "message_start":
      workspaceStore.clearError();
      appendReasoningStep(buildReasoningStep("phase", "active", "开始响应", "助手已开始构建本轮回复。"));
      return;
    case "reasoning_step":
      appendReasoningStep(buildReasoningStep(event.kind, event.status, event.title, event.detail));
      return;
    case "phase_status":
      uiStore.setAgentPhaseStatus({
        phase: event.phase,
        label: event.label,
        detail: event.detail,
      });
      return;
    case "fallback_used":
      uiStore.setAgentPhaseStatus({
        phase: "planning",
        label: "已切换到回退模式",
        detail: event.reason,
      });
      return;
    case "token":
      // Tokens flow into the assistant bubble optimistically. We no longer
      // collapse the thinking panel here because a middle-turn tool-call
      // also emits tokens up until the backend issues a stream_rollback;
      // prematurely collapsing would flicker the thinking UI. The panel
      // finalises cleanly in message_done / done / error.
      uiStore.setAgentPhaseStatus(null);
      queueStreamMessageChunk(event.text);
      return;
    case "stream_rollback":
      // Backend is telling us: the last N chars we just appended to the
      // answer bubble actually belong in the thinking panel (turn was a
      // tool_call, not the final respond). Trim the tail; the backend
      // immediately follows with reasoning_delta events replaying the
      // same deltas into the thinking stream.
      rollbackStreamMessageTail(event.text.length);
      return;
    case "reasoning_delta":
      queueThinkingChunk(event.text);
      return;
    case "retrieval_hits":
      workspaceStore.setSearchHits(event.hits);
      return;
    case "tool_started": {
      // Backend runtime already emitted a `reasoning_step(kind="tool",
      // status="active", title="执行工具 · <name>", detail=<raw args>)` just
      // before dispatching the tool. Enrich that step's detail with the
      // friendlier target/query payload so the thinking panel shows
      // "读取 Notes/xxx.md" / "搜索 缓存" instead of `{'path': 'Notes/...'}`.
      const friendlyDetail =
        (event.target && event.target.trim()) ||
        (event.query && event.query.trim()) ||
        null;
      if (!friendlyDetail) return;
      useAgentConversationStore.setState((state) => {
        const steps = state.reasoningSteps;
        for (let i = steps.length - 1; i >= 0; i -= 1) {
          const step = steps[i];
          if (step.kind === "tool" && step.status === "active") {
            if (step.detail === friendlyDetail) return state;
            const next = [...steps];
            next[i] = { ...step, detail: friendlyDetail };
            return { reasoningSteps: next };
          }
        }
        return state;
      });
      return;
    }
    case "tool_finished":
      // Backend runtime will follow with a `reasoning_step(kind="tool",
      // status="done", ...)` that supersedes the active step. No extra
      // bookkeeping needed here.
      return;
    case "tool_failed":
      workspaceStore.setError(`工具 ${event.tool} 执行失败：${event.detail}`);
      return;
    case "retrying":
      workspaceStore.setError(
        event.detail
          ? `正在重试 ${event.stage}：${event.detail}`
          : `正在重试 ${event.stage}（第 ${event.attempt} 次）`
      );
      return;
    case "recovered":
      workspaceStore.clearError();
      return;
    case "file_written":
      appendReasoningStep(buildReasoningStep("tool", "done", "已写入文件", event.path));
      void (async () => {
        await workspaceStore.refreshTree();
        if (event.path.toLowerCase().endsWith(".md")) {
          await workspaceStore.refreshNotes();
        }
        if (event.path === workspaceStore.selectedPath) {
          await workspaceStore.selectPath(
            event.path,
            event.path.toLowerCase().endsWith(".md") ? "note" : "file"
          );
        }
      })();
      return;
    case "note_created":
      appendReasoningStep(buildReasoningStep("tool", "done", "已创建笔记", event.note.relative_path));
      workspaceStore.upsertNote(event.note);
      void (async () => {
        await workspaceStore.refreshTree();
        await workspaceStore.selectPath(event.note.relative_path, "note");
      })();
      return;
    case "note_updated":
      appendReasoningStep(buildReasoningStep("tool", "done", "已更新笔记", event.note.relative_path));
      workspaceStore.upsertNote(event.note);
      void (async () => {
        if (event.note.relative_path === workspaceStore.selectedPath) {
          await workspaceStore.selectPath(event.note.relative_path, "note");
        } else {
          await workspaceStore.refreshNotes();
        }
      })();
      return;
    case "approval_required":
      appendReasoningStep(buildReasoningStep("tool", "active", "等待审批", event.approval.reason || event.approval.action));
      uiStore.setUtilityDrawerTab("approvals");
      uiStore.setUtilityDrawerOpen(true);
      void workspaceStore.refreshApprovals();
      return;
    case "message_done": {
      const previousMessageId = useAgentConversationStore.getState().streamingMessageId;
      clearQueuedStreamMessage();
      uiStore.setAgentPhaseStatus(null);
      finalizeThinking({ collapse: true });
      const { pendingDraftCapture } = useAgentConversationStore.getState();
      // First merge the backend-authoritative message into the placeholder so
      // the id is up to date; then snapshot the accumulated trace onto the
      // final id and drop the placeholder trace entry.
      useAgentConversationStore.setState((state) => ({
        messages: previousMessageId
          ? state.messages.map((message) =>
              message.id === previousMessageId
                ? { ...event.message, content: message.content || event.message.content }
                : message
            )
          : [...state.messages, event.message],
      }));
      snapshotCurrentTraceIntoStore({
        targetMessageId: event.message.id,
        deletePreviousId: previousMessageId,
      });
      if (pendingDraftCapture) {
        uiStore.setDraftContent(draftKey, event.message.content);
        uiStore.setDocumentViewMode("draft");
      }
      return;
    }
    case "error": {
      activeStreamAbortController = null;
      clearQueuedStreamMessage();
      finalizeThinking();
      uiStore.setAgentPhaseStatus(null);
      workspaceStore.setError(event.detail);
      appendReasoningStep(buildReasoningStep("error", "error", "执行异常", event.detail));
      snapshotCurrentTraceIntoStore();
      useAgentConversationStore.setState({ streamStatus: "error", pendingDraftCapture: false });
      return;
    }
    case "done":
      activeStreamAbortController = null;
      clearQueuedStreamMessage();
      finalizeThinking({ collapse: true });
      uiStore.setAgentPhaseStatus(null);
      void refreshCurrentConversationArtifacts();
      useAgentConversationStore.setState({
        streamStatus: "idle",
        streamingMessageId: null,
        pendingDraftCapture: false,
      });
      return;
    default:
      return;
  }
}

export function useAgentConversation<T>(selector: (state: AgentConversationState) => T): T {
  return useAgentConversationStore(selector);
}

export const agentConversationStore = useAgentConversationStore;
