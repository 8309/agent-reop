import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from repoops.langchain_demo import build_demo_planner_response, build_langchain_artifact, build_learning_chain


ISSUE_TEXT = """# Sample Bug

The CLI should produce a structured plan before attempting any write action.

Acceptance criteria:
- Generate a machine-readable plan
- Keep write actions behind an approval gate
- Save artifacts for later review
"""


class RepoOpsLangChainDemoTest(unittest.TestCase):
    def test_build_learning_chain_returns_structured_plan(self) -> None:
        repo_context = {
            "tools_used": ["list_files", "read_file", "code_search"],
            "file_inventory": ["README.md", "projects/repoops/src/repoops/cli.py"],
            "key_file_previews": [
                {"path": "README.md", "preview": "# Demo", "line_count": 1, "truncated": False}
            ],
            "search_results": [
                {
                    "pattern": "approve_write",
                    "matches": [
                        {
                            "path": "projects/repoops/src/repoops/cli.py",
                            "line_number": 18,
                            "line_text": "approve_write=False",
                        }
                    ],
                }
            ],
        }
        prompt_preview, plan, chain_steps = build_learning_chain(
            repo="/tmp/demo",
            issue_text=ISSUE_TEXT,
            repo_context=repo_context,
        )
        self.assertIn("RepoOps planning component", prompt_preview)
        self.assertIn("Repository context:", prompt_preview)
        self.assertIn("README.md", prompt_preview)
        self.assertEqual(plan.issue_title, "Sample Bug")
        self.assertEqual(plan.plan_outline[2].description, "Generate a machine-readable plan")
        self.assertIn("RunnableLambda", chain_steps)

    @patch("repoops.langchain_demo.CodexCLIProvider.invoke_json")
    def test_build_learning_chain_supports_codex_cli_provider(self, mock_invoke_json: object) -> None:
        mock_invoke_json.return_value = build_demo_planner_response(ISSUE_TEXT)

        prompt_preview, plan, chain_steps = build_learning_chain(
            repo="/tmp/demo",
            issue_text=ISSUE_TEXT,
            repo_context={},
            provider="codex-cli",
        )

        self.assertIn("Use the repository context below", prompt_preview)
        self.assertEqual(plan.issue_title, "Sample Bug")
        self.assertIn("CodexCLIProvider", chain_steps)

    @patch("repoops.langchain_demo.ClaudeCodeCLIProvider.invoke_json")
    def test_build_learning_chain_supports_claude_code_cli_provider(self, mock_invoke_json: object) -> None:
        mock_invoke_json.return_value = build_demo_planner_response(ISSUE_TEXT)

        prompt_preview, plan, chain_steps = build_learning_chain(
            repo="/tmp/demo",
            issue_text=ISSUE_TEXT,
            repo_context={},
            provider="claude-code-cli",
        )

        self.assertIn("Use the repository context below", prompt_preview)
        self.assertEqual(plan.issue_title, "Sample Bug")
        self.assertIn("ClaudeCodeCLIProvider", chain_steps)

    @patch("repoops.langchain_demo.GeminiCLIProvider.invoke_json")
    def test_build_learning_chain_supports_gemini_cli_provider(self, mock_invoke_json: object) -> None:
        mock_invoke_json.return_value = build_demo_planner_response(ISSUE_TEXT)

        prompt_preview, plan, chain_steps = build_learning_chain(
            repo="/tmp/demo",
            issue_text=ISSUE_TEXT,
            repo_context={},
            provider="gemini-cli",
        )

        self.assertIn("Use the repository context below", prompt_preview)
        self.assertEqual(plan.issue_title, "Sample Bug")
        self.assertIn("GeminiCLIProvider", chain_steps)

    def test_build_langchain_artifact_marks_learning_track(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("# Demo Repo\n", encoding="utf-8")
            (root / "Makefile").write_text("demo:\n\t@echo ok\n", encoding="utf-8")
            source_dir = root / "projects/repoops/src/repoops"
            source_dir.mkdir(parents=True)
            (source_dir / "cli.py").write_text("def main():\n    pass\n", encoding="utf-8")

            payload = build_langchain_artifact(
                repo=temp_dir,
                issue=None,
                dry_run=True,
                approve_write=False,
            )

            self.assertEqual(payload["implementation"], "langchain")
            self.assertEqual(payload["learning_track"], "langchain-basics")
            self.assertIn("PromptTemplate", payload["chain_steps"])
            self.assertEqual(payload["provider"], "deterministic")
            self.assertEqual(payload["repo_context"]["tools_used"], ["list_files", "read_file", "code_search"])
            self.assertIn("README.md", payload["repo_context"]["file_inventory"])
