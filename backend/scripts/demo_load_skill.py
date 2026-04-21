"""演示 `load_skill` tool 的实际调用（绕过 LLM，直接在 Python 里手动构造 ToolContext）。

展示 planner 决定激活某个 skill 后、通过 `load_skill(skill_id=...)`
拿到的完整 SKILL.md 正文内容，以及返回给 LLM 的 `summary` 样貌。

Usage:
    python scripts/demo_load_skill.py --workspace ../workspace --skill-id drafting
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from app.ingest import IngestService  # noqa: E402
from app.notes import NoteService  # noqa: E402
from app.search import SearchService  # noqa: E402
from app.services.memory import MemoryService  # noqa: E402
from app.stores.approvals import ApprovalStore  # noqa: E402
from app.tools.base import ToolContext  # noqa: E402
from app.tools.load_skill import load_skill  # noqa: E402
from app.workspace_fs import WorkspaceFS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--skill-id", default="drafting")
    args = parser.parse_args()

    fs = WorkspaceFS(Path(args.workspace).expanduser().resolve())
    fs.bootstrap()
    notes = NoteService(fs)
    context = ToolContext(
        fs=fs,
        note_service=notes,
        search_service=SearchService(fs, note_service=notes),
        ingest_service=IngestService(fs, note_service=notes),
        memory_service=MemoryService(fs),
        approval_store=ApprovalStore(fs),
        prompt="",
        current_note_path=None,
        default_note_dir="Inbox",
    )

    result = load_skill({"skill_id": args.skill_id}, context)
    bar = "=" * 80
    print(bar)
    print(f"load_skill(skill_id='{args.skill_id}')")
    print(bar)
    print(f"ok         : {result.ok}")
    print(f"tool       : {result.tool}")
    print(f"error      : {result.error}")
    print(f"citations  : {result.citations}")
    print(bar)
    print("SUMMARY (what the LLM sees as tool output):")
    print(bar)
    print(result.summary)
    print(bar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
