from __future__ import annotations

from pathlib import Path


IGNORED_DIR_NAMES = {
    ".claude",
    ".codex",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "runs",
}

DEFAULT_KEY_FILES = (
    "README.md",
    "Makefile",
    "projects/repoops/src/repoops/cli.py",
)

DEFAULT_SEARCH_PATTERNS = (
    "plan.json",
    "approve_write",
    "persist_run_artifacts",
)


def _resolve_repo_root(repo_root: str | Path) -> Path:
    return Path(repo_root).resolve()


def _is_ignored(relative_path: Path) -> bool:
    return any(part in IGNORED_DIR_NAMES or part.endswith(".egg-info") for part in relative_path.parts)


def _iter_repo_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(repo_root)
        if _is_ignored(relative_path):
            continue
        files.append(path)
    return files


def list_files(repo_root: str | Path, limit: int = 50) -> list[str]:
    root = _resolve_repo_root(repo_root)
    files: list[str] = []
    for path in _iter_repo_files(root):
        files.append(str(path.relative_to(root)))
        if len(files) >= limit:
            break
    return files


def read_file(repo_root: str | Path, relative_path: str, max_lines: int = 20) -> dict[str, object]:
    root = _resolve_repo_root(repo_root)
    candidate = (root / relative_path).resolve()
    candidate.relative_to(root)

    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(f"File not found: {relative_path}")

    lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
    preview = "\n".join(lines[:max_lines]).rstrip()
    return {
        "path": str(candidate.relative_to(root)),
        "line_count": len(lines),
        "preview": preview,
        "truncated": len(lines) > max_lines,
    }


def read_file_content(repo_root: str | Path, relative_path: str, max_lines: int = 200) -> str:
    """Return the text content of a single file (up to *max_lines*).

    Unlike ``read_file`` which returns a metadata dict, this returns a plain
    string suitable for embedding directly in an LLM prompt.
    """
    root = _resolve_repo_root(repo_root)
    candidate = (root / relative_path).resolve()
    candidate.relative_to(root)  # path-traversal guard

    if not candidate.exists() or not candidate.is_file():
        return ""

    lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[:max_lines])


def code_search(repo_root: str | Path, pattern: str, max_results: int = 10) -> list[dict[str, object]]:
    root = _resolve_repo_root(repo_root)
    matches: list[dict[str, object]] = []
    lowered_pattern = pattern.lower()

    for path in _iter_repo_files(root):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line_number, line_text in enumerate(lines, start=1):
            if lowered_pattern not in line_text.lower():
                continue
            matches.append(
                {
                    "path": str(path.relative_to(root)),
                    "line_number": line_number,
                    "line_text": line_text.strip(),
                }
            )
            if len(matches) >= max_results:
                return matches

    return matches


def collect_repo_context(repo_root: str | Path) -> dict[str, object]:
    root = _resolve_repo_root(repo_root)
    key_file_previews: list[dict[str, object]] = []
    for relative_path in DEFAULT_KEY_FILES:
        if (root / relative_path).exists():
            key_file_previews.append(read_file(root, relative_path, max_lines=12))

    search_results: list[dict[str, object]] = []
    for pattern in DEFAULT_SEARCH_PATTERNS:
        matches = code_search(root, pattern, max_results=5)
        if matches:
            search_results.append({"pattern": pattern, "matches": matches})

    return {
        "tools_used": ["list_files", "read_file", "code_search"],
        "file_inventory": list_files(root, limit=20),
        "key_file_previews": key_file_previews,
        "search_results": search_results,
    }
