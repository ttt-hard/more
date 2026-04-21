// Lightweight Markdown → HTML renderer tailored for note previews and
// assistant replies. It intentionally stays small: it does not aim to support
// every edge case of CommonMark, but it covers the formatting users expect
// from an in-app Markdown surface (headings, emphasis, lists, code, quotes,
// links, horizontal rules) while keeping output safe for `dangerouslySetInnerHTML`.

const ESCAPE_MAP: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ESCAPE_MAP[char] ?? char);
}

function sanitizeUrl(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) {
    return "#";
  }
  // Disallow javascript: and data: URLs to avoid XSS.
  if (/^\s*(javascript|data|vbscript):/i.test(trimmed)) {
    return "#";
  }
  return escapeHtml(trimmed);
}

function renderInline(raw: string): string {
  let text = escapeHtml(raw);

  // Fenced code — not expected inline, but guard against stray backticks.
  text = text.replace(/`([^`]+?)`/g, (_match, code) => `<code>${code}</code>`);

  // Images: ![alt](url)
  text = text.replace(
    /!\[([^\]]*)\]\(([^)]+)\)/g,
    (_match, alt, url) => `<img src="${sanitizeUrl(url)}" alt="${escapeHtml(alt)}" loading="lazy" />`
  );

  // Links: [text](url)
  text = text.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    (_match, label, url) =>
      `<a href="${sanitizeUrl(url)}" target="_blank" rel="noreferrer noopener">${label}</a>`
  );

  // Bold+italic: ***text***
  text = text.replace(/\*\*\*([^*]+)\*\*\*/g, "<strong><em>$1</em></strong>");

  // Bold: **text** or __text__
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/__([^_]+)__/g, "<strong>$1</strong>");

  // Italic: *text* or _text_
  text = text.replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, "$1<em>$2</em>");
  text = text.replace(/(^|[^_])_([^_\s][^_]*?)_(?!_)/g, "$1<em>$2</em>");

  // Strikethrough: ~~text~~
  text = text.replace(/~~([^~]+)~~/g, "<del>$1</del>");

  return text;
}

type BlockRenderer = (lines: string[], startIndex: number) => { html: string; nextIndex: number } | null;

function consumeList(
  lines: string[],
  startIndex: number,
  ordered: boolean
): { html: string; nextIndex: number } {
  const pattern = ordered ? /^(\s*)(\d+)[.)]\s+(.*)$/ : /^(\s*)[-*+]\s+(.*)$/;
  const items: string[] = [];
  let index = startIndex;

  while (index < lines.length) {
    const line = lines[index];
    const match = line.match(pattern);
    if (!match) {
      break;
    }
    const content = ordered ? match[3] : match[2];
    const collected: string[] = [content];
    index += 1;
    // consume continuation lines (indented further than the list marker)
    while (index < lines.length) {
      const next = lines[index];
      if (!next.trim()) {
        break;
      }
      if (next.match(pattern)) {
        break;
      }
      collected.push(next.trim());
      index += 1;
    }
    items.push(collected.join(" "));
    // skip blank lines between items
    while (index < lines.length && !lines[index].trim()) {
      const lookAhead = lines[index + 1];
      if (lookAhead && lookAhead.match(pattern)) {
        index += 1;
      } else {
        break;
      }
    }
  }

  const tag = ordered ? "ol" : "ul";
  const html = `<${tag}>${items.map((item) => `<li>${renderInline(item)}</li>`).join("")}</${tag}>`;
  return { html, nextIndex: index };
}

function consumeBlockquote(
  lines: string[],
  startIndex: number
): { html: string; nextIndex: number } {
  const collected: string[] = [];
  let index = startIndex;
  while (index < lines.length) {
    const match = lines[index].match(/^>\s?(.*)$/);
    if (!match) {
      break;
    }
    collected.push(match[1]);
    index += 1;
  }
  const html = `<blockquote>${renderBlocks(collected.join("\n"))}</blockquote>`;
  return { html, nextIndex: index };
}

function consumeCodeFence(
  lines: string[],
  startIndex: number
): { html: string; nextIndex: number } | null {
  const opening = lines[startIndex].match(/^```([\w-]*)\s*$/);
  if (!opening) {
    return null;
  }
  const language = opening[1] ? escapeHtml(opening[1]) : "";
  const collected: string[] = [];
  let index = startIndex + 1;
  while (index < lines.length) {
    if (/^```\s*$/.test(lines[index])) {
      index += 1;
      const classAttr = language ? ` class="language-${language}"` : "";
      const html = `<pre><code${classAttr}>${escapeHtml(collected.join("\n"))}</code></pre>`;
      return { html, nextIndex: index };
    }
    collected.push(lines[index]);
    index += 1;
  }
  // Unclosed fence — still render what we have.
  const classAttr = language ? ` class="language-${language}"` : "";
  const html = `<pre><code${classAttr}>${escapeHtml(collected.join("\n"))}</code></pre>`;
  return { html, nextIndex: index };
}

const BLOCK_RENDERERS: BlockRenderer[] = [
  (lines, i) => consumeCodeFence(lines, i),
  (lines, i) => {
    const match = lines[i].match(/^(#{1,6})\s+(.*)$/);
    if (!match) {
      return null;
    }
    const level = match[1].length;
    return {
      html: `<h${level}>${renderInline(match[2].trim())}</h${level}>`,
      nextIndex: i + 1,
    };
  },
  (lines, i) => {
    if (/^(\s*)[-*+]\s+/.test(lines[i])) {
      return consumeList(lines, i, false);
    }
    return null;
  },
  (lines, i) => {
    if (/^(\s*)\d+[.)]\s+/.test(lines[i])) {
      return consumeList(lines, i, true);
    }
    return null;
  },
  (lines, i) => {
    if (/^>\s?/.test(lines[i])) {
      return consumeBlockquote(lines, i);
    }
    return null;
  },
  (lines, i) => {
    if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(lines[i])) {
      return { html: "<hr />", nextIndex: i + 1 };
    }
    return null;
  },
];

function consumeParagraph(
  lines: string[],
  startIndex: number
): { html: string; nextIndex: number } {
  const collected: string[] = [];
  let index = startIndex;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      break;
    }
    if (BLOCK_RENDERERS.some((renderer) => renderer(lines, index))) {
      break;
    }
    collected.push(line.trim());
    index += 1;
  }
  if (!collected.length) {
    return { html: "", nextIndex: index + 1 };
  }
  const html = `<p>${renderInline(collected.join(" "))}</p>`;
  return { html, nextIndex: index };
}

function renderBlocks(source: string): string {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const pieces: string[] = [];
  let i = 0;
  while (i < lines.length) {
    if (!lines[i].trim()) {
      i += 1;
      continue;
    }
    let matched = false;
    for (const renderer of BLOCK_RENDERERS) {
      const result = renderer(lines, i);
      if (result) {
        pieces.push(result.html);
        i = result.nextIndex;
        matched = true;
        break;
      }
    }
    if (matched) {
      continue;
    }
    const paragraph = consumeParagraph(lines, i);
    if (paragraph.html) {
      pieces.push(paragraph.html);
    }
    i = paragraph.nextIndex;
  }
  return pieces.join("");
}

export function renderMarkdown(source: string): string {
  if (!source) {
    return "";
  }
  return renderBlocks(source);
}
