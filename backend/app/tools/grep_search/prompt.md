Search workspace text files for lines matching a pattern.

## When to use
- Locating files that mention a keyword, symbol, or TODO tag.
- Finding all references to an old path before renaming (after `move_path`, grep for the old path in notes to update cross-references).
- Quick "does this term exist?" check across the workspace.

## Do NOT use for
- **Finding files by name / extension**: use `glob_search`.
- **Semantic / meaning-based search**: use `search_notes` (retrieval pipeline with embeddings / BM25).
- **Binary file search**: this tool operates on text; binary files are skipped.

## Parameters
- `pattern` (string, required): substring to find. Whether this is regex or literal depends on `WorkspaceFS.grep` — prefer treating it as **literal** for predictability. Case-sensitivity follows workspace defaults.
- `include_hidden` (boolean, optional, default `false`): include dotfiles (`.more/`, `.git/`). Rarely needed.

## Output
- `summary`: header with count, then up to 20 hits formatted as `- path/to/file.md:LINE_NUMBER <line_text>`.
- `citations`: top 5 file paths for follow-up `read_file`.
- `payload.count`: total hits (may exceed 20 shown).

## Chaining
- `grep_search` → `read_file`: find a hit, read surrounding context.
- `grep_search` → `edit_file`: find an occurrence, replace it. When multiple occurrences exist and you want them all, use `edit_file` with `replace_all=true`.
- `move_path` → `grep_search "old_path"` → `edit_file` (per hit): update references after renaming.

## Tips
- **Narrow first**: `grep_search "api_key"` on a large workspace can flood context. If possible, scope by first `glob_search`-ing a folder, then only reading those files.
- **Truncated results**: the summary shows 20 lines max. If `payload.count` is much larger, refine the pattern before digging deeper.

## Risks
- **Matching in comments / strings**: grep is dumb about syntax. A match inside a code comment and inside executable code look the same. Always `read_file` around a hit before assuming semantics.
- **Line-level only**: grep returns lines, not multi-line blocks. For block context, `read_file` and extract programmatically.
