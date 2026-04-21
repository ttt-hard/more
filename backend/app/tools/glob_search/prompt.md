Find workspace files by glob pattern (recursive, pattern-based).

## When to use
- Finding all files of a type: `**/*.md`, `**/*.py`, `Projects/**/README.md`.
- Enumerating a subtree before bulk reading.
- Validating that files under a convention exist (e.g., `Notes/2026/**/*.md`).

## Do NOT use for
- **Content search**: use `grep_search` — this tool only matches **file names / paths**, not file contents.
- **Single known path**: just use `read_file` / `list_directory` directly.
- **Semantic / fuzzy search of notes**: use `search_notes` — glob is exact literal pattern.

## Parameters
- `pattern` (string, required): glob pattern relative to workspace root. Supports `*`, `**`, `?`, `[abc]`. Example: `"Notes/**/*.md"`.
- `include_hidden` (boolean, optional, default `false`): when `true`, include dotfiles (`.more/...`, `.git/...`). Rarely needed.

## Output
- `summary`: header with count, then up to 20 matches as `- file: path/to/a.md`.
- `citations`: top 5 match paths for downstream reference.
- `payload.count`: total match count (may exceed 20 shown).

If count > 20, narrow the pattern or continue with `grep_search` on a specific subset.

## Chaining
- `glob_search` → `read_file`: enumerate candidates, inspect the interesting ones.
- `glob_search` → `grep_search`: restrict grep to a known file-type subset (not yet directly supported via args; manual filter via pattern).

## Patterns cheat-sheet
- `*.md` — all markdown in root
- `**/*.md` — all markdown recursively
- `Notes/**/*.md` — under Notes/ only
- `**/README.{md,txt}` — multiple extensions
- `Archive/2025/*` — specific depth

## Risks / surprises
- **Performance**: very broad patterns (`**/*`) on a large workspace can return thousands of paths. Narrow before calling.
- **Hidden files ignored by default**: `.more/` internals will not match unless `include_hidden=true`; this is correct for almost all agent tasks.
