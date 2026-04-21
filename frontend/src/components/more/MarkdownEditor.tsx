import {
  Bold,
  Code,
  Columns2,
  Eye,
  Heading1,
  Heading2,
  Italic,
  Link2,
  List,
  ListOrdered,
  Quote,
  SquareCode,
  Strikethrough,
} from "lucide-react";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";

import { MarkdownView } from "@/components/MarkdownView";

type Props = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
};

type MdMode = "split" | "preview";

export type MarkdownEditorHandle = {
  focusEdit: () => void;
  toggleMode: () => void;
};

const MODE_STORAGE_KEY = "more.markdownEditor.mode";

function readInitialMode(): MdMode {
  if (typeof window === "undefined") {
    return "split";
  }
  const stored = window.localStorage.getItem(MODE_STORAGE_KEY);
  return stored === "preview" ? "preview" : "split";
}

type WrapAction =
  | { kind: "wrap"; before: string; after: string; placeholder?: string }
  | { kind: "linePrefix"; prefix: string; placeholder?: string }
  | { kind: "link" }
  | { kind: "codeBlock" };

const ACTIONS: Array<{
  id: string;
  label: string;
  shortcut?: string;
  icon: React.ReactNode;
  action: WrapAction;
}> = [
  {
    id: "bold",
    label: "加粗",
    shortcut: "Ctrl+B",
    icon: <Bold className="h-3.5 w-3.5" />,
    action: { kind: "wrap", before: "**", after: "**", placeholder: "加粗文字" },
  },
  {
    id: "italic",
    label: "斜体",
    shortcut: "Ctrl+I",
    icon: <Italic className="h-3.5 w-3.5" />,
    action: { kind: "wrap", before: "*", after: "*", placeholder: "斜体文字" },
  },
  {
    id: "strike",
    label: "删除线",
    icon: <Strikethrough className="h-3.5 w-3.5" />,
    action: { kind: "wrap", before: "~~", after: "~~", placeholder: "删除文字" },
  },
  {
    id: "h1",
    label: "一级标题",
    icon: <Heading1 className="h-3.5 w-3.5" />,
    action: { kind: "linePrefix", prefix: "# ", placeholder: "标题" },
  },
  {
    id: "h2",
    label: "二级标题",
    icon: <Heading2 className="h-3.5 w-3.5" />,
    action: { kind: "linePrefix", prefix: "## ", placeholder: "小节" },
  },
  {
    id: "quote",
    label: "引用",
    icon: <Quote className="h-3.5 w-3.5" />,
    action: { kind: "linePrefix", prefix: "> ", placeholder: "引用内容" },
  },
  {
    id: "ul",
    label: "无序列表",
    icon: <List className="h-3.5 w-3.5" />,
    action: { kind: "linePrefix", prefix: "- ", placeholder: "列表项" },
  },
  {
    id: "ol",
    label: "有序列表",
    icon: <ListOrdered className="h-3.5 w-3.5" />,
    action: { kind: "linePrefix", prefix: "1. ", placeholder: "列表项" },
  },
  {
    id: "code",
    label: "行内代码",
    icon: <Code className="h-3.5 w-3.5" />,
    action: { kind: "wrap", before: "`", after: "`", placeholder: "代码" },
  },
  {
    id: "codeblock",
    label: "代码块",
    icon: <SquareCode className="h-3.5 w-3.5" />,
    action: { kind: "codeBlock" },
  },
  {
    id: "link",
    label: "链接",
    shortcut: "Ctrl+K",
    icon: <Link2 className="h-3.5 w-3.5" />,
    action: { kind: "link" },
  },
];

export const MarkdownEditor = forwardRef<MarkdownEditorHandle, Props>(function MarkdownEditor(
  { value, onChange, placeholder = "开始输入 Markdown…" },
  ref
) {
  const [mode, setMode] = useState<MdMode>(readInitialMode);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Persist mode choice across sessions so the user does not have to re-pick on every file.
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(MODE_STORAGE_KEY, mode);
  }, [mode]);

  useImperativeHandle(
    ref,
    () => ({
      focusEdit: () => {
        setMode("split");
        queueMicrotask(() => {
          textareaRef.current?.focus();
        });
      },
      toggleMode: () => {
        setMode((current) => (current === "split" ? "preview" : "split"));
      },
    }),
    []
  );

  const applyAction = useCallback(
    (action: WrapAction) => {
      const textarea = textareaRef.current;
      if (!textarea) {
        return;
      }
      textarea.focus();
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const current = value;
      const selected = current.slice(start, end);

      if (action.kind === "wrap") {
        const text = selected || action.placeholder || "";
        const insert = `${action.before}${text}${action.after}`;
        const next = current.slice(0, start) + insert + current.slice(end);
        onChange(next);
        queueMicrotask(() => {
          if (!textareaRef.current) return;
          const cursor = start + action.before.length;
          textareaRef.current.setSelectionRange(cursor, cursor + text.length);
          textareaRef.current.focus();
        });
        return;
      }

      if (action.kind === "linePrefix") {
        const lineStart = current.lastIndexOf("\n", start - 1) + 1;
        const lineEnd = current.indexOf("\n", end);
        const blockEnd = lineEnd === -1 ? current.length : lineEnd;
        const block = current.slice(lineStart, blockEnd);
        const pieces = block.length ? block.split("\n") : [""];
        const transformed = pieces
          .map((piece) => {
            if (piece.startsWith(action.prefix)) {
              return piece.slice(action.prefix.length);
            }
            return `${action.prefix}${piece || action.placeholder || ""}`;
          })
          .join("\n");
        const next = current.slice(0, lineStart) + transformed + current.slice(blockEnd);
        onChange(next);
        queueMicrotask(() => {
          if (!textareaRef.current) return;
          textareaRef.current.focus();
          const cursor = lineStart + transformed.length;
          textareaRef.current.setSelectionRange(cursor, cursor);
        });
        return;
      }

      if (action.kind === "codeBlock") {
        const text = selected || "";
        const insert = `\n\`\`\`\n${text || "代码"}\n\`\`\`\n`;
        const next = current.slice(0, start) + insert + current.slice(end);
        onChange(next);
        queueMicrotask(() => {
          if (!textareaRef.current) return;
          const cursor = start + insert.indexOf("\n```\n") + 5;
          textareaRef.current.setSelectionRange(cursor, cursor + (text ? text.length : 2));
          textareaRef.current.focus();
        });
        return;
      }

      if (action.kind === "link") {
        const label = selected || "链接文字";
        const url = "https://";
        const insert = `[${label}](${url})`;
        const next = current.slice(0, start) + insert + current.slice(end);
        onChange(next);
        queueMicrotask(() => {
          if (!textareaRef.current) return;
          const cursor = start + insert.indexOf("(") + 1;
          textareaRef.current.setSelectionRange(cursor, cursor + url.length);
          textareaRef.current.focus();
        });
      }
    },
    [onChange, value]
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (!(event.ctrlKey || event.metaKey)) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "b") {
        event.preventDefault();
        applyAction({ kind: "wrap", before: "**", after: "**", placeholder: "加粗文字" });
      } else if (key === "i") {
        event.preventDefault();
        applyAction({ kind: "wrap", before: "*", after: "*", placeholder: "斜体文字" });
      } else if (key === "k") {
        event.preventDefault();
        applyAction({ kind: "link" });
      }
    },
    [applyAction]
  );

  const isSplit = mode === "split";

  return (
    <section className="markdown-editor">
      <div className="markdown-toolbar">
        <div className="markdown-toolbar-actions">
          {ACTIONS.map((item) => (
            <button
              key={item.id}
              type="button"
              className="markdown-toolbar-button"
              title={item.shortcut ? `${item.label} (${item.shortcut})` : item.label}
              onClick={() => applyAction(item.action)}
              disabled={!isSplit}
            >
              {item.icon}
            </button>
          ))}
        </div>
        <div className="markdown-view-switch" role="tablist" aria-label="视图模式">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "split"}
            className={`markdown-view-switch-button ${mode === "split" ? "markdown-view-switch-button-active" : ""}`}
            onClick={() => {
              setMode("split");
              queueMicrotask(() => textareaRef.current?.focus());
            }}
            title="编辑 · 实时预览"
          >
            <Columns2 className="h-3.5 w-3.5" />
            <span>编辑</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "preview"}
            className={`markdown-view-switch-button ${mode === "preview" ? "markdown-view-switch-button-active" : ""}`}
            onClick={() => setMode("preview")}
            title="仅预览"
          >
            <Eye className="h-3.5 w-3.5" />
            <span>预览</span>
          </button>
        </div>
      </div>
      <div className={`markdown-editor-body markdown-editor-body-${mode}`}>
        {isSplit ? (
          <>
            <textarea
              ref={textareaRef}
              className="markdown-editor-textarea markdown-editor-textarea-split"
              value={value}
              onChange={(event) => onChange(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              spellCheck={false}
            />
            <div className="markdown-editor-preview markdown-editor-preview-split" aria-live="polite">
              <MarkdownView
                source={value}
                emptyFallback={<div className="markdown-empty">在左侧输入内容，右侧会实时预览。</div>}
              />
            </div>
          </>
        ) : (
          <div
            className="markdown-editor-preview markdown-editor-preview-tapable"
            title="双击进入编辑"
            onDoubleClick={() => {
              setMode("split");
              queueMicrotask(() => textareaRef.current?.focus());
            }}
          >
            <MarkdownView
              source={value}
              emptyFallback={
                <div className="markdown-empty">
                  暂无内容。点击「编辑」或双击此处开始书写。
                </div>
              }
            />
          </div>
        )}
      </div>
    </section>
  );
});
