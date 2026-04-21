import { FileText, Plus, Sparkles } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { MarkdownView } from "@/components/MarkdownView";
import { LiveMarkdownEditor } from "@/components/more/LiveMarkdownEditor";
import { useAgentConversation } from "@/hooks/useAgentConversation";
import { GLOBAL_DRAFT_KEY, basename, getRecentNotes, getRelatedSearchHits, getSelectedNote } from "@/lib/more";
import { useUiStore } from "@/stores/uiStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import type { SearchHit } from "@/types";

const INVALID_DRAFT_VALUES = new Set([
  "",
  "No answer was returned.",
  "抱歉，当前没有生成可用回答。请换一个更具体的问题再试。",
]);

const AUTOSAVE_DELAY_MS = 900;

function isMarkdownPath(path: string | null | undefined): boolean {
  if (!path) return false;
  return path.toLowerCase().endsWith(".md");
}

export function DocumentHub() {
  const selectedPath = useWorkspaceStore((state) => state.selectedPath);

  return <main className="document-shell">{selectedPath ? <SelectedDocumentCanvas /> : <HomeWorkspace />}</main>;
}

function SelectedDocumentCanvas() {
  const {
    selectedPath,
    selectedKind,
    notes,
    editorValue,
    busyLabel,
    setEditorValue,
  } = useWorkspaceStore(
    useShallow((state) => ({
      selectedPath: state.selectedPath,
      selectedKind: state.selectedKind,
      notes: state.notes,
      editorValue: state.editorValue,
      busyLabel: state.busyLabel,
      setEditorValue: state.setEditorValue,
    }))
  );
  const { documentViewMode, setDocumentViewMode, draftMap, setDraftContent } = useUiStore(
    useShallow((state) => ({
      documentViewMode: state.documentViewMode,
      setDocumentViewMode: state.setDocumentViewMode,
      draftMap: state.draftMap,
      setDraftContent: state.setDraftContent,
    }))
  );
  const { generateDraft, streamStatus } = useAgentConversation(
    useShallow((state) => ({
      generateDraft: state.generateDraft,
      streamStatus: state.streamStatus,
    }))
  );
  // Autosave runs entirely outside of React via a zustand subscription
  // (see useAutosaveSubscription below). This component only reads the
  // resulting label so it can show "保存中…" / "已自动保存" in the header.
  const autosaveLabel = useAutosaveLabel();

  const selectedNote = useMemo(() => getSelectedNote(notes, selectedPath), [notes, selectedPath]);
  const draftKey = selectedPath ?? GLOBAL_DRAFT_KEY;
  const rawDraftContent = draftMap[draftKey] ?? "";
  const draftContent = INVALID_DRAFT_VALUES.has(rawDraftContent.trim()) ? "" : rawDraftContent;
  const isBusy = streamStatus === "streaming" || Boolean(busyLabel);
  const isMarkdown = isMarkdownPath(selectedPath) || selectedKind === "note";
  const docTitle = selectedNote?.title || (selectedPath ? basename(selectedPath) : "");
  const docSubtitle = selectedPath ?? "";

  const handleGenerateDraft = useCallback(() => {
    void generateDraft();
  }, [generateDraft]);

  return (
    <>
      <div className="document-canvas-head">
        <div className="document-canvas-head-copy">
          <div className="document-canvas-head-title" title={docTitle}>{docTitle || "未命名"}</div>
          <div className="document-canvas-head-meta">
            <span className="document-canvas-head-path" title={docSubtitle}>
              {docSubtitle}
            </span>
            {autosaveLabel ? <span className="document-canvas-head-status">{autosaveLabel}</span> : null}
          </div>
        </div>
        <div className="document-canvas-head-actions">
          {draftContent ? (
            <button
              className={`compact-button compact-button-muted ${documentViewMode === "draft" ? "compact-button-active" : ""}`}
              onClick={() => setDocumentViewMode(documentViewMode === "draft" ? "source" : "draft")}
            >
              <Sparkles className="h-4 w-4" />
              {documentViewMode === "draft" ? "查看原文" : "查看 AI 草稿"}
            </button>
          ) : null}
          <button className="compact-button compact-button-muted" disabled={isBusy} onClick={handleGenerateDraft}>
            <Sparkles className="h-4 w-4" />
            生成草稿
          </button>
        </div>
      </div>

      <div className="document-scroll-region document-scroll-region-canvas">
        {documentViewMode === "draft" ? (
          <DraftCanvas
            content={draftContent}
            onChange={(value) => setDraftContent(draftKey, value)}
            onClose={() => setDocumentViewMode("source")}
          />
        ) : isMarkdown ? (
          <LiveMarkdownEditor
            value={editorValue}
            onChange={setEditorValue}
            placeholder="开始输入 Markdown…"
          />
        ) : (
          <section className="plain-editor">
            <textarea
              className="plain-editor-textarea"
              value={editorValue}
              onChange={(event) => setEditorValue(event.target.value)}
              placeholder="开始输入内容…"
              spellCheck={false}
            />
          </section>
        )}
      </div>
    </>
  );
}

// --- autosave: driven by zustand subscribe rather than useEffect ---
// The subscription is attached exactly once, the first time any mounted
// SelectedDocumentCanvas asks for its label. No effect inside a component
// can possibly trigger a render feedback loop, because the subscription
// lives outside of React's render cycle.
type AutosaveState = "idle" | "dirty" | "saving" | "saved";

let autosaveInstalled = false;
let autosaveLabelRef: AutosaveState = "idle";
const autosaveLabelListeners = new Set<(state: AutosaveState) => void>();

const AUTOSAVE_DEBOUNCE_MS = 900;

function setAutosaveLabel(next: AutosaveState): void {
  if (autosaveLabelRef === next) return;
  autosaveLabelRef = next;
  for (const listener of autosaveLabelListeners) {
    listener(next);
  }
}

function installAutosaveSubscription(): void {
  if (autosaveInstalled) return;
  autosaveInstalled = true;

  let baselinePath: string | null = null;
  let baselineValue = "";
  let timerId: number | null = null;

  const fireSave = async () => {
    timerId = null;
    const current = useWorkspaceStore.getState();
    if (!current.selectedPath || current.selectedPath !== baselinePath) return;
    if (current.busyLabel) return;
    if (current.editorValue === baselineValue) return;
    setAutosaveLabel("saving");
    const snapshotPath = baselinePath;
    const snapshotValue = current.editorValue;
    const ok = await useWorkspaceStore.getState().saveSelectedDocument();
    const after = useWorkspaceStore.getState();
    if (!ok || after.selectedPath !== snapshotPath) {
      setAutosaveLabel("dirty");
      return;
    }
    baselineValue = snapshotValue;
    setAutosaveLabel("saved");
  };

  const scheduleSave = () => {
    if (timerId !== null) {
      window.clearTimeout(timerId);
    }
    timerId = window.setTimeout(() => {
      void fireSave();
    }, AUTOSAVE_DEBOUNCE_MS);
  };

  // Seed baseline on first observation.
  const initial = useWorkspaceStore.getState();
  baselinePath = initial.selectedPath;
  baselineValue = initial.editorValue;
  setAutosaveLabel(baselinePath ? "saved" : "idle");

  useWorkspaceStore.subscribe((state, previous) => {
    if (state.selectedPath !== previous.selectedPath) {
      // Switched files: reset baseline, cancel any pending save.
      if (timerId !== null) {
        window.clearTimeout(timerId);
        timerId = null;
      }
      baselinePath = state.selectedPath;
      baselineValue = state.editorValue;
      setAutosaveLabel(state.selectedPath ? "saved" : "idle");
      return;
    }
    if (state.editorValue !== previous.editorValue) {
      if (!state.selectedPath) return;
      if (state.editorValue === baselineValue) {
        setAutosaveLabel("saved");
        if (timerId !== null) {
          window.clearTimeout(timerId);
          timerId = null;
        }
        return;
      }
      setAutosaveLabel("dirty");
      scheduleSave();
    }
  });
}

function useAutosaveLabel(): string {
  installAutosaveSubscription();
  const [state, setState] = useState<AutosaveState>(autosaveLabelRef);
  useEffect(() => {
    autosaveLabelListeners.add(setState);
    // Pull latest in case it changed between install and subscribe.
    setState(autosaveLabelRef);
    return () => {
      autosaveLabelListeners.delete(setState);
    };
  }, []);
  switch (state) {
    case "saving":
      return "保存中…";
    case "dirty":
      return "待保存";
    case "saved":
      return "已自动保存";
    default:
      return "";
  }
}

function DraftCanvas({
  content,
  onChange,
  onClose,
}: {
  content: string;
  onChange: (value: string) => void;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<"edit" | "preview">("preview");
  return (
    <section className="markdown-editor markdown-editor-draft">
      <div className="markdown-toolbar">
        <div className="markdown-toolbar-actions">
          <span className="markdown-toolbar-chip">AI 草稿</span>
        </div>
        <div className="markdown-view-switch">
          <button
            type="button"
            className={`markdown-view-switch-button ${mode === "edit" ? "markdown-view-switch-button-active" : ""}`}
            onClick={() => setMode("edit")}
          >
            编辑
          </button>
          <button
            type="button"
            className={`markdown-view-switch-button ${mode === "preview" ? "markdown-view-switch-button-active" : ""}`}
            onClick={() => setMode("preview")}
          >
            预览
          </button>
          <button className="markdown-view-switch-button" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
      <div className="markdown-editor-body markdown-editor-body-draft">
        {mode === "edit" ? (
          <textarea
            className="markdown-editor-textarea"
            value={content}
            onChange={(event) => onChange(event.target.value)}
            placeholder="草稿会显示在这里…"
            spellCheck={false}
          />
        ) : (
          <div className="markdown-editor-preview markdown-editor-preview-draft">
            <MarkdownView
              source={content}
              emptyFallback={<div className="markdown-empty">还没有 AI 草稿。点击“生成草稿”让助手创建。</div>}
            />
          </div>
        )}
      </div>
    </section>
  );
}

function HomeWorkspace() {
  const { workspaceLoaded, notes, searchQuery, searchHits, busyLabel, selectPath, createDraftNote } = useWorkspaceStore(
    useShallow((state) => ({
      workspaceLoaded: Boolean(state.workspace),
      notes: state.notes,
      searchQuery: state.searchQuery,
      searchHits: state.searchHits,
      busyLabel: state.busyLabel,
      selectPath: state.selectPath,
      createDraftNote: state.createDraftNote,
    }))
  );
  const { generateDraft, streamStatus } = useAgentConversation(
    useShallow((state) => ({
      generateDraft: state.generateDraft,
      streamStatus: state.streamStatus,
    }))
  );

  const selectedNote = useMemo(() => getSelectedNote(notes, null), [notes]);
  const recentNotes = useMemo(() => getRecentNotes(notes, 8), [notes]);
  const relatedHits = useMemo(
    () => getRelatedSearchHits({ notes, searchHits, selectedNote, recentNotes, limit: 6 }),
    [notes, recentNotes, searchHits, selectedNote]
  );

  const trimmedSearchQuery = searchQuery.trim();
  const homeStatusLabel = workspaceLoaded ? "待打开" : "未连接";
  const isBusy = streamStatus === "streaming" || Boolean(busyLabel);

  return (
    <>
      <div className="document-header document-header-home">
        <div className="min-w-0 flex-1">
          <div className="document-kicker">工作区</div>
          <h1 className="document-title">{workspaceLoaded ? "继续工作" : "打开工作区"}</h1>
        </div>
        <div className="home-header-meta">{homeStatusLabel}</div>
      </div>

      <div className="document-scroll-region document-scroll-region-home">
        <section className="home-workspace-layout">
          <div className="home-main-surface">
            <div className="home-main-head">
              <div className="home-main-copy">
                <div className="document-kicker">{trimmedSearchQuery ? "搜索结果" : "最近文件"}</div>
                <h2 className="home-main-title">{trimmedSearchQuery ? "搜索" : "最近"}</h2>
              </div>

              <div className="home-main-actions">
                <button className="compact-button compact-button-muted" disabled={isBusy} onClick={() => void generateDraft()}>
                  <Sparkles className="h-4 w-4" />
                  生成草稿
                </button>
                <button className="compact-button compact-button-strong" disabled={isBusy} onClick={() => void createDraftNote()}>
                  <Plus className="h-4 w-4" />
                  新建笔记
                </button>
              </div>
            </div>

            <div className="home-status-strip">
              <div className="home-status-item">
                <div className="home-status-label">最近文件</div>
                <div className="home-status-value">{recentNotes.length}</div>
              </div>
              <div className="home-status-item">
                <div className="home-status-label">AI 联想</div>
                <div className="home-status-value">{relatedHits.length}</div>
              </div>
              <div className="home-status-item">
                <div className="home-status-label">{trimmedSearchQuery ? "关键词" : "状态"}</div>
                <div className="home-status-value">{trimmedSearchQuery || homeStatusLabel}</div>
              </div>
            </div>

            <div className="home-main-list">
              {trimmedSearchQuery ? (
                searchHits.length ? (
                  searchHits.map((hit) => <ListCard key={hit.path} hit={hit} onClick={() => void selectPath(hit.path)} />)
                ) : (
                  <div className="home-empty-card">没有匹配内容。</div>
                )
              ) : recentNotes.length ? (
                recentNotes.map((note) => (
                  <button key={note.id} className="home-row" onClick={() => void selectPath(note.relative_path, "note")}>
                    <div className="home-row-title">{note.title}</div>
                    <div className="home-row-meta">
                      <span className="truncate">{note.relative_path}</span>
                    </div>
                    <div className="home-row-snippet">{note.summary || "打开继续。"}</div>
                  </button>
                ))
              ) : (
                <div className="home-empty-card">暂无内容。</div>
              )}
            </div>
          </div>

          <aside className="home-side-surface">
            <div className="home-side-head">
              <div>
                <div className="document-kicker">AI 联想</div>
                <h2 className="home-side-title">相关</h2>
              </div>
            </div>

            <div className="home-list">
              {relatedHits.length ? (
                relatedHits.map((hit) => <ListCard key={hit.path} hit={hit} onClick={() => void selectPath(hit.path)} />)
              ) : (
                <div className="home-empty-card">暂无结果。</div>
              )}
            </div>
          </aside>
        </section>
      </div>
    </>
  );
}

function ListCard({ hit, onClick }: { hit: SearchHit; onClick: () => void }) {
  return (
    <button className="home-row" onClick={onClick}>
      <div className="home-row-title">
        <FileText className="mr-1.5 inline h-3.5 w-3.5 text-slate-400 align-[-2px]" />
        {hit.title}
      </div>
      <div className="home-row-meta">
        <span className="truncate">{hit.path}</span>
        <span className="home-row-kind">{hit.kind === "note" ? "笔记" : "文件"}</span>
      </div>
      <div className="home-row-snippet">{hit.snippet || "打开查看。"}</div>
    </button>
  );
}
