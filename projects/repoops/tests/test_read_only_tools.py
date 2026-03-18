from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from repoops.read_only_tools import code_search, collect_repo_context, list_files, read_file, read_file_content


class ReadOnlyToolsTest(unittest.TestCase):
    def test_list_files_skips_ignored_directories(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("hello\n", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("ignored\n", encoding="utf-8")
            (root / "runs").mkdir()
            (root / "runs" / "plan.json").write_text("ignored\n", encoding="utf-8")

            files = list_files(root)

            self.assertEqual(files, ["README.md"])

    def test_read_file_returns_preview(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("# Demo\n\nLine 2\nLine 3\n", encoding="utf-8")

            preview = read_file(root, "README.md", max_lines=2)

            self.assertEqual(preview["path"], "README.md")
            self.assertEqual(preview["line_count"], 4)
            self.assertTrue(preview["truncated"])
            self.assertEqual(preview["preview"], "# Demo")

    def test_code_search_returns_line_matches(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "app.py").write_text("approve_write = False\npersist_run_artifacts()\n", encoding="utf-8")

            matches = code_search(root, "approve_write")

            self.assertEqual(matches[0]["path"], "app.py")
            self.assertEqual(matches[0]["line_number"], 1)

    def test_collect_repo_context_combines_tool_outputs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("# Demo Repo\n\nplan.json\n", encoding="utf-8")
            (root / "Makefile").write_text("demo:\n\t@echo ok\n", encoding="utf-8")
            source_dir = root / "projects/repoops/src/repoops"
            source_dir.mkdir(parents=True)
            (source_dir / "cli.py").write_text(
                "def persist_run_artifacts():\n    approve_write = False\n",
                encoding="utf-8",
            )

            context = collect_repo_context(root)

            self.assertEqual(context["tools_used"], ["list_files", "read_file", "code_search"])
            self.assertIn("README.md", context["file_inventory"])
            self.assertEqual(context["key_file_previews"][0]["path"], "README.md")
            self.assertEqual(context["search_results"][0]["pattern"], "plan.json")

    def test_read_file_content_returns_full_text(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "app.py").write_text("line1\nline2\nline3\n", encoding="utf-8")

            content = read_file_content(root, "app.py")
            self.assertEqual(content, "line1\nline2\nline3")

    def test_read_file_content_returns_empty_for_missing_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            content = read_file_content(temp_dir, "nonexistent.py")
            self.assertEqual(content, "")
