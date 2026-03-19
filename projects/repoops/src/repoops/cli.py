from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from portfolio_shared.repoops_contracts import build_repoops_run
from repoops.read_only_tools import collect_repo_context
from repoops.write_actions import apply_write_action, prepare_write_action


DEFAULT_VALIDATION_COMMAND = ["make", "test"]


def load_issue_text(issue: str | None) -> str:
    if issue is None:
        return "# Untitled Issue\n\nNo issue text provided."
    return Path(issue).read_text(encoding="utf-8")


def build_artifact(repo: str, issue: str | None, dry_run: bool, approve_write: bool) -> dict[str, object]:
    issue_text = load_issue_text(issue)
    return build_repoops_run(
        implementation="manual",
        repo=repo,
        issue=issue,
        issue_text=issue_text,
        dry_run=dry_run,
        approve_write=approve_write,
        repo_context=collect_repo_context(repo),
    )


def run_validation(
    payload: dict[str, object],
    command: list[str] | None = None,
    timeout: int = 120,
) -> dict[str, object]:
    """Run a validation command and store the result in the payload.

    The test report is stored under ``payload["test_report"]`` with fields:
    command, exit_code, passed, stdout (truncated), stderr (truncated),
    and duration_seconds.
    """
    cmd = command or DEFAULT_VALIDATION_COMMAND
    repo = str(payload.get("repo", "."))
    start = time.monotonic()

    try:
        completed = subprocess.run(
            cmd,
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        duration = round(time.monotonic() - start, 2)
        payload["test_report"] = {
            "command": cmd,
            "exit_code": completed.returncode,
            "passed": completed.returncode == 0,
            "stdout": completed.stdout[-2000:] if completed.stdout else "",
            "stderr": completed.stderr[-2000:] if completed.stderr else "",
            "duration_seconds": duration,
        }
    except FileNotFoundError:
        duration = round(time.monotonic() - start, 2)
        payload["test_report"] = {
            "command": cmd,
            "exit_code": -1,
            "passed": False,
            "stdout": "",
            "stderr": f"Command not found: {cmd[0]}",
            "duration_seconds": duration,
        }
    except subprocess.TimeoutExpired:
        duration = round(time.monotonic() - start, 2)
        payload["test_report"] = {
            "command": cmd,
            "exit_code": -1,
            "passed": False,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "duration_seconds": duration,
        }

    return payload


def persist_run_artifacts(payload: dict[str, object]) -> dict[str, object]:
    run_dir = Path(str(payload["run_dir"]))
    run_dir.mkdir(parents=True, exist_ok=True)

    proposal = payload.get("write_proposal", {})
    artifact_contents = {
        "plan.json": json.dumps(payload, indent=2) + "\n",
    }
    if proposal:
        artifact_contents["patch.diff"] = str(proposal.get("patch_diff", ""))
        artifact_contents["pr_draft.md"] = str(proposal.get("pr_draft", ""))

    test_report = payload.get("test_report")
    if test_report:
        artifact_contents["test_report.json"] = json.dumps(test_report, indent=2) + "\n"

    persisted_artifacts = list(payload.get("persisted_artifacts", []))
    for artifact_name in artifact_contents:
        artifact_path = (run_dir / artifact_name).resolve()
        artifact_path_str = str(artifact_path)
        if artifact_path_str not in persisted_artifacts:
            persisted_artifacts.append(artifact_path_str)
    payload["persisted_artifacts"] = persisted_artifacts

    artifact_contents["plan.json"] = json.dumps(payload, indent=2) + "\n"
    for artifact_name, content in artifact_contents.items():
        (run_dir / artifact_name).write_text(content, encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RepoOps placeholder CLI")
    parser.add_argument("--repo", required=True, help="Path to the target repository")
    parser.add_argument("--issue", help="Path to the issue description")
    parser.add_argument("--dry-run", action="store_true", help="Do not perform any writes")
    parser.add_argument(
        "--approve-write",
        action="store_true",
        help="Allow write actions after explicit approval",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_path = Path(args.repo)
    if not repo_path.exists():
        print(f"Repository path does not exist: {repo_path}", file=sys.stderr)
        return 1

    if args.issue and not Path(args.issue).exists():
        print(f"Issue file does not exist: {args.issue}", file=sys.stderr)
        return 1

    payload = build_artifact(
        repo=str(repo_path.resolve()),
        issue=str(Path(args.issue).resolve()) if args.issue else None,
        dry_run=args.dry_run,
        approve_write=args.approve_write,
    )
    payload = prepare_write_action(payload)
    payload = apply_write_action(payload)
    payload = run_validation(payload)
    # Keep file writes at the CLI boundary so the shared payload builder stays side-effect free.
    payload = persist_run_artifacts(payload)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
