"""Provider registry — eliminates duplicated provider routing logic.

Instead of repeating if/elif chains for each provider in every function,
providers register once and are looked up by name.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from langchain_core.runnables import RunnableLambda

from repoops.base_cli_provider import BaseCLIProvider
from repoops.claude_code_cli_provider import ClaudeCodeCLIProvider
from repoops.codex_cli_provider import CodexCLIProvider
from repoops.gemini_cli_provider import GeminiCLIProvider


# ---------------------------------------------------------------------------
# Registry type: maps provider name → factory that creates a BaseCLIProvider
# ---------------------------------------------------------------------------

ProviderFactory = Callable[[str], BaseCLIProvider]

_PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "gemini-cli": lambda repo: GeminiCLIProvider(repo),
    "claude-code-cli": lambda repo: ClaudeCodeCLIProvider(repo),
    "codex-cli": lambda repo: CodexCLIProvider(repo),
}


def list_providers() -> list[str]:
    """Return all registered provider names (including 'deterministic')."""
    return ["deterministic", *sorted(_PROVIDER_FACTORIES)]


def is_llm_provider(name: str) -> bool:
    """True if *name* is a real LLM provider (not deterministic)."""
    return name in _PROVIDER_FACTORIES


def build_llm_runnable(
    provider: str,
    repo: str,
    output_schema: dict[str, Any],
) -> tuple[RunnableLambda, str]:
    """Build a LangChain RunnableLambda that invokes a CLI provider.

    Returns ``(runnable, step_label)`` where *step_label* is a human-readable
    name for the chain step (e.g. ``"GeminiCLIProvider"``).

    Raises ``ValueError`` for unknown provider names.
    """
    factory = _PROVIDER_FACTORIES.get(provider)
    if factory is None:
        raise ValueError(
            f"Unknown LLM provider: {provider!r}. "
            f"Available: {', '.join(list_providers())}"
        )

    cli_provider = factory(repo)
    schema = output_schema

    def _invoke(prompt_value: object) -> str:
        prompt_text = (
            prompt_value.to_string()
            if hasattr(prompt_value, "to_string")
            else str(prompt_value)
        )
        return cli_provider.invoke_json(prompt_text=prompt_text, output_schema=schema)

    step_label = type(cli_provider).__name__
    return RunnableLambda(_invoke), step_label
