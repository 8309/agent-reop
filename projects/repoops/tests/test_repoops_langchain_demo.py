import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from repoops.langchain_demo import (
    build_demo_edit_response,
    build_demo_planner_response,
    build_langchain_artifact,
    build_learning_chain,
    collect_edit_context,
)


ISSUE_TEXT = """# Sample Bug

The CLI should produce a structured plan before attempting any write action.

Acceptance criteria:
- Generate a machine-readable plan
- Keep write actions behind an approval gate
- Save artifacts for later review
"""

REPO_CONTEXT = {
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


class RepoOpsLangChainDemoTest(unittest.TestCase):
    def test_build_learning_chain_returns_structured_plan_and_edits(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")
            src = root / "projects/repoops/src/repoops"
            src.mkdir(parents=True)
            (src / "cli.py").write_text("approve_write=False\n", encoding="utf-8")

            prompt_preview, plan, edit_proposals, chain_steps = build_learning_chain(
                repo=temp_dir,
                issue_text=ISSUE_TEXT,
                repo_context=REPO_CONTEXT,
            )
            self.assertIn("RepoOps planning component", prompt_preview)
            self.assertIn("Repository context:", prompt_preview)
            self.assertEqual(plan.issue_title, "Sample Bug")
            self.assertEqual(plan.plan_outline[2].description, "Generate a machine-readable plan")
            self.assertIn("RunnableLambda", chain_steps)
            self.assertGreater(len(edit_proposals), 0)
            self.assertIn("cli.py", edit_proposals[0].path)
            # Deterministic edit proposals should include actual file content
            self.assertIn("approve_write", edit_proposals[0].original_snippet)

    @patch("repoops.langchain_demo.CodexCLIProvider.invoke_json")
    def test_build_learning_chain_supports_codex_cli_provider(self, mock_invoke_json: object) -> None:
        # First call returns plan, second call returns edits
        mock_invoke_json.side_effect = [
            build_demo_planner_response(ISSUE_TEXT),
            build_demo_edit_response(ISSUE_TEXT, REPO_CONTEXT, {}),
        ]

        prompt_preview, plan, edit_proposals, chain_steps = build_learning_chain(
            repo="/tmp/demo",
            issue_text=ISSUE_TEXT,
            repo_context=REPO_CONTEXT,
            provider="codex-cli",
        )

        self.assertIn("RepoOps planning component", prompt_preview)
        self.assertEqual(plan.issue_title, "Sample Bug")
        self.assertIn("CodexCLIProvider", chain_steps)

    @patch("repoops.langchain_demo.ClaudeCodeCLIProvider.invoke_json")
    def test_build_learning_chain_supports_claude_code_cli_provider(self, mock_invoke_json: object) -> None:
        mock_invoke_json.side_effect = [
            build_demo_planner_response(ISSUE_TEXT),
            build_demo_edit_response(ISSUE_TEXT, REPO_CONTEXT, {}),
        ]

        prompt_preview, plan, edit_proposals, chain_steps = build_learning_chain(
            repo="/tmp/demo",
            issue_text=ISSUE_TEXT,
            repo_context=REPO_CONTEXT,
            provider="claude-code-cli",
        )

        self.assertIn("RepoOps planning component", prompt_preview)
        self.assertEqual(plan.issue_title, "Sample Bug")
        self.assertIn("ClaudeCodeCLIProvider", chain_steps)

    @patch("repoops.langchain_demo.GeminiCLIProvider.invoke_json")
    def test_build_learning_chain_supports_gemini_cli_provider(self, mock_invoke_json: object) -> None:
        mock_invoke_json.side_effect = [
            build_demo_planner_response(ISSUE_TEXT),
            build_demo_edit_response(ISSUE_TEXT, REPO_CONTEXT, {}),
        ]

        prompt_preview, plan, edit_proposals, chain_steps = build_learning_chain(
            repo="/tmp/demo",
            issue_text=ISSUE_TEXT,
            repo_context=REPO_CONTEXT,
            provider="gemini-cli",
        )

        self.assertIn("RepoOps planning component", prompt_preview)
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

    def test_collect_edit_context_reads_file_contents(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            src = root / "projects/repoops/src/repoops"
            src.mkdir(parents=True)
            (src / "cli.py").write_text("def main():\n    pass\n", encoding="utf-8")

            repo_context = {
                "search_results": [
                    {
                        "pattern": "main",
                        "matches": [
                            {"path": "projects/repoops/src/repoops/cli.py", "line_number": 1, "line_text": "def main():"}
                        ],
                    }
                ],
            }
            contents = collect_edit_context(temp_dir, repo_context)
            self.assertIn("projects/repoops/src/repoops/cli.py", contents)
            self.assertIn("def main():", contents["projects/repoops/src/repoops/cli.py"])

    def test_build_demo_edit_response_uses_file_contents(self) -> None:
        file_contents = {
            "src/example.py": "def old_function():\n    return 42\n",
        }
        repo_context = {
            "search_results": [
                {
                    "pattern": "plan",
                    "matches": [
                        {"path": "src/example.py", "line_number": 1, "line_text": "def old_function():"}
                    ],
                }
            ],
        }
        result = build_demo_edit_response(ISSUE_TEXT, repo_context, file_contents)
        import json
        parsed = json.loads(result)
        self.assertGreater(len(parsed["edit_proposals"]), 0)
        # Should use full file content, not just the one-line search match
        self.assertIn("return 42", parsed["edit_proposals"][0]["original_snippet"])
