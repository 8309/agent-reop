import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from repoops.cli import build_artifact, persist_run_artifacts


class RepoOpsSmokeTest(unittest.TestCase):
    def test_repoops_payload_defaults_to_write_required(self) -> None:
        with TemporaryDirectory() as temp_dir:
            payload = build_artifact(repo=temp_dir, issue=None, dry_run=True, approve_write=False)
            self.assertEqual(payload["project"], "repoops")
            self.assertEqual(payload["implementation"], "manual")
            self.assertTrue(payload["write_required"])
            self.assertFalse(payload["write_approved"])
            self.assertIn("plan_outline", payload)
            self.assertEqual(payload["repo_context"]["tools_used"], ["list_files", "read_file", "code_search"])

    def test_persist_run_artifacts_writes_plan_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            payload = build_artifact(repo=temp_dir, issue=None, dry_run=True, approve_write=False)
            persisted_payload = persist_run_artifacts(payload)

            run_dir = Path(str(persisted_payload["run_dir"]))
            plan_path = run_dir / "plan.json"

            self.assertTrue(plan_path.exists())
            written_payload = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(written_payload["run_id"], persisted_payload["run_id"])
            self.assertIn(str(plan_path.resolve()), written_payload["persisted_artifacts"])

    def test_build_artifact_collects_repo_context(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("# Demo Repo\n\nplan.json appears here.\n", encoding="utf-8")
            (root / "Makefile").write_text("demo:\n\t@echo ok\n", encoding="utf-8")
            source_dir = root / "projects/repoops/src/repoops"
            source_dir.mkdir(parents=True)
            (source_dir / "cli.py").write_text(
                "def persist_run_artifacts():\n    approve_write = False\n",
                encoding="utf-8",
            )

            payload = build_artifact(repo=temp_dir, issue=None, dry_run=True, approve_write=False)

            repo_context = payload["repo_context"]
            self.assertIn("README.md", repo_context["file_inventory"])
            self.assertEqual(repo_context["key_file_previews"][0]["path"], "README.md")
            self.assertEqual(repo_context["search_results"][0]["pattern"], "plan.json")
