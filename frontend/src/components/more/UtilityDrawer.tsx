import { Archive, BookmarkPlus, BrainCircuit, ClipboardCopy, Globe, Pencil, Play, Plus, RefreshCcw, Settings2, ShieldCheck, Sparkles, Trash2, Upload, Waypoints, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { deleteMcpServer, deleteSkill, invokeMcpTool, listMcpServerTools, resolveSkills, upsertMcpServer, upsertSkill } from "@/api";
import { useAgentConversation } from "@/hooks/useAgentConversation";
import { countPendingApprovals, messageFromError } from "@/lib/more";
import { useUiStore } from "@/stores/uiStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import type { MCPInvokeResult, MCPServerDefinition, MCPToolDefinition, SkillDefinition } from "@/types";

type SkillEditorState = {
  skillId: string;
  name: string;
  description: string;
  promptPrefix: string;
  whenToUse: string;
  toolSubset: string;
  examples: string;
  keywords: string;
  enabled: boolean;
};

type McpServerEditorState = {
  serverId: string;
  name: string;
  description: string;
  transport: string;
  command: string;
  argsText: string;
  envJson: string;
  workingDirectory: string;
  enabled: boolean;
  toolsJson: string;
};

type McpInvokeEditorState = {
  serverId: string;
  toolName: string;
  argsJson: string;
  prompt: string;
  currentNotePath: string;
  defaultNoteDir: string;
};

type SkillResolveState = {
  prompt: string;
  currentNotePath: string;
  activeTags: string;
  limit: string;
};

const EMPTY_SKILL_EDITOR: SkillEditorState = {
  skillId: "",
  name: "",
  description: "",
  promptPrefix: "",
  whenToUse: "",
  toolSubset: "",
  examples: "",
  keywords: "",
  enabled: true,
};

const EMPTY_MCP_SERVER_EDITOR: McpServerEditorState = {
  serverId: "",
  name: "",
  description: "",
  transport: "builtin",
  command: "",
  argsText: "",
  envJson: "{}",
  workingDirectory: "",
  enabled: true,
  toolsJson: "[]",
};

const EMPTY_SKILL_RESOLVE: SkillResolveState = {
  prompt: "",
  currentNotePath: "",
  activeTags: "",
  limit: "3",
};

const SKILL_IMPORT_PLACEHOLDER = `粘贴单个 skill 或 skill 数组的 JSON，例如：
{
  "id": "deep-review",
  "name": "Deep Review",
  "description": "在回答前深入核对证据",
  "prompt_prefix": "...",
  "when_to_use": "需要严谨审查时",
  "tool_subset": ["search_notes", "read_note"],
  "examples": ["研究", "research"],
  "keywords": ["研究", "审查"],
  "enabled": true
}`;

const MCP_SERVER_IMPORT_PLACEHOLDER = `粘贴单个 MCP server 或数组的 JSON，例如：
{
  "id": "research-hub",
  "name": "Research Hub",
  "description": "...",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "mcp-server-foo"],
  "env": {},
  "working_directory": null,
  "enabled": true,
  "tools": [
    { "name": "echo", "description": "", "input_schema": {}, "execution_mode": "builtin", "builtin_action": "echo", "enabled": true }
  ]
}`;

export function UtilityDrawer() {
  const { open, tab, activeTag, setUtilityDrawerOpen, setUtilityDrawerTab } = useUiStore(
    useShallow((state) => ({
      open: state.isUtilityDrawerOpen,
      tab: state.utilityDrawerTab,
      activeTag: state.activeTag,
      setUtilityDrawerOpen: state.setUtilityDrawerOpen,
      setUtilityDrawerTab: state.setUtilityDrawerTab,
    }))
  );
  const {
    conversation,
    conversationSummary,
    resumeContext,
    memoryCandidates,
    threadLoading,
    threadBusyAction,
    checkpointLabel,
    setCheckpointLabel,
    refreshThreadArtifacts,
    compactThread,
    createCheckpoint,
    acceptMemoryCandidate,
    rejectMemoryCandidate,
  } = useAgentConversation(
    useShallow((state) => ({
      conversation: state.conversation,
      conversationSummary: state.conversationSummary,
      resumeContext: state.resumeContext,
      memoryCandidates: state.memoryCandidates,
      threadLoading: state.threadLoading,
      threadBusyAction: state.threadBusyAction,
      checkpointLabel: state.checkpointLabel,
      setCheckpointLabel: state.setCheckpointLabel,
      refreshThreadArtifacts: state.refreshThreadArtifacts,
      compactThread: state.compactThread,
      createCheckpoint: state.createCheckpoint,
      acceptMemoryCandidate: state.acceptMemoryCandidate,
      rejectMemoryCandidate: state.rejectMemoryCandidate,
    }))
  );
  const {
    approvals,
    importDestinationDir,
    importTags,
    importSourcePath,
    importUrlValue,
    importStatus,
    skills,
    mcpServers,
    mcpCatalog,
    llmSettings,
    llmForm,
    llmSaving,
    llmTestResult,
    preferences,
    selectedPath,
    selectedKind,
    setImportDestinationDir,
    setImportTags,
    setImportSourcePath,
    setImportUrlValue,
    importFileFromState,
    importUrlFromState,
    decideApproval,
    clearError,
    setError,
    setLlmForm,
    refreshCapabilities,
    saveLLMSettingsFromForm,
    testLLMSettings,
  } = useWorkspaceStore(
    useShallow((state) => ({
      approvals: state.approvals,
      importDestinationDir: state.importDestinationDir,
      importTags: state.importTags,
      importSourcePath: state.importSourcePath,
      importUrlValue: state.importUrlValue,
      importStatus: state.importStatus,
      skills: state.skills,
      mcpServers: state.mcpServers,
      mcpCatalog: state.mcpCatalog,
      llmSettings: state.llmSettings,
      llmForm: state.llmForm,
      llmSaving: state.llmSaving,
      llmTestResult: state.llmTestResult,
      preferences: state.preferences,
      selectedPath: state.selectedPath,
      selectedKind: state.selectedKind,
      setImportDestinationDir: state.setImportDestinationDir,
      setImportTags: state.setImportTags,
      setImportSourcePath: state.setImportSourcePath,
      setImportUrlValue: state.setImportUrlValue,
      importFileFromState: state.importFileFromState,
      importUrlFromState: state.importUrlFromState,
      decideApproval: state.decideApproval,
      clearError: state.clearError,
      setError: state.setError,
      setLlmForm: state.setLlmForm,
      refreshCapabilities: state.refreshCapabilities,
      saveLLMSettingsFromForm: state.saveLLMSettingsFromForm,
      testLLMSettings: state.testLLMSettings,
    }))
  );

  const pendingCount = countPendingApprovals(approvals);
  const currentNotePath = selectedKind === "note" ? selectedPath ?? "" : "";
  const [skillEditor, setSkillEditor] = useState<SkillEditorState>(EMPTY_SKILL_EDITOR);
  const [skillEditorOpen, setSkillEditorOpen] = useState(false);
  const [skillImportOpen, setSkillImportOpen] = useState(false);
  const [skillImportText, setSkillImportText] = useState("");
  const [skillResolve, setSkillResolve] = useState<SkillResolveState>(() =>
    buildEmptySkillResolve(currentNotePath, activeTag)
  );
  const [skillResolveOpen, setSkillResolveOpen] = useState(false);
  const [resolvedSkills, setResolvedSkills] = useState<SkillDefinition[]>([]);
  const [skillResolveAttempted, setSkillResolveAttempted] = useState(false);
  const [mcpServerEditor, setMcpServerEditor] = useState<McpServerEditorState>(EMPTY_MCP_SERVER_EDITOR);
  const [mcpServerEditorOpen, setMcpServerEditorOpen] = useState(false);
  const [mcpImportOpen, setMcpImportOpen] = useState(false);
  const [mcpImportText, setMcpImportText] = useState("");
  const [mcpInvokeEditor, setMcpInvokeEditor] = useState<McpInvokeEditorState>(() =>
    buildEmptyInvokeEditor(preferences.default_note_dir || "Inbox", currentNotePath)
  );
  const [serverToolDefinitions, setServerToolDefinitions] = useState<MCPToolDefinition[] | null>(null);
  const [serverToolsLoading, setServerToolsLoading] = useState(false);
  const [serverToolsError, setServerToolsError] = useState("");
  const [capabilityBusyAction, setCapabilityBusyAction] = useState("");
  const [capabilityNotice, setCapabilityNotice] = useState("");
  const [invokeResult, setInvokeResult] = useState<MCPInvokeResult | null>(null);
  const invokableMcpServers = mcpServers.filter((server) => server.enabled);
  const activeMcpServer = invokableMcpServers.find((server) => server.id === mcpInvokeEditor.serverId) ?? null;
  const activeMcpTools = activeMcpServer ? (serverToolDefinitions ?? activeMcpServer.tools).filter((tool) => tool.enabled) : [];
  const activeMcpTool = activeMcpTools.find((tool) => tool.name === mcpInvokeEditor.toolName) ?? null;
  const capabilityBusy = Boolean(capabilityBusyAction);

  useEffect(() => {
    setSkillResolve((state) => {
      const nextCurrentNote = state.currentNotePath || currentNotePath;
      const nextActiveTags = state.activeTags || (activeTag ? activeTag : "");
      if (nextCurrentNote === state.currentNotePath && nextActiveTags === state.activeTags) {
        return state;
      }
      return {
        ...state,
        currentNotePath: nextCurrentNote,
        activeTags: nextActiveTags,
      };
    });
    setMcpInvokeEditor((state) => {
      const nextCurrentNote = state.currentNotePath || currentNotePath;
      const nextDefaultDir = state.defaultNoteDir || preferences.default_note_dir || "Inbox";
      if (nextCurrentNote === state.currentNotePath && nextDefaultDir === state.defaultNoteDir) {
        return state;
      }
      return {
        ...state,
        currentNotePath: nextCurrentNote,
        defaultNoteDir: nextDefaultDir,
      };
    });
  }, [activeTag, currentNotePath, preferences.default_note_dir]);

  function clearSkillResolveResults(): void {
    if (!skillResolveAttempted && !resolvedSkills.length) {
      return;
    }
    setResolvedSkills([]);
    setSkillResolveAttempted(false);
  }

  function updateSkillResolveState(patch: Partial<SkillResolveState>): void {
    clearSkillResolveResults();
    setSkillResolve((state) => ({ ...state, ...patch }));
  }

  function clearInvokeDebugResult(): void {
    if (invokeResult === null) {
      return;
    }
    setInvokeResult(null);
  }

  function updateMcpInvokeState(patch: Partial<McpInvokeEditorState>): void {
    clearInvokeDebugResult();
    setMcpInvokeEditor((state) => ({ ...state, ...patch }));
  }

  useEffect(() => {
    if (!mcpInvokeEditor.serverId || activeMcpServer) {
      return;
    }
    setServerToolsError("");
    setMcpInvokeEditor((state) => {
      if (!state.serverId) {
        return state;
      }
      return {
        ...state,
        serverId: "",
        toolName: "",
        argsJson: "{}",
      };
    });
    setInvokeResult(null);
  }, [activeMcpServer, mcpInvokeEditor.serverId]);

  useEffect(() => {
    let cancelled = false;
    const serverId = activeMcpServer?.id;
    if (!serverId) {
      setServerToolDefinitions(null);
      setServerToolsLoading(false);
      setServerToolsError("");
      return () => {
        cancelled = true;
      };
    }

    setServerToolsLoading(true);
    setServerToolDefinitions(null);
    setServerToolsError("");
    void listMcpServerTools(serverId)
      .then((tools) => {
        if (cancelled) {
          return;
        }
        setServerToolDefinitions(tools);
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        setServerToolDefinitions(activeMcpServer?.tools ?? []);
        setServerToolsError(`服务端 tools 同步失败，已回退到当前列表：${messageFromError(error)}`);
      })
      .finally(() => {
        if (!cancelled) {
          setServerToolsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeMcpServer?.id, activeMcpServer?.updated_at, activeMcpServer?.tools]);

  useEffect(() => {
    if (!mcpInvokeEditor.toolName || activeMcpTool) {
      return;
    }
    setMcpInvokeEditor((state) => {
      if (!state.toolName) {
        return state;
      }
      return {
        ...state,
        toolName: "",
        argsJson: "{}",
      };
    });
    setInvokeResult(null);
  }, [activeMcpTool, mcpInvokeEditor.toolName]);

  async function runCapabilityAction(action: string, fn: () => Promise<void>): Promise<void> {
    clearError();
    setCapabilityNotice("");
    setCapabilityBusyAction(action);
    try {
      await fn();
    } catch (error) {
      const message = messageFromError(error);
      setError(message);
      setCapabilityNotice(message);
    } finally {
      setCapabilityBusyAction("");
    }
  }

  async function copyTextToClipboard(payload: string): Promise<void> {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(payload);
      return;
    }
    if (typeof document !== "undefined") {
      const textarea = document.createElement("textarea");
      textarea.value = payload;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "absolute";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand("copy");
      } finally {
        document.body.removeChild(textarea);
      }
    }
  }

  function coerceImportedSkill(raw: Record<string, unknown>): SkillEditorState {
    const idSeed = String(raw.id ?? "").trim();
    const nameSeed = String(raw.name ?? "").trim();
    const skillId = normalizeIdentifier(idSeed, nameSeed);
    return {
      skillId: skillId || idSeed,
      name: nameSeed || skillId,
      description: String(raw.description ?? ""),
      promptPrefix: String(raw.prompt_prefix ?? raw.promptPrefix ?? ""),
      whenToUse: String(raw.when_to_use ?? raw.whenToUse ?? ""),
      toolSubset: Array.isArray(raw.tool_subset ?? raw.toolSubset)
        ? ((raw.tool_subset ?? raw.toolSubset) as unknown[]).map((item) => String(item)).join(", ")
        : "",
      examples: Array.isArray(raw.examples)
        ? (raw.examples as unknown[]).map((item) => String(item)).join(", ")
        : "",
      keywords: Array.isArray(raw.keywords)
        ? (raw.keywords as unknown[]).map((item) => String(item)).join(", ")
        : "",
      enabled: raw.enabled === undefined ? true : Boolean(raw.enabled),
    };
  }

  async function handleImportSkillJson(): Promise<void> {
    const text = skillImportText.trim();
    if (!text) {
      setError("请先粘贴 skill JSON。");
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (err) {
      setError(`skill JSON 解析失败：${messageFromError(err)}`);
      return;
    }
    const items = Array.isArray(parsed) ? parsed : [parsed];
    const valid = items.filter(
      (item): item is Record<string, unknown> =>
        !!item && typeof item === "object" && !Array.isArray(item)
    );
    if (!valid.length) {
      setError("JSON 必须是 skill 对象或对象数组。");
      return;
    }
    if (valid.length === 1) {
      const editorState = coerceImportedSkill(valid[0]);
      if (!editorState.skillId) {
        setError("导入的 skill 缺少可识别的 id 或 name。");
        return;
      }
      setSkillEditor(editorState);
      setSkillEditorOpen(true);
      setSkillImportOpen(false);
      setSkillImportText("");
      setCapabilityNotice("已将 JSON 载入编辑器，请确认后保存。");
      return;
    }
    await runCapabilityAction("skill:import", async () => {
      let ok = 0;
      const errors: string[] = [];
      for (const item of valid) {
        const editorState = coerceImportedSkill(item);
        if (!editorState.skillId) {
          errors.push("跳过缺少 id/name 的一项");
          continue;
        }
        try {
          await upsertSkill(editorState.skillId, {
            name: editorState.name || editorState.skillId,
            description: editorState.description,
            prompt_prefix: editorState.promptPrefix,
            when_to_use: editorState.whenToUse,
            tool_subset: parseDelimitedList(editorState.toolSubset),
            examples: parseDelimitedList(editorState.examples),
            keywords: parseDelimitedList(editorState.keywords),
            enabled: editorState.enabled,
          });
          ok += 1;
        } catch (err) {
          errors.push(`${editorState.skillId}: ${messageFromError(err)}`);
        }
      }
      await refreshCapabilities();
      setSkillImportOpen(false);
      setSkillImportText("");
      const summary = `已导入 ${ok} / ${valid.length} 个 skill。`;
      setCapabilityNotice(errors.length ? `${summary}\n${errors.join("\n")}` : summary);
    });
  }

  async function handleCopySkillJson(skill: SkillDefinition): Promise<void> {
    const payload = JSON.stringify(
      {
        id: skill.id,
        name: skill.name,
        description: skill.description,
        prompt_prefix: skill.prompt_prefix,
        when_to_use: skill.when_to_use,
        tool_subset: skill.tool_subset,
        examples: skill.examples,
        keywords: skill.keywords,
        enabled: skill.enabled,
      },
      null,
      2
    );
    try {
      await copyTextToClipboard(payload);
      setCapabilityNotice(`已复制 skill ${skill.id} 的 JSON。`);
    } catch (err) {
      setError(`复制失败：${messageFromError(err)}`);
    }
  }

  function coerceImportedMcpServer(raw: Record<string, unknown>): McpServerEditorState {
    const idSeed = String(raw.id ?? "").trim();
    const nameSeed = String(raw.name ?? "").trim();
    const serverId = normalizeIdentifier(idSeed, nameSeed);
    const toolsSource = Array.isArray(raw.tools) ? raw.tools : [];
    const envSource = raw.env && typeof raw.env === "object" && !Array.isArray(raw.env) ? raw.env : {};
    return {
      serverId: serverId || idSeed,
      name: nameSeed || serverId,
      description: String(raw.description ?? ""),
      transport: String(raw.transport ?? "builtin"),
      command: String(raw.command ?? ""),
      argsText: Array.isArray(raw.args)
        ? (raw.args as unknown[]).map((item) => String(item)).join(", ")
        : "",
      envJson: Object.keys(envSource as Record<string, unknown>).length
        ? JSON.stringify(envSource, null, 2)
        : "{}",
      workingDirectory: raw.working_directory ? String(raw.working_directory) : "",
      enabled: raw.enabled === undefined ? true : Boolean(raw.enabled),
      toolsJson: JSON.stringify(toolsSource, null, 2),
    };
  }

  async function handleImportMcpServerJson(): Promise<void> {
    const text = mcpImportText.trim();
    if (!text) {
      setError("请先粘贴 MCP server JSON。");
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (err) {
      setError(`MCP server JSON 解析失败：${messageFromError(err)}`);
      return;
    }
    const items = Array.isArray(parsed) ? parsed : [parsed];
    const valid = items.filter(
      (item): item is Record<string, unknown> =>
        !!item && typeof item === "object" && !Array.isArray(item)
    );
    if (!valid.length) {
      setError("JSON 必须是 MCP server 对象或对象数组。");
      return;
    }
    if (valid.length === 1) {
      const editorState = coerceImportedMcpServer(valid[0]);
      if (!editorState.serverId) {
        setError("导入的 MCP server 缺少可识别的 id 或 name。");
        return;
      }
      setMcpServerEditor(editorState);
      setMcpServerEditorOpen(true);
      setMcpImportOpen(false);
      setMcpImportText("");
      setCapabilityNotice("已将 JSON 载入编辑器，请确认后保存。");
      return;
    }
    await runCapabilityAction("mcp:import", async () => {
      let ok = 0;
      const errors: string[] = [];
      for (const item of valid) {
        const editorState = coerceImportedMcpServer(item);
        if (!editorState.serverId) {
          errors.push("跳过缺少 id/name 的一项");
          continue;
        }
        try {
          await upsertMcpServer(editorState.serverId, {
            name: editorState.name || editorState.serverId,
            description: editorState.description,
            transport: editorState.transport || "builtin",
            command: editorState.command || undefined,
            args: parseDelimitedList(editorState.argsText),
            env: parseEnvJson(editorState.envJson),
            working_directory: editorState.workingDirectory || null,
            enabled: editorState.enabled,
            tools: parseMcpTools(editorState.toolsJson),
          });
          ok += 1;
        } catch (err) {
          errors.push(`${editorState.serverId}: ${messageFromError(err)}`);
        }
      }
      await refreshCapabilities();
      setMcpImportOpen(false);
      setMcpImportText("");
      const summary = `已导入 ${ok} / ${valid.length} 个 MCP server。`;
      setCapabilityNotice(errors.length ? `${summary}\n${errors.join("\n")}` : summary);
    });
  }

  async function handleCopyMcpServerJson(server: MCPServerDefinition): Promise<void> {
    const payload = JSON.stringify(
      {
        id: server.id,
        name: server.name,
        description: server.description,
        transport: server.transport,
        command: server.command,
        args: server.args,
        env: server.env,
        working_directory: server.working_directory,
        enabled: server.enabled,
        tools: server.tools,
      },
      null,
      2
    );
    try {
      await copyTextToClipboard(payload);
      setCapabilityNotice(`已复制 MCP server ${server.id} 的 JSON。`);
    } catch (err) {
      setError(`复制失败：${messageFromError(err)}`);
    }
  }

  async function handleSaveSkill(): Promise<void> {
    const skillId = normalizeIdentifier(skillEditor.skillId, skillEditor.name);
    if (!skillId) {
      setError("请先填写 skill id 或名称。");
      return;
    }
    await runCapabilityAction(`skill:save:${skillId}`, async () => {
      const saved = await upsertSkill(skillId, {
        name: skillEditor.name.trim() || skillId,
        description: skillEditor.description.trim(),
        prompt_prefix: skillEditor.promptPrefix.trim(),
        when_to_use: skillEditor.whenToUse.trim(),
        tool_subset: parseDelimitedList(skillEditor.toolSubset),
        examples: parseDelimitedList(skillEditor.examples),
        keywords: parseDelimitedList(skillEditor.keywords),
        enabled: skillEditor.enabled,
      });
      await refreshCapabilities();
      setSkillEditor(toSkillEditorState(saved));
      setCapabilityNotice(`已保存 skill：${saved.id}`);
    });
  }

  async function handleDeleteSkill(skillId: string): Promise<void> {
    if (typeof window !== "undefined" && !window.confirm(`确认删除 skill ${skillId}？`)) {
      return;
    }
    await runCapabilityAction(`skill:delete:${skillId}`, async () => {
      await deleteSkill(skillId);
      await refreshCapabilities();
      if (skillEditor.skillId === skillId) {
        setSkillEditor(EMPTY_SKILL_EDITOR);
      }
      setCapabilityNotice(`已删除 skill：${skillId}`);
    });
  }

  async function handleResolveSkills(): Promise<void> {
    const prompt = skillResolve.prompt.trim();
    if (!prompt) {
      setError("请先填写用于 resolve 的 prompt。");
      return;
    }
    await runCapabilityAction("skill:resolve", async () => {
      const matches = await resolveSkills({
        prompt,
        currentNotePath: skillResolve.currentNotePath.trim() || currentNotePath || undefined,
        activeTags: parseDelimitedList(skillResolve.activeTags),
        limit: Number.parseInt(skillResolve.limit, 10) || 3,
      });
      setResolvedSkills(matches);
      setSkillResolveAttempted(true);
      setCapabilityNotice(matches.length ? `已解析 ${matches.length} 个 skill 命中。` : "当前 prompt 没有命中任何 skill。");
    });
  }

  async function handleSaveMcpServer(): Promise<void> {
    const serverId = normalizeIdentifier(mcpServerEditor.serverId, mcpServerEditor.name);
    if (!serverId) {
      setError("请先填写 MCP server id 或名称。");
      return;
    }
    await runCapabilityAction(`mcp:save:${serverId}`, async () => {
      const saved = await upsertMcpServer(serverId, {
        name: mcpServerEditor.name.trim() || serverId,
        description: mcpServerEditor.description.trim(),
        transport: mcpServerEditor.transport.trim() || "builtin",
        command: mcpServerEditor.command.trim() || undefined,
        args: parseDelimitedList(mcpServerEditor.argsText),
        env: parseEnvJson(mcpServerEditor.envJson),
        working_directory: mcpServerEditor.workingDirectory.trim() || null,
        enabled: mcpServerEditor.enabled,
        tools: parseMcpTools(mcpServerEditor.toolsJson),
      });
      await refreshCapabilities();
      setMcpServerEditor(toMcpServerEditorState(saved));
      updateMcpInvokeState({
        serverId: saved.enabled ? saved.id : "",
        toolName: "",
        argsJson: "{}",
      });
      setCapabilityNotice(`已保存 MCP server：${saved.id}`);
    });
  }

  async function handleDeleteMcpServer(serverId: string): Promise<void> {
    if (typeof window !== "undefined" && !window.confirm(`确认删除 MCP server ${serverId}？`)) {
      return;
    }
    await runCapabilityAction(`mcp:delete:${serverId}`, async () => {
      await deleteMcpServer(serverId);
      await refreshCapabilities();
      if (mcpServerEditor.serverId === serverId) {
        setMcpServerEditor(EMPTY_MCP_SERVER_EDITOR);
      }
      if (mcpInvokeEditor.serverId === serverId) {
        setMcpInvokeEditor(buildEmptyInvokeEditor(preferences.default_note_dir || "Inbox", currentNotePath));
        setInvokeResult(null);
      }
      setCapabilityNotice(`已删除 MCP server：${serverId}`);
    });
  }

  async function handleInvokeMcpTool(): Promise<void> {
    const serverId = activeMcpServer?.id ?? "";
    const toolName = activeMcpTool?.name ?? "";
    if (!serverId || !toolName) {
      setError("请先选择可执行的 MCP server 和 tool。");
      return;
    }
    await runCapabilityAction(`mcp:invoke:${serverId}:${toolName}`, async () => {
      const result = await invokeMcpTool(serverId, toolName, {
        args: parseInvokeArgs(mcpInvokeEditor.argsJson),
        prompt: mcpInvokeEditor.prompt.trim() || undefined,
        current_note_path: mcpInvokeEditor.currentNotePath.trim() || currentNotePath || undefined,
        default_note_dir: mcpInvokeEditor.defaultNoteDir.trim() || preferences.default_note_dir || "Inbox",
      });
      setInvokeResult(result);
      setCapabilityNotice(result.ok ? `已执行 MCP 工具：${toolName}` : `MCP 工具执行失败：${toolName}`);
    });
  }

  return (
    <>
      <div className={`drawer-overlay ${open ? "drawer-overlay-open" : ""}`} onClick={() => setUtilityDrawerOpen(false)} />
      <aside className={`utility-drawer ${open ? "utility-drawer-open" : ""}`}>
        <div className="drawer-grip-shell" aria-hidden="true">
          <div className="drawer-grip" />
        </div>

        <div className="flex items-start justify-between border-b border-slate-200/80 px-5 py-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">工具</div>
            <div className="mt-1 text-base font-semibold text-slate-950">线程、能力、导入、审批与模型设置</div>
          </div>
          <button className="icon-button" onClick={() => setUtilityDrawerOpen(false)} aria-label="关闭工具抽屉">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex flex-wrap gap-2 border-b border-slate-200/80 px-4 py-3">
          <DrawerTab active={tab === "thread"} icon={<Sparkles className="h-4 w-4" />} label="线程" onClick={() => setUtilityDrawerTab("thread")} />
          <DrawerTab active={tab === "capabilities"} icon={<BrainCircuit className="h-4 w-4" />} label="能力" onClick={() => setUtilityDrawerTab("capabilities")} />
          <DrawerTab active={tab === "import"} icon={<Upload className="h-4 w-4" />} label="导入" onClick={() => setUtilityDrawerTab("import")} />
          <DrawerTab
            active={tab === "approvals"}
            icon={<ShieldCheck className="h-4 w-4" />}
            label={pendingCount ? `审批 (${pendingCount})` : "审批"}
            onClick={() => setUtilityDrawerTab("approvals")}
          />
          <DrawerTab
            active={tab === "settings"}
            icon={<Settings2 className="h-4 w-4" />}
            label="模型设置"
            onClick={() => setUtilityDrawerTab("settings")}
          />
        </div>

        <div
          className={`min-h-0 flex-1 overflow-auto px-4 py-4 transition-[opacity,transform] duration-150 ${
            open ? "translate-y-0 opacity-100" : "translate-y-1 opacity-0"
          }`}
        >
          {tab === "thread" ? (
            <section className="space-y-3">
              {conversation ? (
                <>
                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-slate-900">{conversation.title || "当前线程"}</div>
                        <div className="mt-1 text-xs text-slate-500">
                          {conversationSummary?.conversation.active_note_path || resumeContext?.active_note?.relative_path || "当前线程未绑定笔记"}
                        </div>
                      </div>
                      <span className="meta-pill">{conversationSummary?.summary_state || conversation.compression_state || "ok"}</span>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-500">
                      <div className="rounded-xl border border-slate-200 bg-slate-50/70 px-3 py-2">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-slate-400">pending tokens</div>
                        <div className="mt-1 text-sm font-medium text-slate-800">
                          {String(conversationSummary?.budget?.pending_tokens ?? resumeContext?.budget?.pending_tokens ?? 0)}
                        </div>
                      </div>
                      <div className="rounded-xl border border-slate-200 bg-slate-50/70 px-3 py-2">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-slate-400">checkpoints</div>
                        <div className="mt-1 text-sm font-medium text-slate-800">{resumeContext?.checkpoints.length ?? 0}</div>
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        className="compact-button compact-button-muted"
                        disabled={threadLoading || Boolean(threadBusyAction)}
                        onClick={() => void refreshThreadArtifacts()}
                      >
                        <RefreshCcw className="h-4 w-4" />
                        刷新
                      </button>
                      <button
                        className="compact-button compact-button-muted"
                        disabled={threadLoading || Boolean(threadBusyAction)}
                        onClick={() => void compactThread()}
                      >
                        <Archive className="h-4 w-4" />
                        压缩线程
                      </button>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">保存检查点</div>
                    <div className="flex gap-2">
                      <input
                        className="soft-input"
                        value={checkpointLabel}
                        onChange={(event) => setCheckpointLabel(event.target.value)}
                        placeholder="例如：整理前"
                      />
                      <button
                        className="compact-button compact-button-strong shrink-0"
                        disabled={threadLoading || Boolean(threadBusyAction)}
                        onClick={() => void createCheckpoint()}
                      >
                        <BookmarkPlus className="h-4 w-4" />
                        保存
                      </button>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">线程摘要</div>
                      {threadLoading ? <span className="meta-pill meta-pill-subtle">同步中</span> : null}
                    </div>
                    <div className="text-sm leading-6 text-slate-700">
                      {conversationSummary?.conversation.summary?.trim() || "当前线程还没有稳定摘要。完成更多轮对话后会逐步沉淀。"}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">最近上下文</div>
                    {resumeContext?.recent_messages.length ? (
                      <div className="space-y-2">
                        {resumeContext.recent_messages.slice(-4).map((message) => (
                          <div key={message.id} className="rounded-xl border border-slate-200/80 bg-slate-50/60 px-3 py-2">
                            <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">{message.role}</div>
                            <div className="mt-1 line-clamp-3 text-sm leading-6 text-slate-700">{message.content}</div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">当前线程还没有可回放的最近消息。</div>
                    )}
                  </div>

                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">检查点</div>
                    {resumeContext?.checkpoints.length ? (
                      <div className="space-y-2">
                        {resumeContext.checkpoints.map((checkpoint) => (
                          <div key={checkpoint.id} className="rounded-xl border border-slate-200/80 bg-slate-50/60 px-3 py-2.5">
                            <div className="flex items-start justify-between gap-3">
                              <div className="text-sm font-medium text-slate-800">{checkpoint.label}</div>
                              <span className="meta-pill meta-pill-subtle">{checkpoint.token_estimate}</span>
                            </div>
                            <div className="mt-1 text-xs leading-5 text-slate-500">{checkpoint.summary || "暂无摘要"}</div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">当前线程还没有保存检查点。</div>
                    )}
                  </div>

                  <div className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">记忆候选</div>
                    {memoryCandidates.length ? (
                      <div className="space-y-3">
                        {memoryCandidates.map((candidate) => {
                          const accepting = threadBusyAction === `accept:${candidate.id}`;
                          const rejecting = threadBusyAction === `reject:${candidate.id}`;
                          return (
                            <div key={candidate.id} className="rounded-xl border border-slate-200/80 bg-slate-50/60 px-3 py-3">
                              <div className="flex items-start justify-between gap-3">
                                <div>
                                  <div className="text-sm font-medium text-slate-800">{candidate.value}</div>
                                  <div className="mt-1 text-[11px] text-slate-500">
                                    {candidate.kind} · 置信度 {Math.round(candidate.confidence * 100)}%
                                  </div>
                                </div>
                                <span className="meta-pill meta-pill-subtle">{candidate.status}</span>
                              </div>
                              {candidate.status === "pending" ? (
                                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                                  <button
                                    className="compact-button compact-button-strong justify-center"
                                    disabled={threadLoading || Boolean(threadBusyAction)}
                                    onClick={() => void acceptMemoryCandidate(candidate.id)}
                                  >
                                    {accepting ? "保存中..." : "接受"}
                                  </button>
                                  <button
                                    className="compact-button compact-button-muted justify-center"
                                    disabled={threadLoading || Boolean(threadBusyAction)}
                                    onClick={() => void rejectMemoryCandidate(candidate.id)}
                                  >
                                    {rejecting ? "处理中..." : "忽略"}
                                  </button>
                                </div>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">当前线程还没有新的记忆候选。</div>
                    )}
                  </div>
                </>
              ) : (
                <div className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">
                  开始一次助手对话后，这里会显示线程摘要、最近上下文、检查点和记忆候选。
                </div>
              )}
            </section>
          ) : null}

          {tab === "capabilities" ? (
            <section className="space-y-3">
              {capabilityNotice ? (
                <div className="rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-3 text-sm text-slate-600">{capabilityNotice}</div>
              ) : null}

              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                    <BrainCircuit className="h-3.5 w-3.5" />
                    Skills
                    <span className="text-[10px] font-normal normal-case tracking-normal text-slate-400">({skills.length})</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      className="compact-button compact-button-strong"
                      disabled={capabilityBusy}
                      onClick={() => {
                        setSkillEditor(EMPTY_SKILL_EDITOR);
                        setSkillEditorOpen(true);
                        setSkillImportOpen(false);
                      }}
                    >
                      <Plus className="h-4 w-4" />
                      新建
                    </button>
                    <button
                      className="compact-button compact-button-muted"
                      disabled={capabilityBusy}
                      onClick={() => {
                        setSkillImportOpen((prev) => !prev);
                        setSkillEditorOpen(false);
                      }}
                    >
                      <ClipboardCopy className="h-4 w-4" />
                      粘贴 JSON 导入
                    </button>
                  </div>
                </div>

                {skillImportOpen ? (
                  <div className="mb-3 rounded-xl border border-slate-200/80 bg-slate-50/40 p-3 space-y-2">
                    <textarea
                      className="soft-input min-h-[140px] font-mono text-[12px] leading-6"
                      value={skillImportText}
                      onChange={(event) => setSkillImportText(event.target.value)}
                      placeholder={SKILL_IMPORT_PLACEHOLDER}
                    />
                    <div className="flex flex-wrap gap-2">
                      <button className="compact-button compact-button-strong" disabled={capabilityBusy} onClick={() => void handleImportSkillJson()}>
                        解析并载入
                      </button>
                      <button
                        className="compact-button compact-button-muted"
                        disabled={capabilityBusy}
                        onClick={() => {
                          setSkillImportOpen(false);
                          setSkillImportText("");
                        }}
                      >
                        取消
                      </button>
                    </div>
                    <div className="text-[11px] leading-5 text-slate-500">
                      支持粘贴单个对象（载入编辑器预览）或对象数组（批量导入）。可让 AI 生成符合格式的 JSON 后直接粘贴。
                    </div>
                  </div>
                ) : null}

                {skillEditorOpen ? (
                  <div className="space-y-2 rounded-xl border border-slate-200/80 bg-slate-50/40 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                        {skillEditor.skillId ? `编辑：${skillEditor.skillId}` : "新建 skill"}
                      </div>
                      <button
                        className="compact-button compact-button-muted"
                        disabled={capabilityBusy}
                        onClick={() => {
                          setSkillEditor(EMPTY_SKILL_EDITOR);
                          setSkillEditorOpen(false);
                        }}
                      >
                        <X className="h-4 w-4" />
                        关闭
                      </button>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <input
                        className="soft-input"
                        value={skillEditor.skillId}
                        onChange={(event) => setSkillEditor((state) => ({ ...state, skillId: event.target.value }))}
                        placeholder="skill id，例如 deep-review"
                      />
                      <input
                        className="soft-input"
                        value={skillEditor.name}
                        onChange={(event) => setSkillEditor((state) => ({ ...state, name: event.target.value }))}
                        placeholder="显示名称"
                      />
                    </div>
                    <textarea
                      className="soft-input min-h-[72px]"
                      value={skillEditor.description}
                      onChange={(event) => setSkillEditor((state) => ({ ...state, description: event.target.value }))}
                      placeholder="技能描述"
                    />
                    <textarea
                      className="soft-input min-h-[92px]"
                      value={skillEditor.promptPrefix}
                      onChange={(event) => setSkillEditor((state) => ({ ...state, promptPrefix: event.target.value }))}
                      placeholder="prompt prefix"
                    />
                    <input
                      className="soft-input"
                      value={skillEditor.whenToUse}
                      onChange={(event) => setSkillEditor((state) => ({ ...state, whenToUse: event.target.value }))}
                      placeholder="when to use"
                    />
                    <div className="grid gap-2 sm:grid-cols-2">
                      <input
                        className="soft-input"
                        value={skillEditor.keywords}
                        onChange={(event) => setSkillEditor((state) => ({ ...state, keywords: event.target.value }))}
                        placeholder="keywords，逗号或换行分隔"
                      />
                      <input
                        className="soft-input"
                        value={skillEditor.toolSubset}
                        onChange={(event) => setSkillEditor((state) => ({ ...state, toolSubset: event.target.value }))}
                        placeholder="tool subset，逗号或换行分隔"
                      />
                    </div>
                    <input
                      className="soft-input"
                      value={skillEditor.examples}
                      onChange={(event) => setSkillEditor((state) => ({ ...state, examples: event.target.value }))}
                      placeholder="examples，逗号或换行分隔"
                    />
                    <label className="flex items-center gap-2 text-sm text-slate-600">
                      <input
                        type="checkbox"
                        checked={skillEditor.enabled}
                        onChange={(event) => setSkillEditor((state) => ({ ...state, enabled: event.target.checked }))}
                      />
                      启用 skill
                    </label>
                    <div className="flex flex-wrap gap-2">
                      <button className="compact-button compact-button-strong" disabled={capabilityBusy} onClick={() => void handleSaveSkill()}>
                        保存 skill
                      </button>
                      <button
                        className="compact-button compact-button-muted"
                        disabled={capabilityBusy}
                        onClick={() => setSkillEditor(EMPTY_SKILL_EDITOR)}
                      >
                        重置字段
                      </button>
                    </div>
                  </div>
                ) : null}

                {skills.length ? (
                  <div className="mt-3 space-y-2">
                    {skills.map((skill) => (
                      <div key={skill.id} className="rounded-xl border border-slate-200/80 bg-slate-50/60 px-3 py-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-slate-800 truncate">{skill.name}</div>
                            <div className="mt-1 text-xs leading-5 text-slate-500 line-clamp-2">{skill.description || skill.when_to_use || "暂无说明"}</div>
                          </div>
                          <div className="flex flex-wrap items-center justify-end gap-1.5 shrink-0">
                            <span className="meta-pill meta-pill-subtle">{skill.id}</span>
                            {!skill.enabled ? <span className="meta-pill meta-pill-subtle">已禁用</span> : null}
                          </div>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <button
                            className="compact-button compact-button-muted"
                            disabled={capabilityBusy}
                            onClick={() => {
                              setSkillEditor(toSkillEditorState(skill));
                              setSkillEditorOpen(true);
                              setSkillImportOpen(false);
                            }}
                          >
                            <Pencil className="h-4 w-4" />
                            编辑
                          </button>
                          <button className="compact-button compact-button-muted" disabled={capabilityBusy} onClick={() => void handleCopySkillJson(skill)}>
                            <ClipboardCopy className="h-4 w-4" />
                            复制 JSON
                          </button>
                          <button className="compact-button compact-button-muted" disabled={capabilityBusy} onClick={() => void handleDeleteSkill(skill.id)}>
                            <Trash2 className="h-4 w-4" />
                            删除
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-3 rounded-xl border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">
                    当前工作区还没有 skills。点击 <span className="font-medium text-slate-700">新建</span> 手动创建，或 <span className="font-medium text-slate-700">粘贴 JSON 导入</span> 一键导入。
                  </div>
                )}
                <div className="mt-4 rounded-xl border border-slate-200/80 bg-slate-50/40 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Skill Resolve 调试</div>
                    <div className="flex items-center gap-2">
                      {skillResolveOpen ? (
                        <button
                          className="compact-button compact-button-muted"
                          disabled={capabilityBusy}
                          onClick={() => {
                            setSkillResolve(buildEmptySkillResolve(currentNotePath, activeTag));
                            clearSkillResolveResults();
                          }}
                        >
                          重置
                        </button>
                      ) : null}
                      <button
                        className="compact-button compact-button-muted"
                        disabled={capabilityBusy}
                        onClick={() => setSkillResolveOpen((prev) => !prev)}
                      >
                        {skillResolveOpen ? "收起" : "展开"}
                      </button>
                    </div>
                  </div>
                  {skillResolveOpen ? (
                  <div className="mt-3 space-y-2">
                    <textarea
                      className="soft-input min-h-[104px]"
                      value={skillResolve.prompt}
                      onChange={(event) => updateSkillResolveState({ prompt: event.target.value })}
                      placeholder="输入一个 prompt，查看后端会解析出哪些 skills"
                    />
                    <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_132px]">
                      <input
                        className="soft-input"
                        value={skillResolve.currentNotePath}
                        onChange={(event) => updateSkillResolveState({ currentNotePath: event.target.value })}
                        placeholder={currentNotePath || "current_note_path（可选）"}
                      />
                      <select
                        className="soft-input"
                        value={skillResolve.limit}
                        onChange={(event) => updateSkillResolveState({ limit: event.target.value })}
                      >
                        <option value="1">Top 1</option>
                        <option value="2">Top 2</option>
                        <option value="3">Top 3</option>
                        <option value="5">Top 5</option>
                        <option value="10">Top 10</option>
                      </select>
                    </div>
                    <input
                      className="soft-input"
                      value={skillResolve.activeTags}
                      onChange={(event) => updateSkillResolveState({ activeTags: event.target.value })}
                      placeholder={activeTag ? `active tags，当前标签：${activeTag}` : "active tags，逗号或换行分隔"}
                    />
                    <div className="flex flex-wrap gap-2">
                      <button className="compact-button compact-button-strong" disabled={capabilityBusy} onClick={() => void handleResolveSkills()}>
                        解析 skills
                      </button>
                      <button
                        className="compact-button compact-button-muted"
                        disabled={capabilityBusy}
                        onClick={() =>
                          updateSkillResolveState({
                            currentNotePath: skillResolve.currentNotePath || currentNotePath,
                            activeTags: skillResolve.activeTags || (activeTag ? activeTag : ""),
                          })
                        }
                      >
                        带入当前上下文
                      </button>
                    </div>
                    {resolvedSkills.length ? (
                      <div className="space-y-2">
                        {resolvedSkills.map((skill, index) => (
                          <div key={`${skill.id}-${index}`} className="rounded-xl border border-slate-200 bg-white px-3 py-3">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <div className="text-sm font-medium text-slate-800">{skill.name}</div>
                                <div className="mt-1 text-xs leading-5 text-slate-500">{skill.when_to_use || skill.description || "暂无说明"}</div>
                              </div>
                              <span className="meta-pill meta-pill-subtle">#{index + 1}</span>
                            </div>
                            {skill.tool_subset.length ? <div className="mt-2 text-[11px] text-slate-500">工具子集：{skill.tool_subset.join("，")}</div> : null}
                            <div className="mt-3">
                              <button className="compact-button compact-button-muted" disabled={capabilityBusy} onClick={() => setSkillEditor(toSkillEditorState(skill))}>
                                <Pencil className="h-4 w-4" />
                                载入到编辑器
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : skillResolveAttempted ? (
                      <div className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">当前输入下没有命中任何 skill。</div>
                    ) : null}
                  </div>
                  ) : null}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                    <Waypoints className="h-3.5 w-3.5" />
                    MCP Servers
                    <span className="text-[10px] font-normal normal-case tracking-normal text-slate-400">({mcpServers.length})</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      className="compact-button compact-button-strong"
                      disabled={capabilityBusy}
                      onClick={() => {
                        setMcpServerEditor(EMPTY_MCP_SERVER_EDITOR);
                        setMcpServerEditorOpen(true);
                        setMcpImportOpen(false);
                      }}
                    >
                      <Plus className="h-4 w-4" />
                      新建
                    </button>
                    <button
                      className="compact-button compact-button-muted"
                      disabled={capabilityBusy}
                      onClick={() => {
                        setMcpImportOpen((prev) => !prev);
                        setMcpServerEditorOpen(false);
                      }}
                    >
                      <ClipboardCopy className="h-4 w-4" />
                      粘贴 JSON 导入
                    </button>
                  </div>
                </div>

                {mcpImportOpen ? (
                  <div className="mb-3 rounded-xl border border-slate-200/80 bg-slate-50/40 p-3 space-y-2">
                    <textarea
                      className="soft-input min-h-[160px] font-mono text-[12px] leading-6"
                      value={mcpImportText}
                      onChange={(event) => setMcpImportText(event.target.value)}
                      placeholder={MCP_SERVER_IMPORT_PLACEHOLDER}
                    />
                    <div className="flex flex-wrap gap-2">
                      <button className="compact-button compact-button-strong" disabled={capabilityBusy} onClick={() => void handleImportMcpServerJson()}>
                        解析并载入
                      </button>
                      <button
                        className="compact-button compact-button-muted"
                        disabled={capabilityBusy}
                        onClick={() => {
                          setMcpImportOpen(false);
                          setMcpImportText("");
                        }}
                      >
                        取消
                      </button>
                    </div>
                    <div className="text-[11px] leading-5 text-slate-500">
                      支持粘贴单个对象（载入编辑器预览）或对象数组（批量导入）。
                    </div>
                  </div>
                ) : null}

                {mcpServerEditorOpen ? (
                  <div className="space-y-2 rounded-xl border border-slate-200/80 bg-slate-50/40 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                        {mcpServerEditor.serverId ? `编辑：${mcpServerEditor.serverId}` : "新建 MCP server"}
                      </div>
                      <button
                        className="compact-button compact-button-muted"
                        disabled={capabilityBusy}
                        onClick={() => {
                          setMcpServerEditor(EMPTY_MCP_SERVER_EDITOR);
                          setMcpServerEditorOpen(false);
                        }}
                      >
                        <X className="h-4 w-4" />
                        关闭
                      </button>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <input
                        className="soft-input"
                        value={mcpServerEditor.serverId}
                        onChange={(event) => setMcpServerEditor((state) => ({ ...state, serverId: event.target.value }))}
                        placeholder="server id，例如 research-hub"
                      />
                      <input
                        className="soft-input"
                        value={mcpServerEditor.name}
                        onChange={(event) => setMcpServerEditor((state) => ({ ...state, name: event.target.value }))}
                        placeholder="显示名称"
                      />
                    </div>
                    <select
                      className="soft-input"
                      value={mcpServerEditor.transport}
                      onChange={(event) => setMcpServerEditor((state) => ({ ...state, transport: event.target.value }))}
                    >
                      <option value="builtin">builtin</option>
                      <option value="stdio">stdio</option>
                    </select>
                    {mcpServerEditor.transport === "stdio" ? (
                      <div className="space-y-2 rounded-xl border border-slate-200/80 bg-white/60 p-3">
                        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">stdio 连接</div>
                        <input
                          className="soft-input"
                          value={mcpServerEditor.command}
                          onChange={(event) => setMcpServerEditor((state) => ({ ...state, command: event.target.value }))}
                          placeholder="可执行命令，例如 npx 或 python"
                        />
                        <input
                          className="soft-input"
                          value={mcpServerEditor.argsText}
                          onChange={(event) => setMcpServerEditor((state) => ({ ...state, argsText: event.target.value }))}
                          placeholder="参数，逗号分隔，例如 -m,mcp_server"
                        />
                        <input
                          className="soft-input"
                          value={mcpServerEditor.workingDirectory}
                          onChange={(event) => setMcpServerEditor((state) => ({ ...state, workingDirectory: event.target.value }))}
                          placeholder="工作目录（可选）"
                        />
                        <textarea
                          className="soft-input min-h-[60px] font-mono text-[12px] leading-6"
                          value={mcpServerEditor.envJson}
                          onChange={(event) => setMcpServerEditor((state) => ({ ...state, envJson: event.target.value }))}
                          placeholder='环境变量 JSON，例如 {"API_KEY":"xxx"}'
                        />
                      </div>
                    ) : null}
                    <textarea
                      className="soft-input min-h-[72px]"
                      value={mcpServerEditor.description}
                      onChange={(event) => setMcpServerEditor((state) => ({ ...state, description: event.target.value }))}
                      placeholder="server 描述"
                    />
                    <textarea
                      className="soft-input min-h-[160px] font-mono text-[12px] leading-6"
                      value={mcpServerEditor.toolsJson}
                      onChange={(event) => setMcpServerEditor((state) => ({ ...state, toolsJson: event.target.value }))}
                      placeholder='tools JSON，例如 [{"name":"echo","description":"Echo","input_schema":{"text":"string"},"execution_mode":"builtin","builtin_action":"echo","enabled":true}]'
                    />
                    <label className="flex items-center gap-2 text-sm text-slate-600">
                      <input
                        type="checkbox"
                        checked={mcpServerEditor.enabled}
                        onChange={(event) => setMcpServerEditor((state) => ({ ...state, enabled: event.target.checked }))}
                      />
                      启用 server
                    </label>
                    <div className="flex flex-wrap gap-2">
                      <button className="compact-button compact-button-strong" disabled={capabilityBusy} onClick={() => void handleSaveMcpServer()}>
                        保存 server
                      </button>
                      <button
                        className="compact-button compact-button-muted"
                        disabled={capabilityBusy}
                        onClick={() => setMcpServerEditor(EMPTY_MCP_SERVER_EDITOR)}
                      >
                        重置字段
                      </button>
                    </div>
                  </div>
                ) : null}

                {mcpServers.length ? (
                  <div className="mt-3 space-y-2">
                    {mcpServers.map((server) => (
                      <div key={server.id} className="rounded-xl border border-slate-200/80 bg-slate-50/60 px-3 py-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-slate-800 truncate">{server.name}</div>
                            <div className="mt-1 text-xs leading-5 text-slate-500 line-clamp-2">{server.description || "暂无描述"}</div>
                            <div className="mt-1 text-[11px] text-slate-500">
                              {server.tools.length} tools · {server.transport}
                              {server.transport === "stdio" && server.command ? ` · ${server.command}` : ""}
                            </div>
                          </div>
                          <div className="flex flex-wrap items-center justify-end gap-1.5 shrink-0">
                            <span className="meta-pill meta-pill-subtle">{server.id}</span>
                            {!server.enabled ? <span className="meta-pill meta-pill-subtle">已禁用</span> : null}
                          </div>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <button
                            className="compact-button compact-button-muted"
                            disabled={capabilityBusy}
                            onClick={() => {
                              setMcpServerEditor(toMcpServerEditorState(server));
                              setMcpServerEditorOpen(true);
                              setMcpImportOpen(false);
                              updateMcpInvokeState({
                                serverId: server.enabled ? server.id : "",
                                toolName: "",
                                argsJson: "{}",
                              });
                            }}
                          >
                            <Pencil className="h-4 w-4" />
                            编辑
                          </button>
                          <button className="compact-button compact-button-muted" disabled={capabilityBusy} onClick={() => void handleCopyMcpServerJson(server)}>
                            <ClipboardCopy className="h-4 w-4" />
                            复制 JSON
                          </button>
                          <button className="compact-button compact-button-muted" disabled={capabilityBusy} onClick={() => void handleDeleteMcpServer(server.id)}>
                            <Trash2 className="h-4 w-4" />
                            删除
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-3 rounded-xl border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">
                    当前工作区还没有 MCP server。点击 <span className="font-medium text-slate-700">新建</span> 手动创建，或 <span className="font-medium text-slate-700">粘贴 JSON 导入</span> 一键导入。
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                  <Play className="h-3.5 w-3.5" />
                  MCP 调试
                </div>
                <div className="space-y-2">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <select
                      className="soft-input"
                      value={mcpInvokeEditor.serverId}
                      onChange={(event) => {
                        setServerToolsError("");
                        updateMcpInvokeState({
                          serverId: event.target.value,
                          toolName: "",
                          argsJson: "{}",
                        });
                      }}
                    >
                      <option value="">选择 MCP server</option>
                      {invokableMcpServers.map((server) => (
                        <option key={server.id} value={server.id}>
                          {server.name}
                        </option>
                      ))}
                    </select>
                    <select
                      className="soft-input"
                      value={mcpInvokeEditor.toolName}
                      onChange={(event) => {
                        const nextTool = activeMcpTools.find((tool) => tool.name === event.target.value) ?? null;
                        updateMcpInvokeState({
                          toolName: event.target.value,
                          argsJson: buildInvokeArgsTemplate(nextTool),
                        });
                      }}
                      disabled={!activeMcpServer}
                    >
                      <option value="">选择 tool</option>
                      {activeMcpTools.map((tool) => (
                        <option key={tool.name} value={tool.name}>
                          {tool.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  {!invokableMcpServers.length ? (
                    <div className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">当前没有可调试的已启用 MCP server。</div>
                  ) : null}
                  {serverToolsError ? (
                    <div className="rounded-xl border border-amber-200 bg-amber-50/80 px-3 py-3 text-sm text-amber-700">{serverToolsError}</div>
                  ) : null}
                  {activeMcpTool ? (
                    <div className="rounded-xl border border-slate-200 bg-slate-50/70 px-3 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">input schema</div>
                        {serverToolsLoading ? <div className="text-[11px] text-slate-400">同步中…</div> : null}
                      </div>
                      <div className="mt-2 text-[11px] leading-5 text-slate-500">
                        action_name：{activeMcpTool.action_name ?? buildMcpActionName(activeMcpServer?.id ?? "", activeMcpTool.name)}
                      </div>
                      <div className="mt-1 text-[11px] leading-5 text-slate-500">
                        mode：{activeMcpTool.execution_mode} · builtin：{activeMcpTool.builtin_action}
                      </div>
                      <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-all text-[11px] leading-5 text-slate-600">{JSON.stringify(activeMcpTool.input_schema, null, 2)}</pre>
                    </div>
                  ) : activeMcpServer && !serverToolsLoading ? (
                    <div className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">请先明确选择一个可执行 tool。</div>
                  ) : null}
                  <div className="grid gap-2 sm:grid-cols-2">
                    <input
                      className="soft-input"
                      value={mcpInvokeEditor.currentNotePath}
                      onChange={(event) => updateMcpInvokeState({ currentNotePath: event.target.value })}
                      placeholder={currentNotePath || "current_note_path（可选）"}
                    />
                    <input
                      className="soft-input"
                      value={mcpInvokeEditor.defaultNoteDir}
                      onChange={(event) => updateMcpInvokeState({ defaultNoteDir: event.target.value })}
                      placeholder={preferences.default_note_dir || "Inbox"}
                    />
                  </div>
                  <input
                    className="soft-input"
                    value={mcpInvokeEditor.prompt}
                    onChange={(event) => updateMcpInvokeState({ prompt: event.target.value })}
                    placeholder="prompt（可选，用于 workspace_search 等工具）"
                  />
                  <textarea
                    className="soft-input min-h-[180px] font-mono text-[12px] leading-6"
                    value={mcpInvokeEditor.argsJson}
                    onChange={(event) => updateMcpInvokeState({ argsJson: event.target.value })}
                    placeholder="args JSON"
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      className="compact-button compact-button-muted"
                      disabled={capabilityBusy || !activeMcpTool}
                      onClick={() =>
                        updateMcpInvokeState({
                          argsJson: buildInvokeArgsTemplate(activeMcpTool),
                          currentNotePath: mcpInvokeEditor.currentNotePath || currentNotePath,
                          defaultNoteDir: mcpInvokeEditor.defaultNoteDir || preferences.default_note_dir || "Inbox",
                        })
                      }
                    >
                      载入参数模板
                    </button>
                    <button className="compact-button compact-button-strong" disabled={capabilityBusy || !activeMcpServer || !activeMcpTool} onClick={() => void handleInvokeMcpTool()}>
                      <Play className="h-4 w-4" />
                      执行工具
                    </button>
                  </div>
                  {invokeResult ? (
                    <div
                      className={`rounded-xl border px-3 py-3 text-sm ${
                        invokeResult.ok ? "border-emerald-200 bg-emerald-50/70 text-emerald-700" : "border-rose-200 bg-rose-50/80 text-rose-700"
                      }`}
                    >
                      <div className="font-medium">{invokeResult.ok ? "执行成功" : "执行失败"}</div>
                      {invokeResult.error ? <div className="mt-2 whitespace-pre-wrap break-all">{invokeResult.error}</div> : null}
                      {invokeResult.summary ? <div className="mt-2 whitespace-pre-wrap break-all">{invokeResult.summary}</div> : null}
                      {invokeResult.citations.length ? <div className="mt-2 text-xs opacity-80">引用：{invokeResult.citations.join("，")}</div> : null}
                      {Object.keys(invokeResult.payload).length ? (
                        <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-all rounded-lg border border-current/10 bg-white/40 px-3 py-2 text-[11px] leading-5">{JSON.stringify(invokeResult.payload, null, 2)}</pre>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">MCP Catalog</div>
                {mcpCatalog.length ? (
                  <div className="space-y-2">
                    {mcpCatalog.slice(0, 12).map((tool) => (
                      <div key={tool.name} className="rounded-xl border border-slate-200/80 bg-slate-50/60 px-3 py-2.5">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-slate-800">{tool.tool_name}</div>
                            <div className="mt-1 text-xs text-slate-500">{tool.server_id} · {tool.description || "暂无描述"}</div>
                          </div>
                          <span className="meta-pill meta-pill-subtle">{tool.execution_mode}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">当前没有可用 MCP catalog。</div>
                )}
              </div>
            </section>
          ) : null}

          {tab === "import" ? (
            <section className="space-y-3">
              <input
                className="soft-input"
                value={importDestinationDir}
                onChange={(event) => setImportDestinationDir(event.target.value)}
                placeholder="目标目录，例如 Inbox"
              />
              <input
                className="soft-input"
                value={importTags}
                onChange={(event) => setImportTags(event.target.value)}
                placeholder="标签，使用逗号分隔"
              />

              <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-3">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">本地文件</div>
                <input
                  className="soft-input"
                  value={importSourcePath}
                  onChange={(event) => setImportSourcePath(event.target.value)}
                  placeholder="D:\\source\\notes.pdf"
                />
                <button className="compact-button compact-button-strong mt-3 w-full justify-center" onClick={() => void importFileFromState()}>
                  <Upload className="h-4 w-4" />
                  导入文件
                </button>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-3">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">网页链接</div>
                <input
                  className="soft-input"
                  value={importUrlValue}
                  onChange={(event) => setImportUrlValue(event.target.value)}
                  placeholder="https://example.com/article"
                />
                <button className="compact-button compact-button-muted mt-3 w-full justify-center" onClick={() => void importUrlFromState()}>
                  <Globe className="h-4 w-4" />
                  导入链接
                </button>
              </div>

              <div className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">
                {importStatus || "导入后的内容会转换为工作区笔记。"}
              </div>
            </section>
          ) : null}

          {tab === "approvals" ? (
            <section className="space-y-3">
              {approvals.length ? (
                approvals.map((approval) => (
                  <div key={approval.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-slate-900">{approval.action}</div>
                        <div className="mt-1 text-xs text-slate-500">{approval.reason}</div>
                      </div>
                      <span className="meta-pill">
                        {approval.status === "pending"
                          ? "待处理"
                          : approval.status === "approved"
                            ? "已批准"
                            : approval.status === "rejected"
                              ? "已拒绝"
                              : approval.status}
                      </span>
                    </div>
                    <div className="mt-3 space-y-1 text-xs text-slate-500">
                      {approval.targets.map((target) => (
                        <div key={target} className="break-all">
                          {target}
                        </div>
                      ))}
                    </div>
                    {approval.status === "pending" ? (
                      <div className="mt-4 grid gap-2 sm:grid-cols-2">
                        <button className="compact-button compact-button-strong justify-center" onClick={() => void decideApproval(approval.id, "approve")}>
                          批准
                        </button>
                        <button className="compact-button compact-button-muted justify-center" onClick={() => void decideApproval(approval.id, "reject")}>
                          拒绝
                        </button>
                      </div>
                    ) : null}
                  </div>
                ))
              ) : (
                <div className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">当前没有审批请求。</div>
              )}
            </section>
          ) : null}

          {tab === "settings" ? (
            <section className="space-y-3">
              <div className="rounded-xl border border-slate-200 bg-slate-50/70 px-3 py-3 text-sm text-slate-600">
                {llmSettings.is_configured ? "模型已配置。" : "模型尚未配置。"}
              </div>
              <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-600">
                <div className="font-medium text-slate-900">DeepSeek 官方 API</div>
                <div className="mt-1 text-slate-500">
                  Base URL 填 `https://api.deepseek.com/v1`，模型可用 `deepseek-chat` 或 `deepseek-reasoner`。
                </div>
              </div>
              <input
                className="soft-input"
                value={llmForm.base_url}
                onChange={(event) => setLlmForm({ base_url: event.target.value })}
                placeholder="https://api.deepseek.com/v1"
              />
              <input
                className="soft-input"
                value={llmForm.model}
                onChange={(event) => setLlmForm({ model: event.target.value })}
                placeholder="deepseek-chat"
              />
              <input
                className="soft-input"
                type="password"
                value={llmForm.api_key}
                onChange={(event) => setLlmForm({ api_key: event.target.value })}
                placeholder={llmSettings.api_key_set ? "留空则保留当前密钥" : "API 密钥"}
              />
              <input
                className="soft-input"
                value={llmForm.timeout}
                onChange={(event) => setLlmForm({ timeout: event.target.value })}
                placeholder="超时时间（秒）"
              />
              <div className="grid gap-2 sm:grid-cols-2">
                <button className="compact-button compact-button-strong justify-center" disabled={llmSaving} onClick={() => void saveLLMSettingsFromForm()}>
                  保存
                </button>
                <button className="compact-button compact-button-muted justify-center" disabled={llmSaving} onClick={() => void testLLMSettings()}>
                  测试连接
                </button>
              </div>
              {llmTestResult ? (
                <div
                  className={`rounded-xl border px-3 py-3 text-sm ${
                    llmTestResult.ok
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : "border-rose-200 bg-rose-50 text-rose-700"
                  }`}
                >
                  {llmTestResult.ok ? (
                    <div className="space-y-1">
                      <div>连接成功：{llmTestResult.model ?? "当前模型"}</div>
                      <div className="text-xs opacity-80">
                        Provider：{llmTestResult.provider ?? "litellm"}
                        {typeof llmTestResult.latency_ms === "number" ? ` · 耗时 ${llmTestResult.latency_ms} ms` : ""}
                      </div>
                    </div>
                  ) : (
                    llmTestResult.error ?? "连接失败。"
                  )}
                </div>
              ) : null}
            </section>
          ) : null}
        </div>
      </aside>
    </>
  );
}

function DrawerTab({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: JSX.Element;
  label: string;
  onClick: () => void;
}) {
  return (
    <button className={`drawer-tab ${active ? "drawer-tab-active" : ""}`} onClick={onClick}>
      {icon}
      {label}
    </button>
  );
}

function toSkillEditorState(skill: SkillDefinition): SkillEditorState {
  return {
    skillId: skill.id,
    name: skill.name,
    description: skill.description,
    promptPrefix: skill.prompt_prefix,
    whenToUse: skill.when_to_use,
    toolSubset: skill.tool_subset.join(", "),
    examples: skill.examples.join(", "),
    keywords: skill.keywords.join(", "),
    enabled: skill.enabled,
  };
}

function toMcpServerEditorState(server: MCPServerDefinition): McpServerEditorState {
  return {
    serverId: server.id,
    name: server.name,
    description: server.description,
    transport: server.transport,
    command: server.command || "",
    argsText: (server.args || []).join(", "),
    envJson: Object.keys(server.env || {}).length ? JSON.stringify(server.env, null, 2) : "{}",
    workingDirectory: server.working_directory || "",
    enabled: server.enabled,
    toolsJson: JSON.stringify(server.tools, null, 2),
  };
}

function buildEmptyInvokeEditor(defaultNoteDir: string, currentNotePath: string): McpInvokeEditorState {
  return {
    serverId: "",
    toolName: "",
    argsJson: "{}",
    prompt: "",
    currentNotePath,
    defaultNoteDir,
  };
}

function buildEmptySkillResolve(currentNotePath: string, activeTag: string | null): SkillResolveState {
  return {
    ...EMPTY_SKILL_RESOLVE,
    currentNotePath,
    activeTags: activeTag ?? "",
  };
}

function normalizeIdentifier(explicitId: string, fallbackName: string): string {
  const source = (explicitId || fallbackName).trim().toLowerCase();
  if (!source) {
    return "";
  }
  return source
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "");
}

function parseDelimitedList(value: string): string[] {
  return value
    .split(/[\n,]/g)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseMcpTools(value: string): MCPToolDefinition[] {
  const trimmed = value.trim();
  if (!trimmed) {
    return [];
  }
  const parsed = JSON.parse(trimmed);
  if (!Array.isArray(parsed)) {
    throw new Error("tools JSON 必须是数组。\n");
  }
  return parsed.map((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      throw new Error("tools JSON 数组中的每一项都必须是对象。\n");
    }
    const candidate = item as Record<string, unknown>;
    return {
      name: String(candidate.name || "").trim(),
      description: String(candidate.description || "").trim(),
      input_schema: typeof candidate.input_schema === "object" && candidate.input_schema && !Array.isArray(candidate.input_schema)
        ? (candidate.input_schema as Record<string, unknown>)
        : {},
      execution_mode: String(candidate.execution_mode || "builtin"),
      builtin_action: String(candidate.builtin_action || "echo"),
      enabled: Boolean(candidate.enabled ?? true),
    };
  });
}

function parseEnvJson(value: string): Record<string, string> | undefined {
  const trimmed = value.trim();
  if (!trimmed || trimmed === "{}") {
    return undefined;
  }
  const parsed = JSON.parse(trimmed);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("env JSON 必须是对象。\n");
  }
  return Object.fromEntries(
    Object.entries(parsed as Record<string, unknown>).map(([key, val]) => [key, String(val ?? "")])
  );
}

function parseInvokeArgs(value: string): Record<string, unknown> {
  const trimmed = value.trim();
  if (!trimmed) {
    return {};
  }
  const parsed = JSON.parse(trimmed);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("args JSON 必须是对象。\n");
  }
  return parsed as Record<string, unknown>;
}

function buildInvokeArgsTemplate(tool: MCPToolDefinition | null): string {
  if (!tool) {
    return "{}";
  }
  const schema = tool.input_schema;
  if (!schema || typeof schema !== "object" || Array.isArray(schema)) {
    return "{}";
  }
  const properties =
    typeof schema.properties === "object" && schema.properties && !Array.isArray(schema.properties)
      ? (schema.properties as Record<string, unknown>)
      : null;
  const keys = properties ? Object.keys(properties) : Object.keys(schema);
  const template = Object.fromEntries(keys.map((key) => [key, ""]));
  return JSON.stringify(template, null, 2);
}

function buildMcpActionName(serverId: string, toolName: string): string {
  const normalizedServer = serverId.trim().replace(/-/g, "_");
  const normalizedTool = toolName.trim().replace(/-/g, "_");
  return `mcp__${normalizedServer}__${normalizedTool}`;
}
