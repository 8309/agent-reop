from __future__ import annotations

from difflib import unified_diff
from pathlib import Path
from typing import TypedDict, cast


class PlanStep(TypedDict):
    step_id: str
    description: str
    status: str


class SearchMatch(TypedDict):
    path: str
    line_number: int
    line_text: str


class SearchResult(TypedDict):
    pattern: str
    matches: list[SearchMatch]


class RepoContext(TypedDict, total=False):
    tools_used: list[str]
    file_inventory: list[str]
    search_results: list[SearchResult]


class FileEditProposal(TypedDict):
    path: str
    description: str
    original_snippet: str
    proposed_snippet: str


class WriteProposal(TypedDict):
    summary: str
    edit_proposals: list[FileEditProposal]
    target_relative_path: str
    target_path: str
    proposed_content: str
    patch_diff: str
    pr_draft: str


# ---------------------------------------------------------------------------
# Payload accessors
# ---------------------------------------------------------------------------

def _get_repo_context(payload: dict[str, object]) -> RepoContext:
    value = payload.get("repo_context")
    if isinstance(value, dict):
        return cast(RepoContext, value)
    return {}


def _get_plan_outline(payload: dict[str, object]) -> list[PlanStep]:
    value = payload.get("plan_outline")
    if isinstance(value, list):
        return cast(list[PlanStep], value)
    return []


def _get_acceptance_criteria(payload: dict[str, object]) -> list[str]:
    value = payload.get("acceptance_criteria")
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _get_edit_proposals(payload: dict[str, object]) -> list[FileEditProposal]:
    value = payload.get("edit_proposals")
    if isinstance(value, list):
        return cast(list[FileEditProposal], value)
    return []


def _get_write_proposal(payload: dict[str, object]) -> WriteProposal | None:
    value = payload.get("write_proposal")
    if isinstance(value, dict) and value:
        return cast(WriteProposal, value)
    return None


# ---------------------------------------------------------------------------
# Edit-proposal builder (deterministic)
# ---------------------------------------------------------------------------

def _match_criterion_to_files(
    criterion: str,
    search_results: list[SearchResult],
    file_inventory: list[str],
) -> list[SearchMatch]:
    """Find files related to an acceptance criterion by keyword overlap."""
    words = {w.lower() for w in criterion.split() if len(w) > 3}
    matches: list[SearchMatch] = []
    seen_paths: set[str] = set()

    for entry in search_results:
        pattern_lower = entry["pattern"].lower()
        if any(w in pattern_lower or pattern_lower in w for w in words):
            for match in entry["matches"]:
                if match["path"] not in seen_paths:
                    matches.append(match)
                    seen_paths.add(match["path"])

    if not matches:
        for path in file_inventory:
            path_lower = path.lower()
            if any(w in path_lower for w in words):
                if path not in seen_paths:
                    matches.append({"path": path, "line_number": 1, "line_text": ""})
                    seen_paths.add(path)

    return matches


def build_edit_proposals(payload: dict[str, object]) -> list[FileEditProposal]:
    """Build issue-specific edit proposals from repo context and acceptance criteria.

    If the payload already contains ``edit_proposals`` (e.g. set by an LLM chain),
    those are returned as-is.
    """
    existing = _get_edit_proposals(payload)
    if existing:
        return existing

    repo_context = _get_repo_context(payload)
    search_results = repo_context.get("search_results", [])
    file_inventory = repo_context.get("file_inventory", [])
    criteria = _get_acceptance_criteria(payload)
    issue_title = str(payload.get("issue_title", "Untitled Issue"))
    issue_summary = str(payload.get("issue_summary", ""))

    proposals: list[FileEditProposal] = []
    seen_paths: set[str] = set()

    for criterion in criteria:
        related = _match_criterion_to_files(criterion, search_results, file_inventory)
        for match in related:
            if match["path"] in seen_paths:
                continue
            seen_paths.add(match["path"])
            original_snippet = match["line_text"].strip() if match["line_text"] else ""
            proposals.append(
                FileEditProposal(
                    path=match["path"],
                    description=f"[{issue_title}] {criterion}",
                    original_snippet=original_snippet,
                    proposed_snippet=f"# TODO({issue_title}): {criterion}",
                )
            )

    if not proposals and file_inventory:
        fallback_path = file_inventory[0]
        proposals.append(
            FileEditProposal(
                path=fallback_path,
                description=f"[{issue_title}] {issue_summary}",
                original_snippet="",
                proposed_snippet=f"# TODO({issue_title}): {issue_summary}",
            )
        )

    return proposals


# ---------------------------------------------------------------------------
# Handoff markdown
# ---------------------------------------------------------------------------

def build_repoops_handoff_markdown(
    payload: dict[str, object],
    edit_proposals: list[FileEditProposal],
) -> str:
    repo_context = _get_repo_context(payload)
    lines = [
        "# RepoOps Handoff",
        "",
        f"Issue: {payload['issue_title']}",
        f"Mode: {payload['mode']}",
        "",
        "## Summary",
        str(payload["issue_summary"]),
        "",
        "## Acceptance Criteria",
    ]

    acceptance_criteria = _get_acceptance_criteria(payload)
    if acceptance_criteria:
        for item in acceptance_criteria:
            lines.append(f"- {item}")
    else:
        lines.append("- No explicit acceptance criteria were provided.")

    lines.extend(["", "## Plan"])
    for step in _get_plan_outline(payload):
        lines.append(f"- {step['step_id']}: {step['description']} ({step['status']})")

    if edit_proposals:
        lines.extend(["", "## Proposed Edits"])
        for proposal in edit_proposals:
            lines.append(f"### `{proposal['path']}`")
            lines.append(f"**{proposal['description']}**")
            if proposal["original_snippet"]:
                lines.extend(["", "Current:", f"```", proposal["original_snippet"], "```"])
            lines.extend(["", "Proposed:", "```", proposal["proposed_snippet"], "```", ""])

    file_inventory = repo_context.get("file_inventory", [])
    if file_inventory:
        lines.extend(["## Repo Context Highlights", "Files seen:"])
        for path in file_inventory[:8]:
            lines.append(f"- {path}")

    search_results = repo_context.get("search_results", [])
    if search_results:
        lines.extend(["", "Search hits:"])
        for entry in search_results[:3]:
            lines.append(f"- Pattern: {entry['pattern']}")
            for match in entry["matches"][:2]:
                lines.append(
                    f"  - {match['path']}:{match['line_number']} -> {match['line_text']}"
                )

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PR draft
# ---------------------------------------------------------------------------

def build_pr_draft(
    payload: dict[str, object],
    edit_proposals: list[FileEditProposal],
) -> str:
    lines = [
        "# PR Draft",
        "",
        f"## {payload.get('issue_title', 'Untitled Issue')}",
        "",
        "## Summary",
    ]

    for proposal in edit_proposals:
        lines.append(f"- `{proposal['path']}`: {proposal['description']}")
    if not edit_proposals:
        lines.append("- No file edits proposed.")

    lines.extend([
        "",
        "## Validation",
        "- `make test`",
        "- Review the generated `plan.json`, `patch.diff`, and `pr_draft.md` artifacts",
        "",
        "## Notes",
        f"- Current write status: `{payload.get('write_status', 'unknown')}`",
        "- Repo writes remain blocked unless `--approve-write` is provided on a live run.",
        "",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Patch diff
# ---------------------------------------------------------------------------

def _build_patch_diff_for_edits(edit_proposals: list[FileEditProposal]) -> str:
    if not edit_proposals:
        return "No edits proposed.\n"

    parts: list[str] = []
    for proposal in edit_proposals:
        original_lines = (proposal["original_snippet"] + "\n").splitlines(keepends=True) if proposal["original_snippet"] else []
        proposed_lines = (proposal["proposed_snippet"] + "\n").splitlines(keepends=True)
        diff = "".join(unified_diff(
            original_lines,
            proposed_lines,
            fromfile=f"a/{proposal['path']}",
            tofile=f"b/{proposal['path']}",
        ))
        if diff:
            parts.append(diff)
        else:
            parts.append(f"# No diff for {proposal['path']} (new content)\n")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Prepare / apply
# ---------------------------------------------------------------------------

DEFAULT_WRITE_TARGET = "repoops-output/repoops-plan.md"


def prepare_write_action(payload: dict[str, object]) -> dict[str, object]:
    repo_root = Path(str(payload["repo"]))
    target_relative_path = DEFAULT_WRITE_TARGET
    target_path = (repo_root / target_relative_path).resolve()

    payload["applied_writes"] = []
    if payload["mode"] == "dry-run":
        payload["write_status"] = "dry-run-proposed"
    elif payload["write_approved"]:
        payload["write_status"] = "approved-pending-apply"
    else:
        payload["write_status"] = "blocked-awaiting-approval"

    edit_proposals = build_edit_proposals(payload)
    payload["edit_proposals"] = [dict(p) for p in edit_proposals]

    proposed_content = build_repoops_handoff_markdown(payload, edit_proposals)
    payload["write_proposal"] = {
        "summary": f"Issue-specific edits for: {payload.get('issue_title', 'Untitled Issue')}",
        "edit_proposals": [dict(p) for p in edit_proposals],
        "target_relative_path": target_relative_path,
        "target_path": str(target_path),
        "proposed_content": proposed_content,
        "patch_diff": _build_patch_diff_for_edits(edit_proposals),
        "pr_draft": build_pr_draft(payload, edit_proposals),
    }
    return payload


def apply_write_action(payload: dict[str, object]) -> dict[str, object]:
    if payload["mode"] == "dry-run":
        return payload

    if not payload["write_approved"]:
        payload["write_status"] = "blocked-awaiting-approval"
        return payload

    proposal = _get_write_proposal(payload)
    if not proposal:
        raise RuntimeError("Write proposal must be prepared before applying write actions")

    target_path = Path(proposal["target_path"])
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(proposal["proposed_content"], encoding="utf-8")

    payload["applied_writes"] = [str(target_path.resolve())]
    payload["write_status"] = "applied"
    return payload
