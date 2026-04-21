"""任务与运行存储。

`TaskStore` 把全工作区所有 turn 的状态分成两份 JSONL：
`.more/tasks/tasks.jsonl`（每行一个 `Task`）和 `.more/tasks/runs.jsonl`
（每行一个 `AgentRun`）。`create_*` 追加新行；`update_*` 读全量改字段
再整文件覆写。`TurnStateService` 在 begin / finalize 时调用它推进状态。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from ..domain import AgentRun, Task, utc_now_iso
from ..infrastructure.file_lock import locked_path
from ..workspace_fs import WorkspaceFS


class TaskStore:
    def __init__(self, fs: WorkspaceFS) -> None:
        self.fs = fs
        self.tasks_root = self.fs.sidecar_root / "tasks"
        self.tasks_root.mkdir(parents=True, exist_ok=True)
        self.tasks_file = self.tasks_root / "tasks.jsonl"
        self.runs_file = self.tasks_root / "runs.jsonl"

    def create_task(self, kind: str, parent_id: str | None = None) -> Task:
        task = Task(
            id=uuid4().hex[:12],
            kind=kind,
            parent_id=parent_id,
            state="pending",
            created_at=utc_now_iso(),
        )
        self._append_jsonl(self.tasks_file, asdict(task))
        return task

    def update_task_state(self, task_id: str, state: str) -> Task:
        with locked_path(self.tasks_file):
            tasks = [asdict(task) for task in self.list_tasks()]
            updated: dict[str, object] | None = None
            for payload in tasks:
                if payload["id"] == task_id:
                    payload["state"] = state
                    updated = payload
                    break
            if updated is None:
                raise FileNotFoundError(f"Task not found: {task_id}")
            self._rewrite_jsonl(self.tasks_file, tasks)
        return Task(**updated)

    def list_tasks(self) -> list[Task]:
        return [Task(**payload) for payload in self._read_jsonl(self.tasks_file)]

    def create_run(self, task_id: str, mode: str) -> AgentRun:
        run = AgentRun(
            id=uuid4().hex[:12],
            task_id=task_id,
            mode=mode,
            status="running",
            created_at=utc_now_iso(),
        )
        self._append_jsonl(self.runs_file, asdict(run))
        return run

    def update_run_status(self, run_id: str, status: str) -> AgentRun:
        with locked_path(self.runs_file):
            runs = [asdict(run) for run in self.list_runs()]
            updated: dict[str, object] | None = None
            for payload in runs:
                if payload["id"] == run_id:
                    payload["status"] = status
                    updated = payload
                    break
            if updated is None:
                raise FileNotFoundError(f"Run not found: {run_id}")
            self._rewrite_jsonl(self.runs_file, runs)
        return AgentRun(**updated)

    def list_runs(self) -> list[AgentRun]:
        return [AgentRun(**payload) for payload in self._read_jsonl(self.runs_file)]

    def _append_jsonl(self, path: Path, payload: dict[str, object]) -> None:
        with locked_path(path):
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _rewrite_jsonl(self, path: Path, payloads: list[dict[str, object]]) -> None:
        rendered = "\n".join(json.dumps(payload, ensure_ascii=False) for payload in payloads)
        with locked_path(path):
            path.write_text(rendered + ("\n" if payloads else ""), encoding="utf-8")

    def _read_jsonl(self, path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        with locked_path(path):
            lines = path.read_text(encoding="utf-8").splitlines()
        payloads: list[dict[str, object]] = []
        for line in lines:
            if not line.strip():
                continue
            payloads.append(json.loads(line))
        return payloads
