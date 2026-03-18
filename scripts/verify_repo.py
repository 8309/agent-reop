from __future__ import annotations

from pathlib import Path
import sys


REQUIRED_PATHS = [
    "AGENTS.md",
    "README.md",
    "environment.yml",
    "scripts/run_in_mamba.sh",
    "scripts/setup_micromamba.sh",
    "scripts/run_tests.py",
    "scripts/verify_repo.py",
    "projects/shared/README.md",
    "projects/shared/src/portfolio_shared/repoops_contracts.py",
    "projects/repoops/README.md",
    "examples/issues/sample_bug.md",
]


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    missing = [path for path in REQUIRED_PATHS if not (root / path).exists()]

    if missing:
        print("Missing required paths:")
        for path in missing:
            print(f"- {path}")
        return 1

    print("Repository scaffold looks complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
