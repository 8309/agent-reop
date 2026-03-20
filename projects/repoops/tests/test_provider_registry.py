import unittest

from repoops.provider_registry import build_llm_runnable, is_llm_provider, list_providers


class ProviderRegistryTest(unittest.TestCase):
    def test_list_providers_includes_all(self) -> None:
        providers = list_providers()
        self.assertIn("deterministic", providers)
        self.assertIn("gemini-cli", providers)
        self.assertIn("claude-code-cli", providers)
        self.assertIn("codex-cli", providers)

    def test_is_llm_provider(self) -> None:
        self.assertTrue(is_llm_provider("gemini-cli"))
        self.assertTrue(is_llm_provider("claude-code-cli"))
        self.assertTrue(is_llm_provider("codex-cli"))
        self.assertFalse(is_llm_provider("deterministic"))
        self.assertFalse(is_llm_provider("unknown"))

    def test_build_llm_runnable_unknown_provider(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            build_llm_runnable("nonexistent", "/tmp", {})
        self.assertIn("nonexistent", str(ctx.exception))

    def test_build_llm_runnable_returns_runnable_and_label(self) -> None:
        # Build a runnable for gemini-cli — doesn't invoke the CLI,
        # just verifies the factory returns the right types.
        runnable, label = build_llm_runnable("gemini-cli", "/tmp", {"type": "object"})
        self.assertEqual(label, "GeminiCLIProvider")
        self.assertTrue(callable(runnable.invoke))

    def test_build_llm_runnable_claude_label(self) -> None:
        runnable, label = build_llm_runnable("claude-code-cli", "/tmp", {})
        self.assertEqual(label, "ClaudeCodeCLIProvider")

    def test_build_llm_runnable_codex_label(self) -> None:
        runnable, label = build_llm_runnable("codex-cli", "/tmp", {})
        self.assertEqual(label, "CodexCLIProvider")
