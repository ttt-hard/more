import { useDeferredValue, useMemo } from "react";

import { renderMarkdown } from "@/lib/markdown";

type Props = {
  source: string;
  className?: string;
  emptyFallback?: React.ReactNode;
};

export function MarkdownView({ source, className, emptyFallback = null }: Props) {
  // `renderMarkdown` is regex-heavy on large strings and followed by a
  // `dangerouslySetInnerHTML` commit. When an assistant message is streaming,
  // the source mutates on every token — re-running this chain 60 times per
  // second blocks the main thread long enough to make other interactive
  // surfaces (the Markdown editor in particular) feel frozen.
  //
  // `useDeferredValue` lets React hold back a stale copy of `source` whenever
  // urgent work (user input, focus, scroll) is in flight, and only catch up
  // when the browser is idle. The memoised parse runs against that deferred
  // value, so the streaming bubble still updates visually but no longer
  // starves sibling components of frame budget.
  const deferredSource = useDeferredValue(source);
  const html = useMemo(() => renderMarkdown(deferredSource), [deferredSource]);
  if (!source.trim()) {
    return <>{emptyFallback}</>;
  }
  return (
    <div
      className={`markdown-surface ${className ?? ""}`.trim()}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
