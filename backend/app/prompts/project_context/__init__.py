"""项目上下文子模块。

`loader.load_project_context` 沿逻辑 cwd（优先 `current_note_path` 的父
目录，否则 workspace root）向上查找 `AGENTS.md / CLAUDE.md / CONTEXT.md`
中第一个存在的项目规范文件，作为 `<project_context>` XML 块注入到
planner / answer prompt。效果等价于 claude-code / opencode 的 AGENTS.md
加载机制。
"""

from .loader import PROJECT_CONTEXT_FILENAMES, ProjectContextEntry, load_project_context

__all__ = ["PROJECT_CONTEXT_FILENAMES", "ProjectContextEntry", "load_project_context"]
