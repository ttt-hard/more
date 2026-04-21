"""Prompt 模板与未来 LangChain / LangGraph 适配预留位。

当前只导出 `PromptTemplateRegistry` + harness 的数据结构给
`LLMService` / `AnswerService` 使用；未来若接入 LangChain / LangGraph
会在此包内补充 adapter，不侵入 agent / services 代码。
"""
from .registry import CompressionPromptInput, AnswerPromptInput, DEFAULT_PROMPT_REGISTRY, PlannerPromptInput, PromptTemplateRegistry

__all__ = ["AnswerPromptInput", "CompressionPromptInput", "DEFAULT_PROMPT_REGISTRY", "PlannerPromptInput", "PromptTemplateRegistry"]
