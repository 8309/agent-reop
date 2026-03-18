import unittest

from portfolio_shared.repoops_contracts import build_plan_outline, build_repoops_run, parse_issue_markdown


ISSUE_TEXT = """# Sample Bug

The CLI should produce a structured plan before attempting any write action.

Acceptance criteria:
- Generate a machine-readable plan
- Keep write actions behind an approval gate
- Save artifacts for later review
"""


class RepoOpsContractsTest(unittest.TestCase):
    def test_parse_issue_markdown_extracts_structure(self) -> None:
        issue = parse_issue_markdown(ISSUE_TEXT)
        self.assertEqual(issue.title, "Sample Bug")
        self.assertIn("structured plan", issue.summary)
        self.assertEqual(len(issue.acceptance_criteria), 3)

    def test_build_plan_outline_reflects_acceptance_items(self) -> None:
        plan = build_plan_outline(["First", "Second"])
        self.assertGreaterEqual(len(plan), 4)
        self.assertEqual(plan[2]["description"], "First")

    def test_build_repoops_run_includes_run_directory(self) -> None:
        payload = build_repoops_run(
            implementation="manual",
            repo="/tmp/demo-repo",
            issue="/tmp/demo-repo/example.md",
            issue_text=ISSUE_TEXT,
            dry_run=True,
            approve_write=False,
        )
        self.assertEqual(payload["run_dir"], f"/tmp/demo-repo/runs/{payload['run_id']}")
        self.assertEqual(payload["persisted_artifacts"], [])
        self.assertEqual(payload["repo_context"], {})
