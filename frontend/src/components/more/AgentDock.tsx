import {
  Archive,
  Check,
  ChevronDown,
  GripVertical,
  MessageSquarePlus,
  PanelRightOpen,
  Pencil,
  Send,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { MarkdownView } from "@/components/MarkdownView";
import { useAgentConversation } from "@/hooks/useAgentConversation";
import { getSelectedNote } from "@/lib/more";
import { useUiStore } from "@/stores/uiStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import type { Conversation, Message } from "@/types";
import type { MessageTrace, ReasoningStep, ThinkingState } from "@/hooks/useAgentConversation";

const MIN_DOCK_WIDTH = 340;
const MAX_DOCK_WIDTH = 520;

export function AgentDock() {
  const { llmSettings, selectedPath, notes, busyLabel } = useWorkspaceStore(
    useShallow((state) => ({
      llmSettings: state.llmSettings,
      selectedPath: state.selectedPath,
      notes: state.notes,
      busyLabel: state.busyLabel,
    }))
  );
  const { collapsed, toggleCollapse, agentDockWidth, agentDockResizing, setAgentDockWidth, setAgentDockResizing } = useUiStore(
    useShallow((state) => ({
      collapsed: state.isAgentDockCollapsed,
      toggleCollapse: state.toggleAgentDockCollapsed,
      agentDockWidth: state.agentDockWidth,
      agentDockResizing: state.agentDockResizing,
      setAgentDockWidth: state.setAgentDockWidth,
      setAgentDockResizing: state.setAgentDockResizing,
    }))
  );
  const { conversation, streamStatus } = useAgentConversation(
    useShallow((state) => ({
      conversation: state.conversation,
      streamStatus: state.streamStatus,
    }))
  );
  const resizeRef = useRef<{ startX: number; startWidth: number } | null>(null);

  const selectedNote = useMemo(() => getSelectedNote(notes, selectedPath), [notes, selectedPath]);
  const contextLabel = selectedNote
    ? `当前笔记：${selectedNote.title}`
    : selectedPath
      ? `当前文件：${selectedPath}`
      : "上下文：整个工作区";
  const statusLabel =
    streamStatus === "streaming"
      ? "正在处理"
      : streamStatus === "error"
        ? "执行异常"
        : llmSettings.is_configured
          ? "已连接"
          : "未配置";
  const modelLabel = llmSettings.is_configured ? llmSettings.model || "已连接模型" : "模型未配置";
  const conversationLabel = conversation?.title?.trim();
  const headerContextLine = conversationLabel ? `${contextLabel} · ${conversationLabel}` : contextLabel;
  const isBusy = streamStatus === "streaming" || Boolean(busyLabel);

  useEffect(() => {
    if (!agentDockResizing) {
      return;
    }

    const handleMouseMove = (event: MouseEvent) => {
      if (!resizeRef.current) {
        return;
      }
      const nextWidth = resizeRef.current.startWidth + (resizeRef.current.startX - event.clientX);
      setAgentDockWidth(Math.max(MIN_DOCK_WIDTH, Math.min(MAX_DOCK_WIDTH, nextWidth)), { persist: false });
    };

    const handleMouseUp = () => {
      const finalWidth = useUiStore.getState().agentDockWidth;
      resizeRef.current = null;
      setAgentDockWidth(finalWidth);
      setAgentDockResizing(false);
    };

    document.body.style.cursor = "col-resize";
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.cursor = "";
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [agentDockResizing, setAgentDockResizing, setAgentDockWidth]);

  if (collapsed) {
    return (
      <aside className="agent-dock agent-dock-collapsed">
        <button className="sidebar-rail-button" onClick={toggleCollapse} aria-label="展开助手侧栏">
          <PanelRightOpen className="h-4 w-4" />
        </button>
        <div className="agent-rail-label">AI</div>
      </aside>
    );
  }

  return (
    <aside
      className={`agent-dock ${agentDockResizing ? "agent-dock-resizing" : ""}`}
      style={{ width: agentDockWidth }}
    >
      <button
        className="agent-resize-handle"
        aria-label="调整助手栏宽度"
        onMouseDown={(event) => {
          event.preventDefault();
          resizeRef.current = { startX: event.clientX, startWidth: agentDockWidth };
          setAgentDockResizing(true);
        }}
      >
        <GripVertical className="h-3.5 w-3.5" />
      </button>

      <div className="agent-header">
        <AgentDockHeader
          busyLabel={busyLabel}
          headerContextLine={headerContextLine}
          modelLabel={modelLabel}
          fallbackStatusLabel={statusLabel}
          onCollapse={toggleCollapse}
        />
        <ConversationSwitcher />
      </div>

      <AgentMessageScroll />

      <div className="agent-footer">
        <AgentComposer isStreaming={streamStatus === "streaming"} />
      </div>
    </aside>
  );
}

const AgentDockHeader = memo(function AgentDockHeader({
  busyLabel,
  headerContextLine,
  modelLabel,
  fallbackStatusLabel,
  onCollapse,
}: {
  busyLabel: string;
  headerContextLine: string;
  modelLabel: string;
  fallbackStatusLabel: string;
  onCollapse: () => void;
}) {
  const { agentPhaseStatus } = useUiStore(
    useShallow((state) => ({
      agentPhaseStatus: state.agentPhaseStatus,
    }))
  );
  const liveStatusLabel = agentPhaseStatus?.label ?? fallbackStatusLabel;

  return (
    <div className="agent-header-row">
      <div className="agent-header-copy">
        <div className="agent-panel-kicker">parallel copilot</div>
        <div className="agent-panel-headline">
          <div className="agent-panel-title">助手</div>
          <div className="agent-panel-status">{liveStatusLabel}</div>
        </div>
        <div className="agent-panel-meta">{modelLabel}</div>
        <div className="agent-context-inline">{busyLabel || headerContextLine}</div>
      </div>
      <div className="agent-header-actions">
        <button className="icon-button" onClick={onCollapse} aria-label="收起助手侧栏">
          <PanelRightOpen className="h-4 w-4 rotate-180" />
        </button>
      </div>
    </div>
  );
});

const ConversationSwitcher = memo(function ConversationSwitcher() {
  const {
    conversation,
    conversations,
    streamStatus,
    createNewConversation,
    switchConversation,
    renameConversation,
    archiveConversation,
    refreshConversations,
  } = useAgentConversation(
    useShallow((state) => ({
      conversation: state.conversation,
      conversations: state.conversations,
      streamStatus: state.streamStatus,
      createNewConversation: state.createNewConversation,
      switchConversation: state.switchConversation,
      renameConversation: state.renameConversation,
      archiveConversation: state.archiveConversation,
      refreshConversations: state.refreshConversations,
    }))
  );
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    void refreshConversations();
  }, [open, refreshConversations]);

  useEffect(() => {
    if (!open) return;
    const handlePointer = (event: MouseEvent) => {
      const el = rootRef.current;
      if (el && event.target instanceof Node && !el.contains(event.target)) {
        setOpen(false);
      }
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", handlePointer);
    window.addEventListener("keydown", handleKey);
    return () => {
      window.removeEventListener("mousedown", handlePointer);
      window.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  const beginRename = useCallback((item: Conversation) => {
    setEditingId(item.id);
    setEditingTitle(item.title || "");
  }, []);

  const commitRename = useCallback(async () => {
    if (!editingId) return;
    await renameConversation(editingId, editingTitle);
    setEditingId(null);
    setEditingTitle("");
  }, [editingId, editingTitle, renameConversation]);

  const cancelRename = useCallback(() => {
    setEditingId(null);
    setEditingTitle("");
  }, []);

  const handleCreate = useCallback(async () => {
    await createNewConversation();
    setOpen(false);
  }, [createNewConversation]);

  const handleSwitch = useCallback(
    async (id: string) => {
      if (streamStatus === "streaming") {
        // Block switching while streaming to avoid tangled state.
        return;
      }
      await switchConversation(id);
      setOpen(false);
    },
    [streamStatus, switchConversation]
  );

  const activeTitle = conversation?.title?.trim() || "未命名会话";
  const total = conversations.length;

  return (
    <div className="conversation-switcher" ref={rootRef}>
      <button
        type="button"
        className="conversation-switcher-trigger"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        title="切换会话 (Ctrl+K)"
      >
        <span className="truncate">{activeTitle}</span>
        <span className="conversation-switcher-count">{total || "新"}</span>
        <ChevronDown className={`h-3.5 w-3.5 transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open ? (
        <div className="conversation-switcher-panel" role="menu">
          <div className="conversation-switcher-header">
            <span className="conversation-switcher-heading">会话</span>
            <button
              type="button"
              className="conversation-switcher-new"
              onClick={handleCreate}
              disabled={streamStatus === "streaming"}
            >
              <MessageSquarePlus className="h-3.5 w-3.5" />
              <span>新建</span>
            </button>
          </div>
          <div className="conversation-switcher-list">
            {conversations.length ? (
              conversations.map((item) => {
                const isActive = item.id === conversation?.id;
                const isEditing = editingId === item.id;
                return (
                  <div
                    key={item.id}
                    className={`conversation-switcher-item ${isActive ? "conversation-switcher-item-active" : ""}`}
                    role="menuitem"
                  >
                    {isEditing ? (
                      <form
                        className="conversation-switcher-rename-form"
                        onSubmit={(event) => {
                          event.preventDefault();
                          void commitRename();
                        }}
                      >
                        <input
                          autoFocus
                          className="conversation-switcher-rename-input"
                          value={editingTitle}
                          onChange={(event) => setEditingTitle(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Escape") {
                              event.preventDefault();
                              cancelRename();
                            }
                          }}
                        />
                        <button
                          type="submit"
                          className="conversation-switcher-icon-button"
                          aria-label="保存"
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          className="conversation-switcher-icon-button"
                          aria-label="取消"
                          onClick={cancelRename}
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </form>
                    ) : (
                      <>
                        <button
                          type="button"
                          className="conversation-switcher-item-body"
                          onClick={() => void handleSwitch(item.id)}
                          disabled={streamStatus === "streaming" && !isActive}
                          title={item.id}
                        >
                          <div className="conversation-switcher-item-title">{item.title || "未命名会话"}</div>
                          <div className="conversation-switcher-item-meta">
                            {new Date(item.updated_at || item.created_at).toLocaleString("zh-CN", {
                              month: "2-digit",
                              day: "2-digit",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </div>
                        </button>
                        <div className="conversation-switcher-item-actions">
                          <button
                            type="button"
                            className="conversation-switcher-icon-button"
                            onClick={() => beginRename(item)}
                            aria-label="重命名"
                            title="重命名"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            className="conversation-switcher-icon-button conversation-switcher-icon-danger"
                            onClick={() => void archiveConversation(item.id)}
                            aria-label="归档"
                            title="归档"
                          >
                            <Archive className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                );
              })
            ) : (
              <div className="conversation-switcher-empty">暂无会话</div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
});

const AgentMessageScroll = memo(function AgentMessageScroll() {
  const { messages, streamingMessageId, liveThinkingContent, liveReasoningCount } = useAgentConversation(
    useShallow((state) => ({
      messages: state.messages,
      streamingMessageId: state.streamingMessageId,
      liveThinkingContent: state.thinking.content,
      liveReasoningCount: state.reasoningSteps.length,
    }))
  );
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pinnedToBottomRef = useRef(true);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) {
      return;
    }
    const distanceFromBottom = el.scrollHeight - (el.scrollTop + el.clientHeight);
    pinnedToBottomRef.current = distanceFromBottom < 64;
  }, []);

  // Defer the scroll-to-bottom write into the next animation frame so a
  // burst of token/thinking/reasoning updates coalesces into a single
  // layout-reflow instead of one per setState. Reading `scrollHeight`
  // forces a synchronous layout, so doing it on every rAF tick during
  // streaming is enough to stall input handlers in sibling surfaces.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !pinnedToBottomRef.current) {
      return;
    }
    if (typeof window === "undefined") {
      el.scrollTop = el.scrollHeight;
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      if (!pinnedToBottomRef.current) return;
      const current = scrollRef.current;
      if (!current) return;
      current.scrollTop = current.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [messages, streamingMessageId, liveThinkingContent, liveReasoningCount]);

  return (
    <div className="agent-message-scroll" ref={scrollRef} onScroll={handleScroll}>
      <AgentMessageHistory messages={messages} />
    </div>
  );
});

const AgentThinkingStream = memo(function AgentThinkingStream({
  thinking,
  onToggle,
}: {
  thinking: ThinkingState;
  onToggle: () => void;
}) {
  const secondsLabel = formatThinkingDuration(thinking);
  const titleLabel = thinking.active ? `Thinking${secondsLabel ? ` for ${secondsLabel}` : "…"}` : `Thought for ${secondsLabel || "—"}`;
  return (
    <section className="agent-thought-panel">
      <button className="agent-thought-toggle" onClick={onToggle} aria-expanded={thinking.expanded}>
        <div className="agent-thought-label">
          <Sparkles className={`h-3.5 w-3.5 ${thinking.active ? "agent-thought-icon-active" : ""}`} />
          <span>{titleLabel}</span>
        </div>
        <ChevronDown className={`agent-thought-icon ${thinking.expanded ? "agent-thought-icon-expanded" : ""}`} />
      </button>
      {thinking.expanded && thinking.content ? (
        <div className="agent-thought-body">{thinking.content}</div>
      ) : null}
    </section>
  );
});

function formatThinkingDuration(thinking: ThinkingState): string {
  if (thinking.durationMs !== null) {
    return formatDurationValue(thinking.durationMs);
  }
  if (thinking.startedAt === null) {
    return "";
  }
  return formatDurationValue(Date.now() - thinking.startedAt);
}

function formatDurationValue(ms: number): string {
  if (ms < 1000) {
    return "<1s";
  }
  const seconds = ms / 1000;
  if (seconds < 10) {
    return `${seconds.toFixed(1)}s`;
  }
  return `${Math.round(seconds)}s`;
}

const AgentReasoningPanel = memo(function AgentReasoningPanel({
  steps,
  totalCount,
  expanded,
  active,
  title,
  onToggle,
}: {
  steps: ReasoningStep[];
  totalCount: number;
  expanded: boolean;
  active: boolean;
  title: string;
  onToggle: () => void;
}) {
  const summaryLabel = active ? title : `完成 · ${totalCount} 步`;
  return (
    <section className="agent-trace-panel">
      <button className="agent-trace-toggle" onClick={onToggle} aria-expanded={expanded}>
        <span className="agent-trace-toggle-label">
          <Sparkles className={`h-3.5 w-3.5 ${active ? "agent-trace-icon-active" : "text-slate-400"}`} />
          <span className="agent-trace-toggle-text">{summaryLabel}</span>
        </span>
        <span className="agent-trace-toggle-side">
          <span className="agent-trace-toggle-meta">{totalCount} 步</span>
          <ChevronDown className={`agent-trace-toggle-icon ${expanded ? "agent-trace-toggle-icon-expanded" : ""}`} />
        </span>
      </button>
      {expanded ? (
        <div className="agent-trace-list">
          {steps.map((step) => (
            <AgentReasoningRow key={step.id} step={step} />
          ))}
        </div>
      ) : null}
    </section>
  );
});

function reasoningKindLabel(kind: ReasoningStep["kind"]): string {
  switch (kind) {
    case "phase":
      return "阶段";
    case "tool":
      return "工具";
    case "retrieval":
      return "上下文";
    case "fallback":
      return "回退";
    case "retry":
      return "重试";
    case "recovered":
      return "恢复";
    case "error":
      return "异常";
    default:
      return "步骤";
  }
}

function reasoningStateLabel(status: ReasoningStep["status"]): string {
  switch (status) {
    case "active":
      return "Live";
    case "error":
      return "Issue";
    default:
      return "Done";
  }
}

const AgentReasoningRow = memo(function AgentReasoningRow({ step }: { step: ReasoningStep }) {
  const kindLabel = reasoningKindLabel(step.kind);
  const statusLabel = reasoningStateLabel(step.status);

  return (
    <div className={`agent-thinking-row agent-thinking-row-${step.status}`}>
      <div className="agent-thinking-row-rail">
        <div className={`agent-thinking-row-dot agent-thinking-row-dot-${step.status}`} />
        <div className="agent-thinking-row-line" />
      </div>
      <div className="agent-thinking-row-body">
        <div className="agent-thinking-row-meta">
          <span className="agent-thinking-kind">{kindLabel}</span>
          <span className={`agent-thinking-row-state agent-thinking-row-state-${step.status}`}>{statusLabel}</span>
        </div>
        <div className="agent-thinking-row-head">
          <div className="agent-thinking-row-title">{step.title}</div>
        </div>
        {step.detail ? <div className="agent-thinking-row-detail">{step.detail}</div> : null}
      </div>
    </div>
  );
});

const AgentMessageHistory = memo(function AgentMessageHistory({ messages }: { messages: Message[] }) {
  if (!messages.length) {
    return (
      <div className="agent-empty-state">
        <div className="agent-empty-title">助手已就绪</div>
        <div className="agent-empty-copy">在下方输入问题，围绕当前文件获取辅助。</div>
      </div>
    );
  }

  return (
    <>
      {messages.map((message) =>
        message.role === "assistant" ? (
          <AssistantTurn key={message.id} message={message} />
        ) : (
          <AgentMessageBubble key={message.id} message={message} />
        )
      )}
    </>
  );
});

const AssistantTurn = memo(function AssistantTurn({ message }: { message: Message }) {
  // Subscribe to only stable, directly-stored slices. Composing a fresh
  // MessageTrace object inside the selector would return a NEW reference on
  // every call, which makes useSyncExternalStore report a changing snapshot
  // and triggers the infinite "Maximum update depth exceeded" loop.
  const isLive = useAgentConversation((state) => state.streamingMessageId === message.id);
  const liveReasoningSteps = useAgentConversation((state) => state.reasoningSteps);
  const liveReasoningExpanded = useAgentConversation((state) => state.reasoningExpanded);
  const liveThinking = useAgentConversation((state) => state.thinking);
  const storedTrace = useAgentConversation((state) => state.messageTraces[message.id] ?? null);
  const setReasoningExpanded = useAgentConversation((state) => state.setReasoningExpanded);
  const setThinkingExpanded = useAgentConversation((state) => state.setThinkingExpanded);
  const setMessageReasoningExpanded = useAgentConversation((state) => state.setMessageReasoningExpanded);
  const setMessageThinkingExpanded = useAgentConversation((state) => state.setMessageThinkingExpanded);

  const trace = useMemo<MessageTrace | null>(() => {
    if (isLive) {
      return {
        reasoningSteps: liveReasoningSteps,
        reasoningExpanded: liveReasoningExpanded,
        thinking: liveThinking,
      };
    }
    return storedTrace;
  }, [isLive, liveReasoningSteps, liveReasoningExpanded, liveThinking, storedTrace]);

  const activeStep = useMemo(
    () =>
      isLive
        ? [...liveReasoningSteps].reverse().find((step) => step.status === "active")
        : undefined,
    [isLive, liveReasoningSteps]
  );
  const latestStep = isLive ? liveReasoningSteps[liveReasoningSteps.length - 1] : undefined;
  const active = isLive && Boolean(activeStep);
  const liveTitle = isLive
    ? activeStep?.title || latestStep?.title || "助手正在整理上下文"
    : "";

  const agentPhaseStatus = useUiStore((state) => state.agentPhaseStatus);
  const activeWithStatus = isLive ? Boolean(agentPhaseStatus) || active : false;
  const effectiveTitle = isLive ? agentPhaseStatus?.label || liveTitle : "";

  const hasThinking = Boolean(trace && (trace.thinking.content || trace.thinking.active));
  const hasReasoning = Boolean(trace && trace.reasoningSteps.length);

  return (
    <div className="agent-turn">
      {hasThinking && trace ? (
        <AgentThinkingStream
          thinking={trace.thinking}
          onToggle={() =>
            isLive
              ? setThinkingExpanded(!trace.thinking.expanded)
              : setMessageThinkingExpanded(message.id, !trace.thinking.expanded)
          }
        />
      ) : null}
      {hasReasoning && trace ? (
        <AgentReasoningPanel
          steps={trace.reasoningExpanded ? trace.reasoningSteps : trace.reasoningSteps.slice(-3)}
          totalCount={trace.reasoningSteps.length}
          expanded={trace.reasoningExpanded}
          active={activeWithStatus}
          title={activeWithStatus ? effectiveTitle : `完成 · ${trace.reasoningSteps.length} 步`}
          onToggle={() =>
            isLive
              ? setReasoningExpanded(!trace.reasoningExpanded)
              : setMessageReasoningExpanded(message.id, !trace.reasoningExpanded)
          }
        />
      ) : null}
      <AgentMessageBubble message={message} streaming={isLive && !message.content} />
    </div>
  );
});

const AgentMessageBubble = memo(function AgentMessageBubble({ message, streaming }: { message: Message; streaming?: boolean }) {
  const isAssistant = message.role === "assistant";
  const showEmptyHint = streaming && isAssistant && !message.content;
  if (isAssistant && !message.content && !streaming) {
    // Completed assistant turn with no content (e.g., error before tokens arrived) — hide the empty bubble.
    return null;
  }
  return (
    <article className={`agent-bubble ${isAssistant ? "agent-bubble-assistant" : "agent-bubble-user"}`}>
      <div className="agent-bubble-kicker">
        {isAssistant ? "助手" : message.role === "user" ? "你" : message.role}
      </div>
      <div className="agent-bubble-content">
        {showEmptyHint ? (
          <span className="agent-bubble-typing">正在组织回答…</span>
        ) : isAssistant ? (
          <MarkdownView source={message.content} />
        ) : (
          <div className="whitespace-pre-wrap text-sm leading-6 text-slate-700">{message.content}</div>
        )}
      </div>
      {message.citations.length ? (
        <div className="agent-bubble-citations">
          {message.citations.map((citation) => (
            <span key={citation} className="meta-pill meta-pill-subtle">
              {citation}
            </span>
          ))}
        </div>
      ) : null}
    </article>
  );
});

const AgentComposer = memo(function AgentComposer({ isStreaming }: { isStreaming: boolean }) {
  const { prompt, setPrompt, sendPrompt, cancelStream } = useAgentConversation(
    useShallow((state) => ({
      prompt: state.prompt,
      setPrompt: state.setPrompt,
      sendPrompt: state.sendPrompt,
      cancelStream: state.cancelStream,
    }))
  );
  const handlePromptChange = useCallback(
    (value: string) => {
      setPrompt(value);
    },
    [setPrompt]
  );
  const handleSendPrompt = useCallback(() => {
    if (!prompt.trim()) {
      return;
    }
    void sendPrompt(prompt);
  }, [prompt, sendPrompt]);
  const handleCancelStream = useCallback(() => {
    void cancelStream();
  }, [cancelStream]);
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key !== "Enter") {
        return;
      }
      // Shift+Enter inserts a newline (default). Plain Enter sends; Ctrl/Cmd+Enter also sends.
      if (event.shiftKey) {
        return;
      }
      if (event.nativeEvent.isComposing) {
        // Chinese IME composition in progress — let it commit.
        return;
      }
      event.preventDefault();
      if (isStreaming) {
        return;
      }
      handleSendPrompt();
    },
    [handleSendPrompt, isStreaming]
  );

  return (
    <div className="agent-composer-shell group transition-all focus-within:border-slate-300 focus-within:shadow-[0_12px_28px_-24px_rgba(15,23,42,0.3)]">
      <textarea
        className="dock-prompt"
        value={prompt}
        onChange={(event) => handlePromptChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="回车发送 · Shift+回车换行"
        disabled={isStreaming}
      />
      {isStreaming ? (
        <button className="agent-send-button" onClick={handleCancelStream} aria-label="停止生成">
          <Square className="h-4 w-4" />
        </button>
      ) : (
        <button className="agent-send-button" onClick={handleSendPrompt} disabled={!prompt.trim()} aria-label="发送消息">
          <Send className="h-4 w-4" />
        </button>
      )}
    </div>
  );
});
