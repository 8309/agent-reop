import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from repoops.cli import build_artifact, persist_run_artifacts
from repoops.write_actions import (
    apply_edit_to_file,
    apply_write_action,
    build_edit_proposals,
    prepare_write_action,
)


SAMPLE_ISSUE = """\
# Sample Bug

The CLI should produce a structured plan before attempting any write action.

Acceptance criteria:
- Generate a machine-readable plan
- Keep write actions behind an approval gate
- Save artifacts for later review
"""


def _make_payload_with_context(temp_dir: str) -> dict[str, object]:
    """Build a payload against a temp repo that has enough files to trigger edit proposals."""
    root = Path(temp_dir)
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    (root / "cli.py").write_text(
        "def persist_run_artifacts():\n    approve_write = False\n",
        encoding="utf-8",
    )
    issue_path = root / "issue.md"
    issue_path.write_text(SAMPLE_ISSUE, encoding="utf-8")
    return build_artifact(repo=temp_dir, issue=str(issue_path), dry_run=True, approve_write=False)


class WriteActionsTest(unittest.TestCase):
    def test_prepare_write_action_adds_proposal(self) -> None:
        with TemporaryDirectory() as temp_dir:
            payload = build_artifact(repo=temp_dir, issue=None, dry_run=True, approve_write=False)
            payload = prepare_write_action(payload)

            self.assertEqual(payload["write_status"], "dry-run-proposed")
            self.assertEqual(
                payload["write_proposal"]["target_relative_path"],
                "repoops-output/repoops-plan.md",
            )
            self.assertIn("RepoOps Handoff", payload["write_proposal"]["proposed_content"])
            self.assertIn("PR Draft", payload["write_proposal"]["pr_draft"])

    def test_apply_write_action_blocks_without_approval(self) -> None:
        with TemporaryDirectory() as temp_dir:
            payload = build_artifact(repo=temp_dir, issue=None, dry_run=False, approve_write=False)
            payload = prepare_write_action(payload)
            payload = apply_write_action(payload)

            self.assertEqual(payload["write_status"], "blocked-awaiting-approval")
            self.assertEqual(payload["applied_writes"], [])
            self.assertFalse((Path(temp_dir) / "repoops-output/repoops-plan.md").exists())

    def test_apply_write_action_writes_target_when_approved(self) -> None:
        with TemporaryDirectory() as temp_dir:
            payload = build_artifact(repo=temp_dir, issue=None, dry_run=False, approve_write=True)
            payload = prepare_write_action(payload)
            payload = apply_write_action(payload)

            target_path = Path(temp_dir) / "repoops-output/repoops-plan.md"
            self.assertEqual(payload["write_status"], "applied")
            self.assertEqual(payload["applied_writes"], [str(target_path.resolve())])
            self.assertTrue(target_path.exists())
            self.assertIn("RepoOps Handoff", target_path.read_text(encoding="utf-8"))

    def test_persist_run_artifacts_writes_patch_and_pr_draft(self) -> None:
        with TemporaryDirectory() as temp_dir:
            payload = build_artifact(repo=temp_dir, issue=None, dry_run=True, approve_write=False)
            payload = prepare_write_action(payload)
            payload = persist_run_artifacts(payload)

            run_dir = Path(str(payload["run_dir"]))
            patch_path = run_dir / "patch.diff"
            pr_draft_path = run_dir / "pr_draft.md"
            plan_path = run_dir / "plan.json"

            self.assertTrue(plan_path.exists())
            self.assertTrue(patch_path.exists())
            self.assertTrue(pr_draft_path.exists())

            written_payload = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertIn(str(patch_path.resolve()), written_payload["persisted_artifacts"])
            self.assertIn(str(pr_draft_path.resolve()), written_payload["persisted_artifacts"])

    def test_build_edit_proposals_generates_issue_specific_proposals(self) -> None:
        with TemporaryDirectory() as temp_dir:
            payload = _make_payload_with_context(temp_dir)
            proposals = build_edit_proposals(payload)

            self.assertGreater(len(proposals), 0)
            paths = [p["path"] for p in proposals]
            self.assertTrue(any("cli.py" in p for p in paths))

            for proposal in proposals:
                self.assertIn("path", proposal)
                self.assertIn("description", proposal)
                self.assertIn("original_snippet", proposal)
                self.assertIn("proposed_snippet", proposal)

    def test_edit_proposals_appear_in_handoff_and_pr_draft(self) -> None:
        with TemporaryDirectory() as temp_dir:
            payload = _make_payload_with_context(temp_dir)
            payload = prepare_write_action(payload)

            self.assertIn("edit_proposals", payload)
            self.assertGreater(len(payload["edit_proposals"]), 0)

            proposal = payload["write_proposal"]
            self.assertIn("Proposed Edits", proposal["proposed_content"])
            self.assertIn("cli.py", proposal["pr_draft"])
            self.assertIn("edit_proposals", proposal)

    def test_existing_edit_proposals_are_preserved(self) -> None:
        with TemporaryDirectory() as temp_dir:
            payload = build_artifact(repo=temp_dir, issue=None, dry_run=True, approve_write=False)
            payload["edit_proposals"] = [
                {
                    "path": "custom/file.py",
                    "description": "LLM-generated edit",
                    "original_snippet": "old code",
                    "proposed_snippet": "new code",
                }
            ]
            proposals = build_edit_proposals(payload)

            self.assertEqual(len(proposals), 1)
            self.assertEqual(proposals[0]["path"], "custom/file.py")

    def test_patch_diff_reflects_edit_proposals(self) -> None:
        with TemporaryDirectory() as temp_dir:
            payload = _make_payload_with_context(temp_dir)
            payload = prepare_write_action(payload)

            patch_diff = payload["write_proposal"]["patch_diff"]
            self.assertIn("---", patch_diff)
            self.assertIn("+++", patch_diff)

    def test_apply_edit_to_file_replaces_snippet(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "app.py"
            target.write_text("def greet():\n    return 'hello'\n", encoding="utf-8")

            proposal = {
                "path": "app.py",
                "description": "update greeting",
                "original_snippet": "return 'hello'",
                "proposed_snippet": "return 'hello world'",
            }
            result = apply_edit_to_file(temp_dir, proposal)

            self.assertTrue(result.success)
            self.assertIn("return 'hello world'", target.read_text(encoding="utf-8"))

    def test_apply_edit_to_file_returns_failure_when_snippet_not_found(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "app.py").write_text("pass\n", encoding="utf-8")

            proposal = {
                "path": "app.py",
                "description": "no match",
                "original_snippet": "nonexistent code",
                "proposed_snippet": "replacement",
            }
            result = apply_edit_to_file(temp_dir, proposal)
            self.assertFalse(result.success)
            self.assertEqual(result.reason, "snippet not found in file")
            self.assertIn("not found in file", result.detail)

    def test_apply_edit_to_file_returns_failure_for_missing_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            proposal = {
                "path": "missing.py",
                "description": "no file",
                "original_snippet": "x",
                "proposed_snippet": "y",
            }
            result = apply_edit_to_file(temp_dir, proposal)
            self.assertFalse(result.success)
            self.assertEqual(result.reason, "file not found")

    def test_apply_edit_diagnoses_indentation_mismatch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            # File has "    my_unique_var = 1", snippet omits leading spaces.
            # "my_unique_var" won't appear without indentation anywhere else.
            (root / "app.py").write_text("    my_unique_var = 1\n", encoding="utf-8")

            proposal = {
                "path": "app.py",
                "description": "indent issue",
                "original_snippet": "my_unique_var = 1\nsome_other_line",
                "proposed_snippet": "my_unique_var = 2",
            }
            result = apply_edit_to_file(temp_dir, proposal)
            self.assertFalse(result.success)
            # Diagnosis should mention the mismatch at line 2
            self.assertIn("snippet not found", result.reason)

    def test_apply_edit_diagnoses_non_contiguous_lines(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "app.py").write_text("x = 1\nz = 3\ny = 2\n", encoding="utf-8")

            proposal = {
                "path": "app.py",
                "description": "reorder",
                "original_snippet": "x = 1\ny = 2",
                "proposed_snippet": "x = 1\ny = 2",
            }
            result = apply_edit_to_file(temp_dir, proposal)
            self.assertFalse(result.success)
            self.assertIn("contiguous", result.detail)

    def test_apply_write_action_applies_code_edits_when_approved(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "src" / "main.py"
            target.parent.mkdir(parents=True)
            target.write_text("x = 1\ny = 2\n", encoding="utf-8")

            payload = build_artifact(repo=temp_dir, issue=None, dry_run=False, approve_write=True)
            # Inject a concrete edit proposal that matches the file content.
            payload["edit_proposals"] = [
                {
                    "path": "src/main.py",
                    "description": "change x",
                    "original_snippet": "x = 1",
                    "proposed_snippet": "x = 42",
                }
            ]
            payload = prepare_write_action(payload)
            payload = apply_write_action(payload)

            self.assertEqual(payload["write_status"], "applied")
            self.assertIn(str(target.resolve()), payload["applied_writes"])
            self.assertIn("x = 42", target.read_text(encoding="utf-8"))
