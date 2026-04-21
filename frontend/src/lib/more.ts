import type { ApprovalRequest, LLMSettings, NoteMeta, Preference, SearchHit } from "../types";

export const DEFAULT_WORKSPACE_PATH = "D:\\more\\workspace";
export const GLOBAL_DRAFT_KEY = "__workspace__";

export const DEFAULT_PREFERENCES: Preference = {
  language: "zh-CN",
  answer_style: "concise",
  default_note_dir: "Inbox",
  theme: "light",
};

export const EMPTY_LLM_SETTINGS: LLMSettings = {
  base_url: "",
  api_key_set: false,
  api_key_preview: "",
  model: "",
  timeout: 60,
  is_configured: false,
};

export function buildDraftNotePath(directory: string): string {
  const date = new Date();
  const stamp = [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
    "-",
    String(date.getHours()).padStart(2, "0"),
    String(date.getMinutes()).padStart(2, "0"),
    String(date.getSeconds()).padStart(2, "0"),
  ].join("");

  return `${directory.replace(/[\\/]+$/, "")}/note-${stamp}.md`;
}

export function parseTags(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function messageFromError(error: unknown): string {
  if (error instanceof Error) {
    const message = error.message;
    if (message.includes("Workspace does not exist")) {
      return "工作区路径不存在，请确认路径后再试。";
    }
    if (message.includes("No active workspace")) {
      return "当前还没有激活的工作区，请先创建或打开工作区。";
    }
    if (message.toLowerCase().includes("timeout")) {
      return "请求超时，请检查网络、Base URL 或模型服务状态。";
    }
    if (message.toLowerCase().includes("unauthorized") || message.includes("401")) {
      return "模型鉴权失败，请检查 API Key 是否有效。";
    }
    return message;
  }

  return "发生了未预期的错误。";
}

export function toSearchLikeHit(note: NoteMeta): SearchHit {
  return {
    path: note.relative_path,
    kind: "note",
    title: note.title,
    score: 0,
    snippet: note.summary || note.tags.map((tag) => `#${tag}`).join(" "),
  };
}

export function basename(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  const parts = normalized.split("/");
  return parts[parts.length - 1] || normalized;
}

export function getSelectedNote(notes: NoteMeta[], selectedPath: string | null): NoteMeta | null {
  if (!selectedPath) {
    return null;
  }
  return notes.find((note) => note.relative_path === selectedPath) ?? null;
}

export function getRecentNotes(notes: NoteMeta[], limit = 8, activeTag?: string | null): NoteMeta[] {
  const source = activeTag ? notes.filter((note) => note.tags.includes(activeTag)) : notes;
  return [...source]
    .sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime())
    .slice(0, limit);
}

export function getRelatedSearchHits({
  notes,
  searchHits,
  selectedNote,
  recentNotes,
  limit = 6,
}: {
  notes: NoteMeta[];
  searchHits: SearchHit[];
  selectedNote: NoteMeta | null;
  recentNotes: NoteMeta[];
  limit?: number;
}): SearchHit[] {
  if (searchHits.length) {
    return searchHits.slice(0, limit);
  }

  if (selectedNote) {
    const tagged = notes.filter(
      (note) =>
        note.relative_path !== selectedNote.relative_path &&
        note.tags.some((tag) => selectedNote.tags.includes(tag))
    );
    return tagged.slice(0, limit).map(toSearchLikeHit);
  }

  return recentNotes.slice(0, limit).map(toSearchLikeHit);
}

export function countPendingApprovals(approvals: ApprovalRequest[]): number {
  return approvals.filter((item) => item.status === "pending").length;
}

export function readInitialWorkspacePath(): string {
  if (typeof window === "undefined") {
    return DEFAULT_WORKSPACE_PATH;
  }

  return window.localStorage.getItem("more.workspacePath") || DEFAULT_WORKSPACE_PATH;
}
