from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class RepoOpsIssue:
    title: str
    summary: str
    acceptance_criteria: list[str]


def parse_issue_markdown(text: str) -> RepoOpsIssue:
    lines = [line.rstrip() for line in text.splitlines()]

    title = "Untitled Issue"
    summary = ""
    acceptance_criteria: list[str] = []
    in_acceptance_section = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if in_acceptance_section:
                in_acceptance_section = False
            continue

        if line.startswith("# "):
            title = line[2:].strip() or title
            continue

        lowered = line.lower()
        if lowered.startswith("acceptance criteria"):
            in_acceptance_section = True
            continue

        if in_acceptance_section and line.startswith("- "):
            acceptance_criteria.append(line[2:].strip())
            continue

        if not summary and not line.startswith("- "):
            summary = line

    if not summary:
        summary = "No summary was provided in the issue body."

    return RepoOpsIssue(
        title=title,
        summary=summary,
        acceptance_criteria=acceptance_criteria,
    )


def build_plan_outline(acceptance_criteria: list[str]) -> list[dict[str, str]]:
    base_steps = [
        "Inspect issue scope and current repository state",
        "Draft a minimal plan before touching write actions",
    ]
    dynamic_steps = acceptance_criteria or [
        "Clarify missing acceptance criteria",
        "Prepare a safe dry-run artifact set",
    ]
    closing_steps = [
        "Run or capture validation output",
        "Prepare a concise PR summary",
    ]

    descriptions = base_steps + dynamic_steps + closing_steps
    plan: list[dict[str, str]] = []
    for index, description in enumerate(descriptions, start=1):
        plan.append(
            {
                "step_id": f"step-{index:02d}",
                "description": description,
                "status": "pending",
            }
        )
    return plan


@dataclass
class RepoOpsRun:
    project: str
    implementation: str
    run_id: str
    run_dir: str
    repo: str
    issue: str | None
    issue_title: str
    issue_summary: str
    acceptance_criteria: list[str]
    plan_outline: list[dict[str, str]]
    mode: str
    write_required: bool
    write_approved: bool
    repo_context: dict[str, object]
    artifacts: list[str]
    persisted_artifacts: list[str]
    next_steps: list[str]


def build_repoops_run(
    implementation: str,
    repo: str,
    issue: str | None,
    issue_text: str,
    dry_run: bool,
    approve_write: bool,
    repo_context: dict[str, object] | None = None,
) -> dict[str, object]:
    parsed_issue = parse_issue_markdown(issue_text)
    plan_outline = build_plan_outline(parsed_issue.acceptance_criteria)
    # Use a stable timestamp-based run id so artifacts from one execution stay grouped together.
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payload = RepoOpsRun(
        project="repoops",
        implementation=implementation,
        run_id=run_id,
        # Make the output location part of the shared contract so every RepoOps execution path
        # persists artifacts in the same layout.
        run_dir=str((Path(repo) / "runs" / run_id).resolve()),
        repo=repo,
        issue=issue,
        issue_title=parsed_issue.title,
        issue_summary=parsed_issue.summary,
        acceptance_criteria=parsed_issue.acceptance_criteria,
        plan_outline=plan_outline,
        mode="dry-run" if dry_run else "live",
        write_required=True,
        write_approved=approve_write,
        repo_context=repo_context or {},
        artifacts=["plan.json", "patch.diff", "test_report.json", "pr_draft.md"],
        # The contract declares expected artifacts first; the CLI fills this list after it writes
        # real files to disk.
        persisted_artifacts=[],
        next_steps=[
            "Use repo context inside provider-backed planning runs",
            "Add approval-gated write actions",
            "Expand the run artifact set beyond plan.json",
        ],
    )
    return asdict(payload)
