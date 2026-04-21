Request deletion of a workspace file or directory. **Always** requires user approval.

## When to use
- User explicitly asked to delete a file ("delete the draft", "remove the old notes").
- Cleaning up temporary artifacts after a successful import or refactor that the user confirmed.

## Do NOT use for
- **Silent cleanup**: never call `delete_path` unless the user asked. Even then, verify what will be deleted via `list_directory` or `read_file` first.
- **Moving to archive**: prefer `move_path` with `target_path="Archive/..."` — moves are reversible, deletes are not.
- **Clearing the workspace**: do not recurse-delete folders as a "reset" operation unless the user explicitly confirmed scope.

## Approval behavior
This tool is **unconditionally approval-gated**. Every call returns:
- `ok=true, requires_approval=true, task_state="awaiting_approval"`
- An `approval_required` event with the approval id
- No filesystem change happens until the user approves.

The agent must treat this as a hard stop: do NOT retry, do NOT proceed with further mutations in the same turn. Surface the approval request to the user and stop.

## Parameters
- `path` (string, required): workspace-relative path to delete.
- `recursive` (boolean, optional, default `false`): when `true`, allows deleting a non-empty directory. Explicit opt-in only.

## Output
- Always: summary "Delete request for X is awaiting approval", citation includes `path`, event contains full approval payload.

## Chaining
- `read_file` / `list_directory` → `delete_path`: confirm what's at the path before requesting deletion.
- `delete_path` (approved, out-of-band) → next turn: the agent sees the change via workspace events, not within the same turn.

## Risks
- **Data loss**: deletion is permanent (no recycle bin unless the OS provides one at its layer). The approval prompt must describe clearly what will be removed.
- **Recursive deletion explosion**: `recursive=true` on a folder can wipe hundreds of files. Always list first.
- **Do not chain multiple deletes without approvals**: if the user asks to delete 5 files, issue 5 approvals and wait; do not assume "approved the first → approved all".
