from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parent.parent
TEST_DIRS = [
    ROOT / "projects/shared/tests",
    ROOT / "projects/repoops/tests",
]


def main() -> int:
    # Packages are expected to be installed via ``pip install -e``.
    # Fall back to PYTHONPATH / sys.path manipulation only when running
    # outside the managed environment.
    try:
        import portfolio_shared  # noqa: F401
    except ImportError:
        for src_dir in [ROOT / "projects/shared/src", ROOT / "projects/repoops/src"]:
            sys.path.insert(0, str(src_dir))

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for test_dir in TEST_DIRS:
        suite.addTests(loader.discover(start_dir=str(test_dir), pattern="test_*.py", top_level_dir=str(test_dir)))

    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
