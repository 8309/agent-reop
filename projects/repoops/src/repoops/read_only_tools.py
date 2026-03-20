from __future__ import annotations

import re
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

# Common project files to look for (language-agnostic).
# collect_repo_context will pick whichever exist in the target repo.
WELL_KNOWN_PROJECT_FILES = (
    "README.md",
    "README.rst",
    "Makefile",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "CMakeLists.txt",
)

# Stop-words excluded when extracting search keywords from issue text.
_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "and", "but", "or",
    "nor", "not", "so", "yet", "for", "at", "by", "to", "in", "on", "of",
    "if", "then", "else", "when", "from", "with", "that", "this", "it",
    "its", "into", "also", "each", "all", "any", "both", "such", "than",
    "too", "very", "just", "about", "above", "after", "before", "between",
    "more", "most", "other", "some", "only", "same", "here", "there",
    "what", "which", "who", "whom", "how", "where", "why",
    # domain filler
    "should", "must", "need", "needs", "make", "ensure", "add", "remove",
    "update", "change", "fix", "bug", "feature", "issue", "error",
    "implement", "implementation", "currently", "instead", "return",
    "returns", "raise", "raises", "handle", "test", "tests",
})


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


def detect_key_files(repo_root: Path) -> list[str]:
    """Auto-detect key project files that exist in the target repo."""
    found: list[str] = []
    for name in WELL_KNOWN_PROJECT_FILES:
        if (repo_root / name).exists():
            found.append(name)
    return found


def extract_search_keywords(issue_text: str, max_keywords: int = 6) -> list[str]:
    """Extract meaningful search keywords from issue text.

    Splits on non-alphanumeric/underscore boundaries, filters stop-words and
    short tokens, then returns up to *max_keywords* unique terms ordered by
    frequency (most common first).
    """
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", issue_text)
    freq: dict[str, int] = {}
    for tok in tokens:
        lower = tok.lower()
        if lower in _STOP_WORDS or len(lower) <= 2:
            continue
        freq[lower] = freq.get(lower, 0) + 1
    # Sort by frequency desc, then alphabetically for stability.
    ranked = sorted(freq, key=lambda w: (-freq[w], w))
    return ranked[:max_keywords]


def collect_repo_context(
    repo_root: str | Path,
    issue_text: str | None = None,
) -> dict[str, object]:
    """Scan a target repository and return context for LLM prompts.

    Key files are auto-detected from well-known project file names.
    Search patterns are extracted from *issue_text* keywords when provided,
    falling back to file-inventory-only mode when no issue is given.
    """
    root = _resolve_repo_root(repo_root)

    # Auto-detect key files.
    key_file_previews: list[dict[str, object]] = []
    for relative_path in detect_key_files(root):
        key_file_previews.append(read_file(root, relative_path, max_lines=12))

    # Extract search keywords from issue text.
    search_patterns = extract_search_keywords(issue_text) if issue_text else []
    search_results: list[dict[str, object]] = []
    for pattern in search_patterns:
        matches = code_search(root, pattern, max_results=5)
        if matches:
            search_results.append({"pattern": pattern, "matches": matches})

    return {
        "tools_used": ["list_files", "read_file", "code_search"],
        "file_inventory": list_files(root, limit=20),
        "key_file_previews": key_file_previews,
        "search_results": search_results,
    }
