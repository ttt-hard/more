import { create } from "zustand";

import {
  approveRequest,
  createNote,
  createWorkspace,
  getFileContent,
  getLLMSettings,
  getNote,
  getPreferences,
  getTree,
  importFile,
  importUrl,
  listMcpCatalog,
  listMcpServers,
  listApprovals,
  listSkills,
  listNotes,
  openWorkspace,
  rejectRequest,
  searchWorkspace,
  testLLMConnection,
  updateLLMSettings,
  updateNote,
  writeFile,
} from "../api";
import type { SelectionKind } from "../components/more/types";
import {
  basename,
  buildDraftNotePath,
  DEFAULT_PREFERENCES,
  EMPTY_LLM_SETTINGS,
  messageFromError,
  parseTags,
  readInitialWorkspacePath,
} from "../lib/more";
import { useUiStore } from "./uiStore";
import type {
  ApprovalRequest,
  LLMSettings,
  LLMTestResult,
  MCPServerDefinition,
  MCPToolCatalogItem,
  NoteMeta,
  Preference,
  SearchHit,
  SkillDefinition,
  TreeEntry,
  Workspace,
} from "../types";

type HydrationTargets = Partial<{
  tree: boolean;
  notes: boolean;
  approvals: boolean;
  preferences: boolean;
  llmSettings: boolean;
  capabilities: boolean;
}>;

type LLMFormState = {
  base_url: string;
  api_key: string;
  model: string;
  timeout: string;
};

export type OpenTab = {
  path: string;
  kind: SelectionKind;
  title: string;
};

function upsertTab(current: OpenTab[], tab: OpenTab): OpenTab[] {
  const index = current.findIndex((item) => item.path === tab.path);
  if (index === -1) {
    return [...current, tab];
  }
  const existing = current[index];
  if (existing.title === tab.title && existing.kind === tab.kind) {
    return current;
  }
  const next = current.slice();
  next[index] = { ...existing, ...tab };
  return next;
}

type PersistedSession = {
  workspaceRoot: string;
  selectedPath: string | null;
  selectedKind: SelectionKind;
  openTabs: OpenTab[];
};

const SESSION_STORAGE_KEY = "more.lastSession";

function loadPersistedSession(): PersistedSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PersistedSession>;
    if (!parsed || typeof parsed.workspaceRoot !== "string") return null;
    return {
      workspaceRoot: parsed.workspaceRoot,
      selectedPath: parsed.selectedPath ?? null,
      selectedKind: (parsed.selectedKind as SelectionKind) ?? null,
      openTabs: Array.isArray(parsed.openTabs) ? parsed.openTabs.filter(Boolean) : [],
    };
  } catch {
    return null;
  }
}

function persistSession(snapshot: PersistedSession): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    // Ignore quota / serialization failures.
  }
}

function clearPersistedSession(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(SESSION_STORAGE_KEY);
}

type WorkspaceStore = {
  workspacePath: string;
  workspace: Workspace | null;
  tree: TreeEntry | null;
  notes: NoteMeta[];
  selectedPath: string | null;
  selectedKind: SelectionKind;
  openTabs: OpenTab[];
  editorValue: string;
  searchQuery: string;
  searchHits: SearchHit[];
  preferences: Preference;
  approvals: ApprovalRequest[];
  skills: SkillDefinition[];
  mcpServers: MCPServerDefinition[];
  mcpCatalog: MCPToolCatalogItem[];
  importDestinationDir: string;
  importTags: string;
  importSourcePath: string;
  importUrlValue: string;
  importStatus: string;
  busyLabel: string;
  error: string;
  llmSettings: LLMSettings;
  llmForm: LLMFormState;
  llmSaving: boolean;
  llmTestResult: LLMTestResult | null;
  setWorkspacePath: (value: string) => void;
  setEditorValue: (value: string) => void;
  setSearchQuery: (value: string) => void;
  setSearchHits: (value: SearchHit[]) => void;
  setImportDestinationDir: (value: string) => void;
  setImportTags: (value: string) => void;
  setImportSourcePath: (value: string) => void;
  setImportUrlValue: (value: string) => void;
  setLlmForm: (patch: Partial<LLMFormState>) => void;
  clearError: () => void;
  setError: (value: string) => void;
  refreshTree: () => Promise<TreeEntry | null>;
  refreshNotes: () => Promise<NoteMeta[]>;
  refreshApprovals: () => Promise<ApprovalRequest[]>;
  refreshPreferences: () => Promise<Preference>;
  refreshLLMSettings: () => Promise<LLMSettings>;
  refreshCapabilities: () => Promise<void>;
  hydrateWorkspace: (nextWorkspace?: Workspace, targets?: HydrationTargets) => Promise<void>;
  activateWorkspace: (mode: "create" | "open") => Promise<Workspace | null>;
  selectPath: (path: string, kindHint?: SelectionKind) => Promise<void>;
  closeTab: (path: string) => void;
  showHome: () => void;
  saveSelectedDocument: () => Promise<boolean>;
  createDraftNote: () => Promise<void>;
  createNoteInFolder: (directory: string, options?: { tags?: string[] }) => Promise<void>;
  bootstrapSession: () => Promise<void>;
  runSearch: () => Promise<void>;
  importFileFromState: () => Promise<void>;
  importUrlFromState: () => Promise<void>;
  decideApproval: (id: string, decision: "approve" | "reject") => Promise<void>;
  saveLLMSettingsFromForm: () => Promise<void>;
  testLLMSettings: () => Promise<void>;
  upsertNote: (note: NoteMeta) => void;
};

export const useWorkspaceStore = create<WorkspaceStore>((set, get) => ({
  workspacePath: readInitialWorkspacePath(),
  workspace: null,
  tree: null,
  notes: [],
  selectedPath: null,
  selectedKind: null,
  openTabs: [],
  editorValue: "",
  searchQuery: "",
  searchHits: [],
  preferences: DEFAULT_PREFERENCES,
  approvals: [],
  skills: [],
  mcpServers: [],
  mcpCatalog: [],
  importDestinationDir: "Inbox",
  importTags: "",
  importSourcePath: "",
  importUrlValue: "",
  importStatus: "",
  busyLabel: "",
  error: "",
  llmSettings: EMPTY_LLM_SETTINGS,
  llmForm: {
    base_url: "",
    api_key: "",
    model: "",
    timeout: "60",
  },
  llmSaving: false,
  llmTestResult: null,
  setWorkspacePath: (value) => {
    const current = useWorkspaceStore.getState().workspacePath;
    if (current === value) {
      return;
    }
    if (typeof window !== "undefined") {
      window.localStorage.setItem("more.workspacePath", value);
    }
    set({ workspacePath: value });
  },
  setEditorValue: (value) => set((state) => (state.editorValue === value ? state : { editorValue: value })),
  setSearchQuery: (value) => set((state) => (state.searchQuery === value ? state : { searchQuery: value })),
  setSearchHits: (value) => set((state) => (state.searchHits === value ? state : { searchHits: value })),
  setImportDestinationDir: (value) =>
    set((state) => (state.importDestinationDir === value ? state : { importDestinationDir: value })),
  setImportTags: (value) => set((state) => (state.importTags === value ? state : { importTags: value })),
  setImportSourcePath: (value) =>
    set((state) => (state.importSourcePath === value ? state : { importSourcePath: value })),
  setImportUrlValue: (value) =>
    set((state) => (state.importUrlValue === value ? state : { importUrlValue: value })),
  setLlmForm: (patch) =>
    set((state) => {
      const next = { ...state.llmForm, ...patch };
      if (
        next.base_url === state.llmForm.base_url &&
        next.api_key === state.llmForm.api_key &&
        next.model === state.llmForm.model &&
        next.timeout === state.llmForm.timeout
      ) {
        return state;
      }
      return { llmForm: next };
    }),
  clearError: () => set((state) => (state.error ? { error: "" } : state)),
  setError: (value) => set((state) => (state.error === value ? state : { error: value })),
  refreshTree: async () => {
    const tree = await getTree();
    set({ tree });
    return tree;
  },
  refreshNotes: async () => {
    const notes = await listNotes();
    set({ notes });
    return notes;
  },
  refreshApprovals: async () => {
    const approvals = await listApprovals();
    set({ approvals });
    return approvals;
  },
  refreshPreferences: async () => {
    const preferences = await getPreferences();
    set((state) => ({
      preferences,
      importDestinationDir:
        state.importDestinationDir && state.importDestinationDir !== state.preferences.default_note_dir
          ? state.importDestinationDir
          : preferences.default_note_dir || "Inbox",
    }));
    return preferences;
  },
  refreshLLMSettings: async () => {
    try {
      const settings = await getLLMSettings();
      set((state) => ({
        llmSettings: settings,
        llmForm: {
          base_url: settings.base_url,
          api_key: "",
          model: settings.model,
          timeout: String(settings.timeout),
        },
        llmTestResult: state.llmTestResult,
      }));
      return settings;
    } catch {
      set({ llmSettings: EMPTY_LLM_SETTINGS });
      return EMPTY_LLM_SETTINGS;
    }
  },
  refreshCapabilities: async () => {
    const [skillsResult, mcpServersResult, mcpCatalogResult] = await Promise.allSettled([
      listSkills(true),
      listMcpServers(true),
      listMcpCatalog(),
    ]);
    set((state) => ({
      skills: skillsResult.status === "fulfilled" ? skillsResult.value : state.skills,
      mcpServers: mcpServersResult.status === "fulfilled" ? mcpServersResult.value : state.mcpServers,
      mcpCatalog: mcpCatalogResult.status === "fulfilled" ? mcpCatalogResult.value : state.mcpCatalog,
    }));
  },
  hydrateWorkspace: async (nextWorkspace, targets) => {
    const activeWorkspace = nextWorkspace ?? get().workspace;
    if (!activeWorkspace) {
      return;
    }

    const resolvedTargets = {
      tree: true,
      notes: true,
      approvals: true,
      preferences: true,
      llmSettings: true,
      capabilities: true,
      ...targets,
    };

    const tasks: Promise<unknown>[] = [];
    if (resolvedTargets.tree) {
      tasks.push(get().refreshTree());
    }
    if (resolvedTargets.notes) {
      tasks.push(get().refreshNotes());
    }
    if (resolvedTargets.approvals) {
      tasks.push(get().refreshApprovals());
    }
    if (resolvedTargets.preferences) {
      tasks.push(get().refreshPreferences());
    }
    if (resolvedTargets.llmSettings) {
      tasks.push(get().refreshLLMSettings());
    }
    if (resolvedTargets.capabilities) {
      tasks.push(get().refreshCapabilities());
    }
    await Promise.all(tasks);
  },
  activateWorkspace: async (mode) => {
    const { workspacePath, busyLabel } = get();
    if (busyLabel) {
      return null;
    }
    if (!workspacePath.trim()) {
      set({ error: "请输入工作区路径。" });
      return null;
    }

    set({
      busyLabel: mode === "create" ? "正在创建工作区..." : "正在打开工作区...",
      error: "",
    });

    try {
      const workspace =
        mode === "create"
          ? await createWorkspace(workspacePath.trim())
          : await openWorkspace(workspacePath.trim());

      set({
        workspace,
        selectedPath: null,
        selectedKind: null,
        openTabs: [],
        editorValue: "",
        searchHits: [],
        skills: [],
        mcpServers: [],
        mcpCatalog: [],
        importStatus: "",
      });
      clearPersistedSession();
      useUiStore.getState().setDocumentViewMode("source");
      await get().hydrateWorkspace(workspace);
      return workspace;
    } catch (error) {
      set({ error: messageFromError(error) });
      return null;
    } finally {
      set({ busyLabel: "" });
    }
  },
  selectPath: async (path, kindHint) => {
    set({ error: "" });
    try {
      const notes = get().notes;
      const shouldLoadAsNote =
        kindHint === "note" || notes.some((note) => note.relative_path === path) || path.toLowerCase().endsWith(".md");

      let resolvedPath = path;
      let resolvedTitle = basename(path);
      if (shouldLoadAsNote) {
        const note = await getNote(path);
        resolvedPath = note.meta.relative_path;
        resolvedTitle = note.meta.title || basename(note.meta.relative_path);
        set((state) => ({
          selectedPath: resolvedPath,
          selectedKind: "note",
          editorValue: note.content,
          openTabs: upsertTab(state.openTabs, {
            path: resolvedPath,
            kind: "note",
            title: resolvedTitle,
          }),
        }));
      } else {
        const content = await getFileContent(path);
        set((state) => ({
          selectedPath: path,
          selectedKind: "file",
          editorValue: content,
          openTabs: upsertTab(state.openTabs, {
            path,
            kind: "file",
            title: resolvedTitle,
          }),
        }));
      }

      useUiStore.getState().setDocumentViewMode("source");

      const snapshot = get();
      if (snapshot.workspace) {
        persistSession({
          workspaceRoot: snapshot.workspace.root_path,
          selectedPath: snapshot.selectedPath,
          selectedKind: snapshot.selectedKind,
          openTabs: snapshot.openTabs,
        });
      }
    } catch (error) {
      set({ error: messageFromError(error) });
    }
  },
  closeTab: (path) => {
    let pendingFallback: OpenTab | null = null;
    let shouldClearSelection = false;
    set((state) => {
      const index = state.openTabs.findIndex((tab) => tab.path === path);
      if (index === -1) {
        return state;
      }
      const nextTabs = [...state.openTabs.slice(0, index), ...state.openTabs.slice(index + 1)];
      if (state.selectedPath !== path) {
        return { openTabs: nextTabs };
      }
      if (nextTabs.length === 0) {
        shouldClearSelection = true;
        return {
          openTabs: nextTabs,
          selectedPath: null,
          selectedKind: null,
          editorValue: "",
        };
      }
      const fallbackIndex = Math.min(index, nextTabs.length - 1);
      pendingFallback = nextTabs[fallbackIndex];
      return {
        openTabs: nextTabs,
      };
    });
    useUiStore.getState().setDocumentViewMode("source");
    // Load the fallback lazily so its editorValue reflects server-side content.
    if (pendingFallback) {
      const fallback: OpenTab = pendingFallback;
      void get().selectPath(fallback.path, fallback.kind);
    } else {
      const snapshot = get();
      if (snapshot.workspace) {
        persistSession({
          workspaceRoot: snapshot.workspace.root_path,
          selectedPath: snapshot.selectedPath,
          selectedKind: snapshot.selectedKind,
          openTabs: snapshot.openTabs,
        });
      }
      // shouldClearSelection is kept for future diagnostics; persistence already wrote the cleared state.
      void shouldClearSelection;
    }
  },
  showHome: () => {
    set({
      selectedPath: null,
      selectedKind: null,
    });
    useUiStore.getState().setDocumentViewMode("source");
    const snapshot = get();
    if (snapshot.workspace) {
      persistSession({
        workspaceRoot: snapshot.workspace.root_path,
        selectedPath: null,
        selectedKind: null,
        openTabs: snapshot.openTabs,
      });
    }
  },
  saveSelectedDocument: async () => {
    const { selectedPath, selectedKind, editorValue, busyLabel } = get();
    if (busyLabel) {
      return false;
    }
    if (!selectedPath) {
      set({ error: "请先选择要保存的文件或笔记。" });
      return false;
    }

    set({ busyLabel: "正在保存...", error: "" });
    try {
      if (selectedKind === "note" || selectedPath.toLowerCase().endsWith(".md")) {
        await updateNote(selectedPath, editorValue);
        await get().refreshNotes();
      } else {
        await writeFile(selectedPath, editorValue);
      }
      await get().refreshTree();
      return true;
    } catch (error) {
      set({ error: messageFromError(error) });
      return false;
    } finally {
      set({ busyLabel: "" });
    }
  },
  createDraftNote: async () => {
    const directory = get().preferences.default_note_dir || "Inbox";
    await get().createNoteInFolder(directory);
  },
  bootstrapSession: async () => {
    if (typeof window === "undefined") return;
    const state = get();
    if (state.workspace || state.busyLabel) {
      // Already active or busy; nothing to restore.
      return;
    }
    const persisted = loadPersistedSession();
    const candidatePath = persisted?.workspaceRoot || state.workspacePath;
    if (!candidatePath) {
      return;
    }
    set({ busyLabel: "正在恢复工作区...", error: "" });
    try {
      const workspace = await openWorkspace(candidatePath);
      set({
        workspace,
        workspacePath: workspace.root_path,
        selectedPath: null,
        selectedKind: null,
        openTabs: [],
        editorValue: "",
        searchHits: [],
        skills: [],
        mcpServers: [],
        mcpCatalog: [],
        importStatus: "",
      });
      window.localStorage.setItem("more.workspacePath", workspace.root_path);
      useUiStore.getState().setDocumentViewMode("source");
      await get().hydrateWorkspace(workspace);

      // Restore the last tab strip + selection if the persisted snapshot belongs to the same workspace.
      if (persisted && persisted.workspaceRoot === workspace.root_path) {
        if (persisted.openTabs.length) {
          set({ openTabs: persisted.openTabs });
        }
        if (persisted.selectedPath) {
          await get().selectPath(persisted.selectedPath, persisted.selectedKind ?? null);
        }
      }
    } catch (error) {
      // Non-fatal: leave the user on the "no workspace" home view.
      set({ error: messageFromError(error) });
      clearPersistedSession();
    } finally {
      set({ busyLabel: "" });
    }
  },
  createNoteInFolder: async (directory: string, options) => {
    const { busyLabel } = get();
    if (busyLabel) {
      return;
    }
    const normalized = directory.replace(/[\\/]+$/, "") || "Inbox";
    const path = buildDraftNotePath(normalized);
    set({ busyLabel: `正在于 ${normalized} 中新建笔记...`, error: "" });
    try {
      const note = await createNote(path, "", options?.tags ? { tags: options.tags } : {});
      get().upsertNote(note.meta);
      await get().refreshTree();
      await get().selectPath(note.meta.relative_path, "note");
    } catch (error) {
      set({ error: messageFromError(error) });
    } finally {
      set({ busyLabel: "" });
    }
  },
  runSearch: async () => {
    const { searchQuery, busyLabel } = get();
    if (busyLabel) {
      return;
    }
    const query = searchQuery.trim();
    if (!query) {
      set({ searchHits: [] });
      return;
    }
    set({ busyLabel: "正在搜索...", error: "" });
    try {
      const hits = await searchWorkspace(query);
      set({ searchHits: hits });
    } catch (error) {
      set({ error: messageFromError(error) });
    } finally {
      set({ busyLabel: "" });
    }
  },
  importFileFromState: async () => {
    const { importSourcePath, importDestinationDir, importTags, busyLabel } = get();
    if (busyLabel) {
      return;
    }
    if (!importSourcePath.trim()) {
      set({ error: "请输入本地文件路径。" });
      return;
    }

    set({ busyLabel: "正在导入文件...", importStatus: "", error: "" });
    try {
      const result = await importFile(
        importSourcePath.trim(),
        importDestinationDir.trim() || "Inbox",
        parseTags(importTags)
      );
      set({
        importStatus: `已导入到 ${result.note.meta.relative_path}`,
        importSourcePath: "",
      });
      await get().refreshTree();
      await get().refreshNotes();
      await get().selectPath(result.note.meta.relative_path, "note");
      useUiStore.getState().setUtilityDrawerTab("import");
    } catch (error) {
      set({ error: messageFromError(error) });
    } finally {
      set({ busyLabel: "" });
    }
  },
  importUrlFromState: async () => {
    const { importUrlValue, importDestinationDir, importTags, busyLabel } = get();
    if (busyLabel) {
      return;
    }
    if (!importUrlValue.trim()) {
      set({ error: "请输入链接地址。" });
      return;
    }

    set({ busyLabel: "正在导入链接...", importStatus: "", error: "" });
    try {
      const result = await importUrl(
        importUrlValue.trim(),
        importDestinationDir.trim() || "Inbox",
        parseTags(importTags)
      );
      set({
        importStatus: `已导入到 ${result.note.meta.relative_path}`,
        importUrlValue: "",
      });
      await get().refreshTree();
      await get().refreshNotes();
      await get().selectPath(result.note.meta.relative_path, "note");
      useUiStore.getState().setUtilityDrawerTab("import");
    } catch (error) {
      set({ error: messageFromError(error) });
    } finally {
      set({ busyLabel: "" });
    }
  },
  decideApproval: async (id, decision) => {
    if (get().busyLabel) {
      return;
    }
    set({
      busyLabel: decision === "approve" ? "正在批准..." : "正在拒绝...",
      error: "",
    });
    try {
      if (decision === "approve") {
        await approveRequest(id);
      } else {
        await rejectRequest(id);
      }
      await Promise.all([get().refreshApprovals(), get().refreshTree(), get().refreshNotes()]);
    } catch (error) {
      set({ error: messageFromError(error) });
    } finally {
      set({ busyLabel: "" });
    }
  },
  saveLLMSettingsFromForm: async () => {
    const { llmForm, llmSaving } = get();
    if (llmSaving) {
      return;
    }
    set({ llmSaving: true, error: "", llmTestResult: null });
    try {
      const settings = await updateLLMSettings({
        base_url: llmForm.base_url.trim() || undefined,
        api_key: llmForm.api_key.trim() || undefined,
        model: llmForm.model.trim() || undefined,
        timeout: Number(llmForm.timeout) || undefined,
      });
      set((state) => ({
        llmSettings: settings,
        llmForm: { ...state.llmForm, api_key: "" },
      }));
    } catch (error) {
      set({ error: messageFromError(error) });
    } finally {
      set({ llmSaving: false });
    }
  },
  testLLMSettings: async () => {
    if (get().llmSaving) {
      return;
    }
    set({ llmSaving: true, error: "" });
    try {
      const result = await testLLMConnection();
      set({ llmTestResult: result });
    } catch (error) {
      set({ error: messageFromError(error) });
    } finally {
      set({ llmSaving: false });
    }
  },
  upsertNote: (note) =>
    set((state) => {
      const next = [...state.notes];
      const index = next.findIndex((item) => item.relative_path === note.relative_path);
      if (index >= 0) {
        next[index] = note;
      } else {
        next.unshift(note);
      }
      return { notes: next };
    }),
}));
