Move or rename a workspace file or directory. May require user approval.

## When to use
- Renaming a note (e.g., `Inbox/untitled.md` → `Notes/system-design.md`).
- Relocating a file to a different folder as part of organizing work.
- Consolidating files into an archive folder.

## Do NOT use for
- **Copying**: this tool moves (the source no longer exists after). There is no copy tool; use `read_file` + `write_file` if you need to duplicate.
- **Moving files outside the workspace**: workspace FS rejects paths that escape the root.
- **Bulk renames**: call once per path. For pattern-based batching, first `glob_search` to enumerate paths.

## Approval behavior
This tool is **approval-gated**. Specifically:
- If `overwrite=true` OR the source is a directory, the call returns `ok=true, requires_approval=true, task_state="awaiting_approval"` and an `approval_required` event. The actual move does NOT happen until the user approves via the approvals UI.
- Simple file rename (no overwrite, source is a file, target missing) executes immediately.

When you get `awaiting_approval`, STOP further file mutations in the same turn and surface the approval request to the user. Do not call `move_path` again with the same args.

## Parameters
- `source_path` (string, required): current workspace-relative path.
- `target_path` (string, required): new workspace-relative path. Parent directory is auto-created.
- `overwrite` (boolean, optional, default `false`): if `true`, allow replacing an existing target. Triggers approval.

## Output
- Executed move: `summary` says "Moved X to Y", `payload.entry` contains the new FS entry.
- Awaiting approval: `summary` says "awaiting approval", `events[].approval` includes the approval request id. You should wait; do not retry.

## Chaining
- `list_directory` or `glob_search` → `move_path`: confirm source exists before moving.
- `move_path` (approved) → `read_file`: verify the new location has the expected content.

## Risks
- **Data loss via overwrite**: overwriting an existing file discards the original. The approval gate exists precisely to prevent this happening silently.
- **Broken links**: if other notes reference the old path, they will not auto-update. Consider running `grep_search "OldPath"` afterwards and calling `edit_file` on each referrer.
