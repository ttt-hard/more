import {
  Check,
  ChevronLeft,
  ChevronRight,
  File,
  FileText,
  FolderOpen,
  FolderTree,
  Hash,
  Home,
  Plus,
  Upload,
  X,
} from "lucide-react";
import { memo, useCallback, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { useAgentConversation } from "@/hooks/useAgentConversation";
import { basename, getRecentNotes } from "@/lib/more";
import { useUiStore } from "@/stores/uiStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import type { TreeEntry } from "@/types";

export function Sidebar() {
  const {
    workspace,
    tree,
    notes,
    selectedPath,
    busyLabel,
    selectPath,
    createDraftNote,
    createNoteInFolder,
    showHome,
  } = useWorkspaceStore(
    useShallow((state) => ({
      workspace: state.workspace,
      tree: state.tree,
      notes: state.notes,
      selectedPath: state.selectedPath,
      busyLabel: state.busyLabel,
      selectPath: state.selectPath,
      createDraftNote: state.createDraftNote,
      createNoteInFolder: state.createNoteInFolder,
      showHome: state.showHome,
    }))
  );
  const { collapsed, activeTag, setActiveTag, toggleSidebarCollapsed, setUtilityDrawerOpen, setUtilityDrawerTab } = useUiStore(
    useShallow((state) => ({
      collapsed: state.sidebarCollapsed,
      activeTag: state.activeTag,
      setActiveTag: state.setActiveTag,
      toggleSidebarCollapsed: state.toggleSidebarCollapsed,
      setUtilityDrawerOpen: state.setUtilityDrawerOpen,
      setUtilityDrawerTab: state.setUtilityDrawerTab,
    }))
  );
  const { streamStatus } = useAgentConversation(
    useShallow((state) => ({
      streamStatus: state.streamStatus,
    }))
  );

  const tags = useMemo(
    () => Array.from(new Set(notes.flatMap((note) => note.tags))).sort((a, b) => a.localeCompare(b)),
    [notes]
  );
  const recentNotes = useMemo(() => getRecentNotes(notes, 10, activeTag), [activeTag, notes]);
  const controlsDisabled = Boolean(busyLabel) || streamStatus === "streaming";
  const handleSelectPath = useCallback(
    (path: string, kindHint?: "file" | "note" | null) => {
      void selectPath(path, kindHint);
    },
    [selectPath]
  );
  const handleCreateInFolder = useCallback(
    (directory: string) => {
      void createNoteInFolder(directory);
    },
    [createNoteInFolder]
  );

  if (collapsed) {
    return (
      <aside className="sidebar sidebar-collapsed">
        <div className="sidebar-rail-brand">M</div>
        <button className="sidebar-rail-button" onClick={toggleSidebarCollapsed} aria-label="展开侧边栏">
          <ChevronRight className="h-4 w-4" />
        </button>
        <button className="sidebar-rail-button" onClick={showHome} aria-label="返回首页">
          <Home className="h-4 w-4" />
        </button>
        <button
          className="sidebar-rail-button"
          onClick={() => void createDraftNote()}
          aria-label="新建笔记"
          disabled={controlsDisabled}
        >
          <Plus className="h-4 w-4" />
        </button>
        <button
          className="sidebar-rail-button"
          onClick={() => {
            setUtilityDrawerTab("import");
            setUtilityDrawerOpen(true);
          }}
          aria-label="导入资料"
          disabled={controlsDisabled}
        >
          <Upload className="h-4 w-4" />
        </button>
      </aside>
    );
  }

  return (
    <aside className="sidebar sidebar-compact">
      <div className="sidebar-header sidebar-header-tight">
        <div className="sidebar-profile">
          <div className="sidebar-avatar">{workspace?.name?.slice(0, 1).toUpperCase() ?? "M"}</div>
          <div className="min-w-0">
            <div className="sidebar-eyebrow">workspace</div>
            <div className="truncate text-[13px] font-semibold text-slate-950">{workspace?.name ?? "workspace"}</div>
            <div className="truncate text-[10px] text-slate-500">{workspace?.root_path ?? "未打开工作区"}</div>
          </div>
        </div>
        <button className="icon-button icon-button-sm" onClick={toggleSidebarCollapsed} aria-label="收起侧边栏">
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="sidebar-quick-nav">
        <button className="sidebar-nav-item" onClick={showHome}>
          <Home className="h-3.5 w-3.5" />
          <span>首页</span>
        </button>
        <button className="sidebar-nav-item" disabled={controlsDisabled} onClick={() => void createDraftNote()}>
          <File className="h-3.5 w-3.5" />
          <span>空白笔记</span>
        </button>
        <button
          className="sidebar-nav-item"
          disabled={controlsDisabled}
          onClick={() => {
            setUtilityDrawerTab("import");
            setUtilityDrawerOpen(true);
          }}
        >
          <Upload className="h-3.5 w-3.5" />
          <span>导入资料</span>
        </button>
      </div>

      <section className="sidebar-tree-panel">
        <div className="sidebar-section-label">
          <FolderTree className="h-3 w-3" />
          <span>工作区目录</span>
          <button
            type="button"
            className="sidebar-section-action"
            onClick={() => void createDraftNote()}
            disabled={controlsDisabled}
            aria-label="新建笔记到默认目录"
            title="新建笔记 (Ctrl+N)"
          >
            <Plus className="h-3 w-3" />
          </button>
        </div>
        <div className="sidebar-tree-scroll">
          {tree ? (
            <TreeView
              node={tree}
              selectedPath={selectedPath}
              onSelect={handleSelectPath}
              onCreateInFolder={handleCreateInFolder}
              disabled={controlsDisabled}
            />
          ) : (
            <div className="sidebar-empty-state">打开后可浏览目录。</div>
          )}
        </div>
      </section>

      <section className="sidebar-footer-panels">
        <div className="sidebar-meta-panel">
          <TagPanel
            activeTag={activeTag}
            setActiveTag={setActiveTag}
            notes={notes}
            tags={tags}
            disabled={controlsDisabled}
            onCreateNoteWithTags={(parsed) => {
              const directory = useWorkspaceStore.getState().preferences.default_note_dir || "Inbox";
              void createNoteInFolder(directory, { tags: parsed });
            }}
          />
        </div>

        <div className="sidebar-recent-panel">
          <div className="sidebar-section-label">
            <FileText className="h-3 w-3" />
            <span>最近笔记</span>
            {activeTag ? (
              <button
                type="button"
                className="sidebar-section-badge"
                onClick={() => setActiveTag(null)}
                title="点击取消筛选"
              >
                #{activeTag}
              </button>
            ) : null}
          </div>
          <div className="sidebar-notes-scroll">
            {recentNotes.length ? (
              recentNotes.map((note) => (
                <button
                  key={note.id}
                  className={`sidebar-note-row ${selectedPath === note.relative_path ? "sidebar-note-row-active" : ""}`}
                  onClick={() => void selectPath(note.relative_path, "note")}
                >
                  <div className="truncate text-[11.5px] font-medium leading-[18px] text-slate-900">{note.title}</div>
                  <div className="truncate text-[9.5px] leading-[14px] text-slate-500">{note.relative_path}</div>
                </button>
              ))
            ) : (
              <div className="sidebar-empty-state sidebar-empty-state-compact">
                {activeTag ? `#${activeTag} 下暂无笔记` : "暂无内容"}
              </div>
            )}
          </div>
        </div>
      </section>
    </aside>
  );
}

const TreeView = memo(function TreeView({
  node,
  selectedPath,
  onSelect,
  onCreateInFolder,
  disabled = false,
  depth = 0,
}: {
  node: TreeEntry;
  selectedPath: string | null;
  onSelect: (path: string, kindHint?: "file" | "note" | null) => void;
  onCreateInFolder?: (directory: string) => void;
  disabled?: boolean;
  depth?: number;
}) {
  const children = node.children ?? [];

  return (
    <div className={depth === 0 ? "space-y-[1px]" : "ml-2 mt-[1px] space-y-[1px] border-l border-slate-200/60 pl-1.5"}>
      {children.map((child) => {
        const isActive = child.path === selectedPath;
        const isNote = child.path.toLowerCase().endsWith(".md");
        const isDirectory = child.kind === "directory";

        return (
          <div key={child.path}>
            <div className={`tree-item-row ${isActive ? "tree-item-row-active" : ""}`}>
              <button
                className={`tree-item flex flex-1 items-center gap-1.5 rounded-[10px] px-1.5 py-[3px] text-left text-[11.5px] leading-[18px] ${
                  isActive ? "tree-item-active" : "text-slate-600"
                }`}
                onClick={() => {
                  if (!isDirectory) {
                    onSelect(child.path, isNote ? "note" : "file");
                  }
                }}
              >
                {isDirectory ? (
                  <FolderOpen className="h-3 w-3 shrink-0 text-slate-400" />
                ) : isNote ? (
                  <FileText className="h-3 w-3 shrink-0 text-slate-400" />
                ) : (
                  <File className="h-3 w-3 shrink-0 text-slate-400" />
                )}
                <span className="truncate">{basename(child.path)}</span>
              </button>
              {isDirectory && onCreateInFolder ? (
                <button
                  type="button"
                  className="tree-item-action"
                  onClick={(event) => {
                    event.stopPropagation();
                    onCreateInFolder(child.path);
                  }}
                  disabled={disabled}
                  aria-label={`在 ${basename(child.path)} 内新建笔记`}
                  title={`在 ${basename(child.path)} 内新建笔记`}
                >
                  <Plus className="h-3 w-3" />
                </button>
              ) : null}
            </div>
            {isDirectory && child.children && child.children.length ? (
              <TreeView
                node={child}
                selectedPath={selectedPath}
                onSelect={onSelect}
                onCreateInFolder={onCreateInFolder}
                disabled={disabled}
                depth={depth + 1}
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
});

type NoteLike = { tags: string[] };

const TagPanel = memo(function TagPanel({
  activeTag,
  setActiveTag,
  notes,
  tags,
  disabled,
  onCreateNoteWithTags,
}: {
  activeTag: string | null;
  setActiveTag: (value: string | null) => void;
  notes: NoteLike[];
  tags: string[];
  disabled: boolean;
  onCreateNoteWithTags: (tags: string[]) => void;
}) {
  const [composerOpen, setComposerOpen] = useState(false);
  const [composerValue, setComposerValue] = useState("");

  const openComposer = useCallback(() => {
    setComposerValue("");
    setComposerOpen(true);
  }, []);

  const cancelComposer = useCallback(() => {
    setComposerOpen(false);
    setComposerValue("");
  }, []);

  const submitComposer = useCallback(() => {
    const parsed = composerValue
      .split(/[,，\s]+/)
      .map((item) => item.trim().replace(/^#/, ""))
      .filter(Boolean);
    if (!parsed.length) {
      cancelComposer();
      return;
    }
    onCreateNoteWithTags(parsed);
    setComposerOpen(false);
    setComposerValue("");
  }, [composerValue, onCreateNoteWithTags, cancelComposer]);

  return (
    <>
      <div className="sidebar-section-label">
        <Hash className="h-3 w-3" />
        <span>标签</span>
        <button
          type="button"
          className="sidebar-section-action"
          onClick={composerOpen ? cancelComposer : openComposer}
          disabled={disabled}
          aria-label={composerOpen ? "取消添加标签" : "添加标签到新笔记"}
          title={composerOpen ? "取消" : "添加标签并创建新笔记"}
        >
          {composerOpen ? <X className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
        </button>
      </div>

      {composerOpen ? (
        <form
          className="tag-composer"
          onSubmit={(event) => {
            event.preventDefault();
            submitComposer();
          }}
        >
          <input
            autoFocus
            value={composerValue}
            onChange={(event) => setComposerValue(event.target.value)}
            placeholder="输入标签，回车确认"
            className="tag-composer-input"
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                cancelComposer();
              }
            }}
          />
          <button
            type="submit"
            className="tag-composer-confirm"
            disabled={disabled || !composerValue.trim()}
            aria-label="创建带此标签的笔记"
          >
            <Check className="h-3 w-3" />
          </button>
        </form>
      ) : null}

      <div className="flex flex-wrap gap-1">
        <button
          className={`tag-chip ${activeTag === null ? "tag-chip-active" : ""}`}
          onClick={() => setActiveTag(null)}
        >
          全部 · {notes.length}
        </button>
        {tags.length ? (
          tags.map((tag) => {
            const count = notes.filter((note) => note.tags.includes(tag)).length;
            return (
              <button
                key={tag}
                className={`tag-chip ${activeTag === tag ? "tag-chip-active" : ""}`}
                onClick={() => setActiveTag(activeTag === tag ? null : tag)}
                title={activeTag === tag ? "点击取消筛选" : `按 #${tag} 筛选`}
              >
                #{tag}
                <span className="tag-chip-count">{count}</span>
              </button>
            );
          })
        ) : (
          <span className="text-[11px] text-slate-400">暂无标签 · 点击「+」建一条带标签的笔记</span>
        )}
      </div>
    </>
  );
});
