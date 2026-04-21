"""工具目录共享的小辅助函数（仅限 app.tools 包内部使用）。

提供 `slugify`（笔记路径自动命名）、`normalize_str_list`（把 tags /
related / target_paths 这类字段统一成去空白的字符串列表，None / 单字符串
都容忍）、`as_optional_str`（把 LLM 给的 JSON 值规整成 "有意义字符串或
None"，空白也算 None）。挪到这里是为了让每个工具子目录的 `__init__.py`
只关心自己的 handler，不重复这些规整代码。
"""

from __future__ import annotations

import re


def slugify(text: str) -> str:
    text = text.strip().casefold()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "untitled-note"


def normalize_str_list(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = ["as_optional_str", "normalize_str_list", "slugify"]
