List files and subdirectories inside a workspace path.

## When to use
- Exploring an unfamiliar folder to understand its structure.
- Checking whether a target file exists before `read_file` / `write_file`.
- Discovering the default note directory (e.g., `Inbox/`) or user-created folders.

## Do NOT use for
- **Content search**: use `grep_search`.
- **Glob pattern match across the tree**: use `glob_search` (faster, recursive, pattern-based).
- **Reading file content**: this tool only returns names and types, not body.

## Parameters
- `path` (string, optional, default `"."`): workspace-relative directory. `"."` or empty means workspace root.

## Output
- `summary`: a header line with count, then up to 20 entries as `- file: Notes/a.md` or `- dir: Archive/`.
- `citations`: the requested path.
- `payload.path`: echoes the normalized path.

Note: **capped at 20 entries in the summary** to avoid blowing up context. If you expect more, call `glob_search` with a pattern instead, or paginate by listing subdirectories.

## Chaining
- `list_directory` → `read_file`: find an entry, then inspect it.
- `list_directory` → `list_directory`: descend into a subfolder.
- `list_directory` → `glob_search`: if the folder is large, switch to a pattern-based search.

## Edge cases
- Empty directory: returns a zero-count summary, still `ok=true`.
- Missing path: fails with `ok=false`; verify the parent directory first.
- Hidden entries (`.*`): current implementation returns them by default; to filter, post-process the list or use `glob_search` with explicit pattern.
