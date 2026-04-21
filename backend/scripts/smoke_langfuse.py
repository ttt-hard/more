"""End-to-end smoke test for Langfuse Cloud wiring.

Loads backend/.env, calls `init_langfuse()`, opens a span via the
`@observe` decorator, flushes, and prints what the wrapper reports.
If the keys are good you'll see the span land in cloud.langfuse.com
under Sessions within seconds.

Run:
    python scripts/smoke_langfuse.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def _load_env_file(path: Path) -> None:
    """Tiny `.env` parser so this script has no extra deps.

    We can't use python-dotenv because it isn't in the project's
    runtime deps, and pulling it in just for a smoke test would
    pollute the install surface.
    """
    if not path.is_file():
        print(f"[smoke] .env not found at {path}", file=sys.stderr)
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    backend_root = Path(__file__).resolve().parent.parent
    _load_env_file(backend_root / ".env")

    # Make sure `app.*` imports resolve whether this script is launched
    # from the backend dir or via `python -m scripts.smoke_langfuse`.
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from app.observability_langfuse import (  # noqa: E402
        init_langfuse,
        is_active,
        observe,
        set_turn_session,
    )

    print("[smoke] LANGFUSE_HOST         =", os.environ.get("LANGFUSE_HOST"))
    print("[smoke] LANGFUSE_PUBLIC_KEY?  =", bool(os.environ.get("LANGFUSE_PUBLIC_KEY")))
    print("[smoke] LANGFUSE_SECRET_KEY?  =", bool(os.environ.get("LANGFUSE_SECRET_KEY")))

    activated = init_langfuse()
    print(f"[smoke] init_langfuse() -> {activated}, is_active() -> {is_active()}")
    if not activated:
        print("[smoke] Langfuse NOT active — traces will be no-ops. Check keys.")
        return 1

    @observe(name="smoke.root")
    def root_span() -> str:
        set_turn_session(
            "smoke-session-001",
            metadata={"source": "scripts/smoke_langfuse.py"},
            tags=["smoke"],
        )

        @observe(name="smoke.child.work")
        def do_work(x: int) -> int:
            time.sleep(0.05)
            return x * 2

        @observe(name="smoke.child.tool", as_type="tool")
        def do_tool(action: str, args: dict) -> dict:
            time.sleep(0.02)
            return {"ok": True, "action": action, "args": args}

        total = 0
        for i in range(3):
            total += do_work(i)
        do_tool("note_read", {"path": "fake/path.md"})
        return f"sum={total}"

    result = root_span()
    print(f"[smoke] root_span returned: {result}")

    # Force the background worker to flush buffered spans; without this
    # the process could exit before the HTTPS POST to cloud.langfuse.com
    # leaves the SDK's queue.
    from langfuse import get_client  # type: ignore

    client = get_client()
    client.flush()
    print("[smoke] flushed. Open https://cloud.langfuse.com → Sessions "
          "→ smoke-session-001 within ~10s to confirm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
