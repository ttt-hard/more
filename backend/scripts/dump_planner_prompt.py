"""Dump the rendered planner user prompt for a given workspace + prompt.

Use this to verify P0 deliverables end-to-end without starting the FastAPI
server or invoking a real LLM. The script:

  1. Opens the workspace (bootstraps .more/ if needed).
  2. Creates a throwaway conversation.
  3. Runs the turn-context + skill-resolve pipeline (identical to a real run).
  4. Prints the planner user prompt that would be sent to the LLM, with
     per-section character counts for quick inspection.

Examples:

  python scripts/dump_planner_prompt.py \
    --workspace d:/more/workspace \
    --prompt "帮我整理当前笔记里的缓存架构要点"

  python scripts/dump_planner_prompt.py --workspace ../workspace --section tool_catalog

Pass `--section <name>` to filter the output to a single XML block (e.g.,
`project_context`, `active_skills`, `tool_catalog`).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Make `app.*` imports resolvable when invoked as `python scripts/...`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from app.agent import SingleAgentCoordinator  # noqa: E402
from app.prompts import DEFAULT_PROMPT_REGISTRY, PlannerPromptInput  # noqa: E402
from app.workspace_fs import WorkspaceFS  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", required=True, help="workspace root path")
    parser.add_argument(
        "--prompt",
        default="Help me draft interview questions about caching strategies.",
        help="user prompt to render a turn for",
    )
    parser.add_argument(
        "--current-note-path",
        default=None,
        help="optional workspace-relative current note path",
    )
    parser.add_argument(
        "--section",
        default=None,
        help="print only this XML block (e.g., project_context, active_skills, tool_catalog)",
    )
    return parser.parse_args()


def _extract_section(rendered: str, section: str) -> str:
    pattern = re.compile(rf"<{section}>.*?</{section}>", re.DOTALL)
    match = pattern.search(rendered)
    return match.group(0) if match else f"(section <{section}> not found)"


def _section_lengths(rendered: str) -> list[tuple[str, int]]:
    counts: list[tuple[str, int]] = []
    for match in re.finditer(r"<(?P<name>[a-z_]+)>.*?</(?P=name)>", rendered, re.DOTALL):
        counts.append((match.group("name"), len(match.group(0))))
    return counts


def main() -> int:
    args = parse_args()
    workspace_root = Path(args.workspace).expanduser().resolve()
    if not workspace_root.exists():
        workspace_root.mkdir(parents=True, exist_ok=True)

    fs = WorkspaceFS(workspace_root)
    fs.bootstrap()

    coordinator = SingleAgentCoordinator(fs)
    conversation = coordinator.create_conversation("dump-prompt-demo")
    preflight = coordinator.turn_context_service.prepare_preflight(
        conversation_id=conversation.id
    )
    turn_context = coordinator.turn_context_service.build_turn_context(
        current_note_path=args.current_note_path,
        prompt=args.prompt,
        preflight=preflight,
    )
    augmented = coordinator._augment_turn_context(
        turn_context,
        prompt=args.prompt,
        current_note_path=args.current_note_path,
    )

    prompt_input = PlannerPromptInput(
        prompt=args.prompt,
        memory_context=augmented.memory_context,
        current_note_path=args.current_note_path,
        tool_results=[],
        thread_summary=(augmented.thread_summary or ""),
    )
    rendered = DEFAULT_PROMPT_REGISTRY.planner_user_prompt(prompt_input)

    if args.section:
        print(_extract_section(rendered, args.section))
        return 0

    bar = "=" * 80
    print(bar)
    print(f"WORKSPACE: {workspace_root}")
    print(f"PROMPT: {args.prompt}")
    print(f"CURRENT NOTE: {args.current_note_path or '<none>'}")
    print(bar)
    print("SECTION LENGTHS (chars):")
    for name, length in _section_lengths(rendered):
        print(f"  <{name:28}> {length:>7} chars")
    print(bar)
    print("FULL PLANNER USER PROMPT BELOW")
    print(bar)
    print(rendered)
    print(bar)
    print("END OF PLANNER USER PROMPT")
    print(bar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
