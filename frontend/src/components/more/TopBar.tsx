import {
  ChevronRight,
  CornerDownLeft,
  File,
  FileText,
  FolderOpen,
  Hash,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { useAgentConversation } from "@/hooks/useAgentConversation";
import { basename, countPendingApprovals } from "@/lib/more";
import { useUiStore } from "@/stores/uiStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";

type SearchSuggestion = {
  kind: "note" | "tag";
  key: string;
  label: string;
  subtitle: string;
  path?: string;
  tag?: string;
};

export function TopBar() {
  const {
    workspace,
    workspacePath,
    selectedPath,
    searchQuery,
    busyLabel,
    pendingApprovalsCount,
    openTabs,
    notes,
    selectPath,
    closeTab,
    setWorkspacePath,
    setSearchQuery,
    runSearch,
    activateWorkspace,
  } = useWorkspaceStore(
    useShallow((state) => ({
      workspace: state.workspace,
      workspacePath: state.workspacePath,
      selectedPath: state.selectedPath,
      searchQuery: state.searchQuery,
      busyLabel: state.busyLabel,
      pendingApprovalsCount: countPendingApprovals(state.approvals),
      openTabs: state.openTabs,
      notes: state.notes,
      selectPath: state.selectPath,
      closeTab: state.closeTab,
      setWorkspacePath: state.setWorkspacePath,
      setSearchQuery: state.setSearchQuery,
      runSearch: state.runSearch,
      activateWorkspace: state.activateWorkspace,
    }))
  );
  const setActiveTag = useUiStore((state) => state.setActiveTag);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const searchWrapRef = useRef<HTMLDivElement | null>(null);
  const { isAgentDockCollapsed, toggleAgentDockCollapsed, setUtilityDrawerOpen } = useUiStore(
    useShallow((state) => ({
      isAgentDockCollapsed: state.isAgentDockCollapsed,
      toggleAgentDockCollapsed: state.toggleAgentDockCollapsed,
      setUtilityDrawerOpen: state.setUtilityDrawerOpen,
    }))
  );
  const { resetForWorkspace } = useAgentConversation(
    useShallow((state) => ({
      resetForWorkspace: state.resetForWorkspace,
    }))
  );

  const controlsDisabled = Boolean(busyLabel);

  async function handleActivate(mode: "create" | "open"): Promise<void> {
    const nextWorkspace = await activateWorkspace(mode);
    if (nextWorkspace) {
      await resetForWorkspace(nextWorkspace);
    }
  }

  const trimmedQuery = searchQuery.trim();
  const suggestions = useMemo<SearchSuggestion[]>(() => {
    if (!trimmedQuery) {
      return [];
    }
    const needle = trimmedQuery.toLowerCase();
    const tagCandidates = needle.startsWith("#") ? needle.slice(1) : needle;
    const seenTags = new Set<string>();
    const tagHits: SearchSuggestion[] = [];
    for (const note of notes) {
      for (const tag of note.tags) {
        if (seenTags.has(tag)) continue;
        if (tagCandidates && !tag.toLowerCase().includes(tagCandidates)) continue;
        seenTags.add(tag);
        tagHits.push({
          kind: "tag",
          key: `tag:${tag}`,
          label: `#${tag}`,
          subtitle: `${notes.filter((item) => item.tags.includes(tag)).length} 条笔记`,
          tag,
        });
        if (tagHits.length >= 3) break;
      }
      if (tagHits.length >= 3) break;
    }

    const noteHits: SearchSuggestion[] = [];
    for (const note of notes) {
      const titleMatch = note.title.toLowerCase().includes(needle);
      const pathMatch = note.relative_path.toLowerCase().includes(needle);
      if (!titleMatch && !pathMatch) continue;
      noteHits.push({
        kind: "note",
        key: `note:${note.relative_path}`,
        label: note.title || basename(note.relative_path),
        subtitle: note.relative_path,
        path: note.relative_path,
      });
      if (noteHits.length >= 7) break;
    }

    return [...tagHits, ...noteHits];
  }, [notes, trimmedQuery]);

  useEffect(() => {
    if (!suggestions.length) {
      setActiveIndex(0);
      return;
    }
    setActiveIndex((prev) => (prev >= suggestions.length ? 0 : prev));
  }, [suggestions]);

  useEffect(() => {
    if (!suggestOpen) return;
    const handlePointer = (event: MouseEvent) => {
      const el = searchWrapRef.current;
      if (el && event.target instanceof Node && !el.contains(event.target)) {
        setSuggestOpen(false);
      }
    };
    window.addEventListener("mousedown", handlePointer);
    return () => window.removeEventListener("mousedown", handlePointer);
  }, [suggestOpen]);

  function applySuggestion(suggestion: SearchSuggestion): void {
    setSuggestOpen(false);
    if (suggestion.kind === "note" && suggestion.path) {
      void selectPath(suggestion.path, suggestion.path.toLowerCase().endsWith(".md") ? "note" : "file");
      setSearchQuery("");
      return;
    }
    if (suggestion.kind === "tag" && suggestion.tag) {
      setActiveTag(suggestion.tag);
      setSearchQuery("");
    }
  }

  return (
    <header className="topbar-shell topbar-shell-vscode">
      <div className="topbar-row topbar-row-main">
        <div className="topbar-leading">
          <div className="topbar-brand">more</div>
          <div className="workspace-chip" title={workspace?.root_path ?? workspacePath}>
            <span className="workspace-chip-label">工作区</span>
            <input
              className="workspace-chip-input"
              value={workspacePath}
              onChange={(event) => setWorkspacePath(event.target.value)}
              aria-label="工作区路径"
              placeholder="输入或打开一个工作区路径"
            />
          </div>
        </div>

        <div className="topbar-search-wrap" ref={searchWrapRef}>
          <div className="topbar-search-shell">
            <Search className="h-4 w-4 text-slate-400" />
            <input
              id="more-search-input"
              className="topbar-input"
              value={searchQuery}
              onChange={(event) => {
                setSearchQuery(event.target.value);
                setSuggestOpen(true);
              }}
              onFocus={() => setSuggestOpen(true)}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown") {
                  event.preventDefault();
                  setSuggestOpen(true);
                  setActiveIndex((prev) => (suggestions.length ? (prev + 1) % suggestions.length : 0));
                  return;
                }
                if (event.key === "ArrowUp") {
                  event.preventDefault();
                  setActiveIndex((prev) =>
                    suggestions.length ? (prev - 1 + suggestions.length) % suggestions.length : 0
                  );
                  return;
                }
                if (event.key === "Escape") {
                  setSuggestOpen(false);
                  return;
                }
                if (event.key === "Enter") {
                  event.preventDefault();
                  if (suggestOpen && suggestions[activeIndex]) {
                    applySuggestion(suggestions[activeIndex]);
                    return;
                  }
                  void runSearch();
                }
              }}
              placeholder="搜索文档、标签或上下文..."
              autoComplete="off"
            />
            {searchQuery ? (
              <button
                type="button"
                className="topbar-search-clear"
                onClick={() => {
                  setSearchQuery("");
                  setSuggestOpen(false);
                }}
                aria-label="清空搜索"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </div>
          {suggestOpen && suggestions.length ? (
            <div className="topbar-search-suggest" role="listbox" aria-label="搜索联想">
              {suggestions.map((suggestion, index) => (
                <button
                  key={suggestion.key}
                  type="button"
                  role="option"
                  aria-selected={index === activeIndex}
                  className={`topbar-search-suggest-item ${index === activeIndex ? "topbar-search-suggest-item-active" : ""}`}
                  onMouseEnter={() => setActiveIndex(index)}
                  onMouseDown={(event) => {
                    // Use mousedown so it fires before input blur closes the panel.
                    event.preventDefault();
                    applySuggestion(suggestion);
                  }}
                >
                  {suggestion.kind === "tag" ? (
                    <Hash className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                  ) : (
                    <FileText className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="topbar-search-suggest-label">{suggestion.label}</div>
                    <div className="topbar-search-suggest-sub">{suggestion.subtitle}</div>
                  </div>
                  {index === activeIndex ? (
                    <span className="topbar-search-suggest-cue">
                      <CornerDownLeft className="h-3 w-3" />
                    </span>
                  ) : (
                    <ChevronRight className="h-3 w-3 text-slate-300" />
                  )}
                </button>
              ))}
              <div className="topbar-search-suggest-footer">
                <span>↑↓ 选择 · 回车打开 · Esc 关闭</span>
                <button
                  type="button"
                  className="topbar-search-suggest-run"
                  onMouseDown={(event) => {
                    event.preventDefault();
                    setSuggestOpen(false);
                    void runSearch();
                  }}
                >
                  搜索全部
                </button>
              </div>
            </div>
          ) : null}
        </div>

        <div className="topbar-actions">

          <button
            className="compact-button compact-button-muted"
            disabled={controlsDisabled}
            onClick={() => void handleActivate("open")}
          >
            <FolderOpen className="h-4 w-4" />
            打开
          </button>

          <button
            className="compact-button compact-button-strong topbar-primary-action"
            disabled={controlsDisabled}
            onClick={() => void handleActivate("create")}
          >
            <Plus className="h-4 w-4" />
            创建
          </button>

          <button className="icon-button" onClick={toggleAgentDockCollapsed} aria-label="切换助手栏">
            {isAgentDockCollapsed ? <PanelRightOpen className="h-4 w-4" /> : <PanelRightClose className="h-4 w-4" />}
          </button>

          <button className="icon-button relative" onClick={() => setUtilityDrawerOpen(true)} aria-label="打开工具抽屉">
            <SlidersHorizontal className="h-4 w-4" />
            {pendingApprovalsCount ? <span className="topbar-badge">{pendingApprovalsCount}</span> : null}
          </button>
        </div>
      </div>

      {openTabs.length ? (
        <div className="topbar-row topbar-row-tabs">
          <div className="topbar-tab-strip" role="tablist" aria-label="已打开的文件">
            {openTabs.map((tab) => {
              const isActive = tab.path === selectedPath;
              const isNote = tab.kind === "note" || tab.path.toLowerCase().endsWith(".md");
              return (
                <div
                  key={tab.path}
                  role="tab"
                  aria-selected={isActive}
                  className={`topbar-file-tab ${isActive ? "topbar-file-tab-active" : ""}`}
                  title={tab.path}
                  onClick={() => {
                    if (!isActive) {
                      void selectPath(tab.path, tab.kind);
                    }
                  }}
                  onAuxClick={(event) => {
                    // Middle-click closes the tab, matching VSCode behavior.
                    if (event.button === 1) {
                      event.preventDefault();
                      closeTab(tab.path);
                    }
                  }}
                >
                  {isNote ? (
                    <FileText className="topbar-file-tab-icon" />
                  ) : (
                    <File className="topbar-file-tab-icon" />
                  )}
                  <span className="truncate">{tab.title}</span>
                  <button
                    type="button"
                    className="topbar-file-tab-close"
                    onClick={(event) => {
                      event.stopPropagation();
                      closeTab(tab.path);
                    }}
                    aria-label={`关闭 ${tab.title}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </header>
  );
}
