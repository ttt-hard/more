"""用户偏好与 LLM 设置存储。

`PreferenceStore` 管理 `.more/preferences.yaml`（语言 / 回答风格 / 默认
笔记目录 / 主题）；`LLMSettingsStore` 管理 `.more/llm_settings.yaml`
（base_url / api_key / model / timeout），两者都是 YAML 格式、都用
`locked_path` 串行化读写。
"""

from __future__ import annotations

from dataclasses import asdict

import yaml

from ..domain import LLMSettings, UserPreference
from ..infrastructure.file_lock import locked_path
from ..workspace_fs import WorkspaceFS


class PreferenceStore:
    def __init__(self, fs: WorkspaceFS) -> None:
        self.fs = fs
        self.preferences_path = self.fs.sidecar_root / "preferences.yaml"

    def load(self) -> UserPreference:
        if not self.preferences_path.exists():
            return UserPreference()
        with locked_path(self.preferences_path):
            raw = yaml.safe_load(self.preferences_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("preferences.yaml must be a mapping")
        return UserPreference(
            language=str(raw.get("language") or "zh-CN"),
            answer_style=str(raw.get("answer_style") or "concise"),
            default_note_dir=str(raw.get("default_note_dir") or "Notes"),
            theme=str(raw.get("theme") or "system"),
        )

    def save(self, updates: dict[str, str | None]) -> UserPreference:
        with locked_path(self.preferences_path):
            current = asdict(self.load())
            for key, value in updates.items():
                if value is None:
                    continue
                if key not in current:
                    raise ValueError(f"Unknown preference key: {key}")
                current[key] = str(value).strip() or current[key]
            preference = UserPreference(**current)
            self.preferences_path.write_text(
                yaml.safe_dump(asdict(preference), sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
        return preference


class LLMSettingsStore:
    def __init__(self, fs: WorkspaceFS) -> None:
        self.fs = fs
        self.settings_path = self.fs.sidecar_root / "llm_settings.yaml"

    def load(self) -> LLMSettings:
        if not self.settings_path.exists():
            return LLMSettings()
        with locked_path(self.settings_path):
            raw = yaml.safe_load(self.settings_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("llm_settings.yaml must be a mapping")
        raw_fc = raw.get("use_function_calling")
        return LLMSettings(
            base_url=str(raw.get("base_url") or "").strip(),
            api_key=str(raw.get("api_key") or "").strip(),
            model=str(raw.get("model") or "").strip(),
            timeout=float(raw.get("timeout") or 30.0),
            use_function_calling=(bool(raw_fc) if raw_fc is not None else True),
        )

    def save(self, updates: dict[str, str | float | bool | None]) -> LLMSettings:
        with locked_path(self.settings_path):
            current = self.load()
            base_url = updates.get("base_url")
            api_key = updates.get("api_key")
            model = updates.get("model")
            timeout = updates.get("timeout")
            use_function_calling = updates.get("use_function_calling")
            settings = LLMSettings(
                base_url=str(base_url).strip().rstrip("/") if base_url is not None else current.base_url,
                api_key=str(api_key).strip() if api_key is not None else current.api_key,
                model=str(model).strip() if model is not None else current.model,
                timeout=float(timeout) if timeout is not None else current.timeout,
                use_function_calling=bool(use_function_calling) if use_function_calling is not None else current.use_function_calling,
            )
            payload = {
                "base_url": settings.base_url,
                "api_key": settings.api_key,
                "model": settings.model,
                "timeout": settings.timeout,
                "use_function_calling": settings.use_function_calling,
            }
            self.settings_path.write_text(
                yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
        return settings
