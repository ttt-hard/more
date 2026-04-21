"""Prompt 打包 harness。

`PlannerPromptInput` / `AnswerPromptInput` 把 coordinator 侧的
`MemoryContext + tool_results + thread_summary + token_budget + ...`
打成 `PromptTemplateRegistry` 能直接消费的结构，供两阶段生成提示词。
"""

from __future__ import annotations

from .registry import CompressionPromptInput, AnswerPromptInput, DEFAULT_PROMPT_REGISTRY, PlannerPromptInput, PromptTemplateRegistry


__all__ = ["AnswerPromptInput", "CompressionPromptInput", "DEFAULT_PROMPT_REGISTRY", "PlannerPromptInput", "PromptTemplateRegistry"]
