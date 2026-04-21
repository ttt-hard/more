import { useCallback, useEffect, useLayoutEffect, useRef } from "react";

/**
 * LiveMarkdownEditor
 *
 * A single contentEditable surface. The user types plain markdown — we keep
 * the raw characters (so `**`, `#`, `-` markers stay visible while the caret
 * is on that line) but wrap them in styled spans so `**bold**` looks bold,
 * `# h1` looks like a big heading, and so on. There is no separate preview
 * pane: every keystroke redraws the decorations in place.
 *
 * Typora-style active-line: only the line containing the caret shows the
 * raw markdown markers (`#`, `**`, `- `, ...). Every other line renders as
 * the "resting" styled output with the markers faded out. This gives the
 * WYSIWYG feel users expect from Typora while keeping the underlying source
 * plain Markdown. When the editor loses focus, every line is "resting",
 * i.e. no markers are visible. Implementation: we toggle an `.md-line-active`
 * class on the `<div class="md-line">` that wraps the caret row; the CSS
 * in `styles.css` hides `.md-mark` for every line that lacks that class.
 *
 * Caret preservation is done by computing the caret's plain-text offset before
 * we rewrite innerHTML and restoring it by walking text nodes afterwards.
 */

type Props = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
};

const ESCAPE_MAP: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (ch) => ESCAPE_MAP[ch] ?? ch);
}

function decorateInline(raw: string): string {
  let html = escapeHtml(raw);
  // Inline code first — code contents should not be touched by emphasis.
  html = html.replace(
    /`([^`\n]+)`/g,
    '<span class="md-mark">`</span><span class="md-inline-code">$1</span><span class="md-mark">`</span>'
  );
  // Bold **foo** (skip *** which would collide with italic).
  html = html.replace(
    /\*\*([^\*\n]+)\*\*/g,
    '<span class="md-mark">**</span><span class="md-bold">$1</span><span class="md-mark">**</span>'
  );
  // Italic *foo* — not inside a ** pair (we already matched bolds, so the
  // remaining * are italic markers).
  html = html.replace(
    /(^|[^\*])\*([^\*\n]+)\*(?!\*)/g,
    '$1<span class="md-mark">*</span><span class="md-italic">$2</span><span class="md-mark">*</span>'
  );
  // Strike ~~foo~~
  html = html.replace(
    /~~([^~\n]+)~~/g,
    '<span class="md-mark">~~</span><span class="md-strike">$1</span><span class="md-mark">~~</span>'
  );
  // Links [label](url) — keep the markers visible, color the label.
  html = html.replace(
    /\[([^\]\n]+)\]\(([^\)\n]+)\)/g,
    (_match, label, url) =>
      `<span class="md-mark">[</span><span class="md-link">${label}</span><span class="md-mark">](${url})</span>`
  );
  return html;
}

function decorateLine(line: string): string {
  if (line === "") {
    // Empty line — browsers need a <br> inside a block element for a visible
    // caret row. The \u200B zero-width space keeps the line measurable when
    // copied, but we rely on the <br> for caret placement.
    return '<div class="md-line"><br /></div>';
  }
  const heading = line.match(/^(#{1,6})\s(.*)$/);
  if (heading) {
    const level = heading[1].length;
    const marker = `${heading[1]} `;
    return `<div class="md-line md-h${level}"><span class="md-mark">${escapeHtml(marker)}</span>${decorateInline(heading[2])}</div>`;
  }
  const bullet = line.match(/^(\s*)([-*+])\s(.*)$/);
  if (bullet) {
    const indent = bullet[1];
    const marker = `${indent}${bullet[2]} `;
    return `<div class="md-line md-ul"><span class="md-mark">${escapeHtml(marker)}</span>${decorateInline(bullet[3])}</div>`;
  }
  const ordered = line.match(/^(\s*)(\d+)\.\s(.*)$/);
  if (ordered) {
    const indent = ordered[1];
    const marker = `${indent}${ordered[2]}. `;
    return `<div class="md-line md-ol"><span class="md-mark">${escapeHtml(marker)}</span>${decorateInline(ordered[3])}</div>`;
  }
  const quote = line.match(/^(>\s?)(.*)$/);
  if (quote) {
    return `<div class="md-line md-quote"><span class="md-mark">${escapeHtml(quote[1])}</span>${decorateInline(quote[2])}</div>`;
  }
  return `<div class="md-line">${decorateInline(line)}</div>`;
}

function decorate(source: string): string {
  if (!source) {
    // Empty doc — render one caret-friendly line so the user can type into it.
    return '<div class="md-line"><br /></div>';
  }
  const lines = source.split("\n");
  return lines.map(decorateLine).join("");
}

function getCaretOffset(root: HTMLElement): number {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0) return 0;
  const range = selection.getRangeAt(0);
  if (!root.contains(range.endContainer)) return 0;
  const pre = range.cloneRange();
  pre.selectNodeContents(root);
  pre.setEnd(range.endContainer, range.endOffset);
  return pre.toString().length;
}

function setCaretOffset(root: HTMLElement, targetOffset: number): void {
  const selection = window.getSelection();
  if (!selection) return;
  let offset = Math.max(0, targetOffset);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    const textLen = (node.textContent ?? "").length;
    if (offset <= textLen) {
      const range = document.createRange();
      range.setStart(node, offset);
      range.collapse(true);
      selection.removeAllRanges();
      selection.addRange(range);
      return;
    }
    offset -= textLen;
    node = walker.nextNode();
  }
  // Fallback: place caret at the very end.
  const range = document.createRange();
  range.selectNodeContents(root);
  range.collapse(false);
  selection.removeAllRanges();
  selection.addRange(range);
}

/**
 * Read the text out of the contenteditable surface as the canonical
 * markdown source. We can't just use innerText because Firefox and Chrome
 * disagree on how block boundaries translate to newlines. Walking the child
 * nodes explicitly makes it deterministic: each immediate child div is one
 * line, and hard <br>s inside are also line breaks.
 */
function extractText(root: HTMLElement): string {
  const lines: string[] = [];
  for (const child of Array.from(root.childNodes)) {
    if (child.nodeType === Node.TEXT_NODE) {
      lines.push(child.textContent ?? "");
      continue;
    }
    if (child.nodeType === Node.ELEMENT_NODE) {
      const el = child as HTMLElement;
      if (el.tagName === "BR") {
        lines.push("");
        continue;
      }
      // Recursive flatten: nested divs from paste events etc.
      const nested = el.innerText.replace(/\r\n/g, "\n");
      // innerText inside a single <div> line may already be correct, but if
      // nested divs exist it'll contain extra \n. Keep as-is; split below.
      for (const piece of nested.split("\n")) {
        lines.push(piece);
      }
      continue;
    }
  }
  return lines.join("\n");
}

function findActiveLine(root: HTMLElement): HTMLElement | null {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0) return null;
  const range = selection.getRangeAt(0);
  let node: Node | null = range.endContainer;
  while (node && node !== root) {
    if (
      node.nodeType === Node.ELEMENT_NODE &&
      (node as HTMLElement).classList?.contains("md-line")
    ) {
      return node as HTMLElement;
    }
    node = node.parentNode;
  }
  return null;
}

function clearActiveLines(root: HTMLElement): void {
  const previous = root.querySelectorAll(".md-line-active");
  previous.forEach((el) => el.classList.remove("md-line-active"));
}

export function LiveMarkdownEditor({ value, onChange, placeholder }: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  // Remember what value we last rendered to the DOM. If the next value we get
  // already matches that, we do not need to rewrite innerHTML (and risk
  // disturbing the caret).
  const lastRenderedRef = useRef<string | null>(null);
  const pendingCaretRef = useRef<number | null>(null);
  const composingRef = useRef(false);

  const applyActiveLine = useCallback(() => {
    const root = rootRef.current;
    if (!root) return;
    // Only paint active-line while the editor actually owns focus. When the
    // user clicks elsewhere we want every line to fall back to the "resting"
    // rendering (markers hidden), matching Typora's WYSIWYG preview look.
    if (document.activeElement !== root) {
      clearActiveLines(root);
      return;
    }
    const target = findActiveLine(root);
    clearActiveLines(root);
    if (target) {
      target.classList.add("md-line-active");
    }
  }, []);

  // Render decorations whenever the value prop changes. Uses useLayoutEffect
  // so the DOM is updated before the browser paints (prevents caret flash).
  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    if (lastRenderedRef.current === value) return;
    if (composingRef.current) return;
    const hadFocus = document.activeElement === root;
    const caret = hadFocus ? getCaretOffset(root) : pendingCaretRef.current;
    root.innerHTML = decorate(value);
    lastRenderedRef.current = value;
    if (hadFocus && caret !== null) {
      setCaretOffset(root, caret);
    }
    // Redecoration wipes the previous `.md-line-active` class; re-apply it
    // based on the restored caret position.
    applyActiveLine();
  }, [value, applyActiveLine]);

  // Ensure placeholder visibility updates when value is empty.
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    if (!value) {
      root.setAttribute("data-empty", "true");
    } else {
      root.removeAttribute("data-empty");
    }
  }, [value]);

  // Track caret movement so the active line highlight (showing markdown
  // markers) follows the user's cursor. We listen on `selectionchange` at
  // document level because contentEditable does not emit a reliable
  // per-element selection event.
  useEffect(() => {
    const handler = () => {
      applyActiveLine();
    };
    document.addEventListener("selectionchange", handler);
    return () => {
      document.removeEventListener("selectionchange", handler);
    };
  }, [applyActiveLine]);

  return (
    <div
      ref={rootRef}
      className="live-markdown-editor"
      contentEditable
      spellCheck={false}
      suppressContentEditableWarning
      role="textbox"
      aria-multiline="true"
      aria-label="Markdown 编辑器"
      data-placeholder={placeholder ?? "开始输入 Markdown…"}
      onFocus={applyActiveLine}
      onBlur={() => {
        const root = rootRef.current;
        if (root) clearActiveLines(root);
      }}
      onCompositionStart={() => {
        composingRef.current = true;
      }}
      onCompositionEnd={(event) => {
        composingRef.current = false;
        const root = event.currentTarget;
        pendingCaretRef.current = getCaretOffset(root);
        const text = extractText(root);
        // Mark that we caused this value so the layout effect will skip reflow.
        lastRenderedRef.current = text;
        onChange(text);
      }}
      onInput={(event) => {
        const root = event.currentTarget;
        if (composingRef.current) {
          // Let IME composition finish before reporting the value.
          return;
        }
        pendingCaretRef.current = getCaretOffset(root);
        const text = extractText(root);
        // We own this change — skip the layout effect's redecoration for the
        // exact same value so the caret does not move mid-keystroke.
        lastRenderedRef.current = text;
        onChange(text);
        // Still, decorations need to reflect markers that just appeared. Force
        // a decoration redraw on the NEXT animation frame so typing remains
        // snappy while the preview keeps up.
        requestAnimationFrame(() => {
          const current = rootRef.current;
          if (!current) return;
          if (lastRenderedRef.current !== text) return;
          if (composingRef.current) return;
          const caret = getCaretOffset(current);
          current.innerHTML = decorate(text);
          setCaretOffset(current, caret);
        });
      }}
      onPaste={(event) => {
        // Force plain-text paste so we never inject foreign HTML.
        event.preventDefault();
        const text = event.clipboardData.getData("text/plain");
        const root = event.currentTarget;
        const selection = window.getSelection();
        if (!selection || selection.rangeCount === 0) return;
        const range = selection.getRangeAt(0);
        range.deleteContents();
        range.insertNode(document.createTextNode(text));
        range.collapse(false);
        selection.removeAllRanges();
        selection.addRange(range);
        pendingCaretRef.current = getCaretOffset(root);
        const next = extractText(root);
        lastRenderedRef.current = next;
        onChange(next);
      }}
    />
  );
}
