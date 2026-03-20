from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from repoops.read_only_tools import (
    code_search,
    collect_repo_context,
    detect_key_files,
    extract_search_keywords,
    list_files,
    read_file,
    read_file_content,
)


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
            (root / "README.md").write_text("# Demo Repo\n", encoding="utf-8")
            (root / "Makefile").write_text("test:\n\t@echo ok\n", encoding="utf-8")
            (root / "app.py").write_text("def divide(a, b):\n    return a / b\n", encoding="utf-8")

            context = collect_repo_context(
                root,
                issue_text="Fix the divide function to handle zero division",
            )

            self.assertEqual(context["tools_used"], ["list_files", "read_file", "code_search"])
            self.assertIn("README.md", context["file_inventory"])
            # Auto-detected key files
            key_paths = [p["path"] for p in context["key_file_previews"]]
            self.assertIn("README.md", key_paths)
            self.assertIn("Makefile", key_paths)
            # Issue-derived search found "divide" in app.py
            patterns = [r["pattern"] for r in context["search_results"]]
            self.assertIn("divide", patterns)

    def test_collect_repo_context_without_issue(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("# Hello\n", encoding="utf-8")

            context = collect_repo_context(root)

            self.assertEqual(context["search_results"], [])
            self.assertIn("README.md", context["file_inventory"])

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

    def test_detect_key_files_finds_existing_project_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("# hi\n", encoding="utf-8")
            (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

            found = detect_key_files(root)

            self.assertIn("README.md", found)
            self.assertIn("pyproject.toml", found)
            # Files that don't exist should not appear.
            self.assertNotIn("Cargo.toml", found)

    def test_detect_key_files_empty_repo(self) -> None:
        with TemporaryDirectory() as temp_dir:
            self.assertEqual(detect_key_files(Path(temp_dir)), [])

    def test_extract_search_keywords_filters_stop_words(self) -> None:
        text = "Fix the divide function to handle zero division"
        keywords = extract_search_keywords(text)

        self.assertIn("divide", keywords)
        self.assertIn("zero", keywords)
        self.assertIn("division", keywords)
        # Stop words should be excluded
        self.assertNotIn("the", keywords)
        self.assertNotIn("fix", keywords)

    def test_extract_search_keywords_respects_max(self) -> None:
        text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        keywords = extract_search_keywords(text, max_keywords=3)
        self.assertEqual(len(keywords), 3)

    def test_extract_search_keywords_empty_input(self) -> None:
        self.assertEqual(extract_search_keywords(""), [])

    def test_extract_search_keywords_ranks_by_frequency(self) -> None:
        text = "divide divide divide zero zero function"
        keywords = extract_search_keywords(text)
        # "divide" appears 3×, "zero" 2×, "function" 1× — but "function" is a stop word
        self.assertEqual(keywords[0], "divide")
        self.assertEqual(keywords[1], "zero")
