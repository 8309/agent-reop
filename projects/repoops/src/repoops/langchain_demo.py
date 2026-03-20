from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, ConfigDict, Field

from portfolio_shared.repoops_contracts import build_plan_outline, build_repoops_run, parse_issue_markdown
from repoops.cli import detect_validation_command, load_issue_text, persist_run_artifacts, run_validation
from repoops.provider_registry import build_llm_runnable, is_llm_provider, list_providers
from repoops.read_only_tools import collect_repo_context, read_file_content
from repoops.write_actions import (
    apply_write_action,
    backup_repo_files,
    prepare_write_action,
    rollback_repo_files,
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class PlanStepModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(description="Stable identifier for one plan step")
    description: str = Field(description="Human-readable step description")
    status: str = Field(description="Execution status for the step")


class FileEditModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Relative path to the file to edit")
    description: str = Field(description="What change is proposed and why")
    original_snippet: str = Field(description="Existing code snippet for context (may be empty for new files)")
    proposed_snippet: str = Field(description="Proposed replacement code snippet")


class PlanDraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_title: str = Field(description="Short issue title")
    issue_summary: str = Field(description="Single-sentence summary of the issue")
    acceptance_criteria: list[str] = Field(description="Acceptance criteria copied from the issue")
    plan_outline: list[PlanStepModel] = Field(description="Structured execution plan")


class EditPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edit_proposals: list[FileEditModel] = Field(
        description="Proposed file edits with original and replacement code snippets",
    )


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

def _collect_relevant_paths(repo_context: dict[str, object]) -> list[str]:
    """Extract unique file paths from search results."""
    paths: list[str] = []
    seen: set[str] = set()
    for entry in repo_context.get("search_results", []):
        if not isinstance(entry, dict):
            continue
        for match in entry.get("matches", []):
            p = match.get("path", "")
            if p and p not in seen:
                seen.add(p)
                paths.append(p)
    return paths


def collect_edit_context(repo: str, repo_context: dict[str, object]) -> dict[str, str]:
    """Read full content of files found in search results so LLM providers
    have enough context to generate real code edits."""
    file_contents: dict[str, str] = {}
    for rel_path in _collect_relevant_paths(repo_context):
        content = read_file_content(repo, rel_path, max_lines=200)
        if content:
            file_contents[rel_path] = content
    return file_contents


def format_repo_context_for_prompt(repo_context: dict[str, object]) -> str:
    lines = [
        "Tools used: " + ", ".join(repo_context.get("tools_used", [])),
        "",
        "File inventory:",
    ]
    for path in repo_context.get("file_inventory", []):
        lines.append(f"- {path}")

    key_file_previews = repo_context.get("key_file_previews", [])
    if key_file_previews:
        lines.extend(["", "Key file previews:"])
        for preview in key_file_previews:
            lines.append(f"- {preview['path']}:")
            lines.append(str(preview["preview"]))

    search_results = repo_context.get("search_results", [])
    if search_results:
        lines.extend(["", "Search hits:"])
        for entry in search_results:
            lines.append(f"- Pattern: {entry['pattern']}")
            for match in entry["matches"]:
                lines.append(
                    f"  - {match['path']}:{match['line_number']} -> {match['line_text']}"
                )

    return "\n".join(lines).strip()


def format_file_contents_for_prompt(file_contents: dict[str, str]) -> str:
    """Format full file contents for inclusion in the edit prompt."""
    if not file_contents:
        return "No file contents available."
    parts: list[str] = []
    for path, content in file_contents.items():
        parts.append(f"### {path}\n```\n{content}\n```")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Deterministic response builders
# ---------------------------------------------------------------------------

def build_demo_planner_response(issue_text: str) -> str:
    parsed_issue = parse_issue_markdown(issue_text)
    payload = PlanDraftModel(
        issue_title=parsed_issue.title,
        issue_summary=parsed_issue.summary,
        acceptance_criteria=parsed_issue.acceptance_criteria,
        plan_outline=[
            PlanStepModel(**step)
            for step in build_plan_outline(parsed_issue.acceptance_criteria)
        ],
    )
    return payload.model_dump_json(indent=2)


def build_demo_edit_response(
    issue_text: str,
    repo_context: dict[str, object],
    file_contents: dict[str, str],
) -> str:
    """Generate deterministic edit proposals using actual file content."""
    parsed_issue = parse_issue_markdown(issue_text)
    proposals: list[FileEditModel] = []
    search_results = repo_context.get("search_results", [])
    criteria = parsed_issue.acceptance_criteria
    seen: set[str] = set()

    for criterion in criteria:
        words = {w.lower() for w in criterion.split() if len(w) > 3}
        for entry in search_results if isinstance(search_results, list) else []:
            pattern_lower = entry["pattern"].lower()
            if not any(w in pattern_lower or pattern_lower in w for w in words):
                continue
            for match in entry["matches"]:
                path = match["path"]
                if path in seen:
                    continue
                seen.add(path)
                full_content = file_contents.get(path, "")
                original_snippet = full_content if full_content else match.get("line_text", "").strip()
                proposals.append(FileEditModel(
                    path=path,
                    description=f"[{parsed_issue.title}] {criterion}",
                    original_snippet=original_snippet,
                    proposed_snippet=f"# TODO({parsed_issue.title}): {criterion}\n{original_snippet}",
                ))

    return EditPlanModel(edit_proposals=proposals).model_dump_json(indent=2)


# ---------------------------------------------------------------------------
# Planner runnables (step 1: plan outline)
# ---------------------------------------------------------------------------

def build_planner_runnable(
    provider: str,
    repo: str,
    issue_text: str,
) -> tuple[RunnableLambda, list[str]]:
    if provider == "deterministic":
        return (
            RunnableLambda(lambda _prompt_value: build_demo_planner_response(issue_text)),
            ["PromptTemplate", "RunnableLambda", "PydanticOutputParser"],
        )

    runnable, step_label = build_llm_runnable(
        provider, repo, PlanDraftModel.model_json_schema(),
    )
    return runnable, ["PromptTemplate", step_label, "PydanticOutputParser"]


# ---------------------------------------------------------------------------
# Edit runnables (step 2: code-level edit proposals)
# ---------------------------------------------------------------------------

def build_edit_runnable(
    provider: str,
    repo: str,
    issue_text: str,
    repo_context: dict[str, object],
    file_contents: dict[str, str],
) -> tuple[RunnableLambda, list[str]]:
    if provider == "deterministic":
        ctx = repo_context
        fc = file_contents
        return (
            RunnableLambda(
                lambda _pv: build_demo_edit_response(issue_text, repo_context=ctx, file_contents=fc),
            ),
            ["EditPromptTemplate", "RunnableLambda", "PydanticOutputParser"],
        )

    runnable, step_label = build_llm_runnable(
        provider, repo, EditPlanModel.model_json_schema(),
    )
    return runnable, ["EditPromptTemplate", step_label, "PydanticOutputParser"]


# ---------------------------------------------------------------------------
# Two-step chain: plan → edit proposals
# ---------------------------------------------------------------------------

PLAN_PROMPT_TEMPLATE = (
    "You are a RepoOps planning component.\n"
    "Read the issue below and produce a structured execution plan.\n\n"
    "Use the repository context below as supporting evidence. Do not run shell commands.\n\n"
    "Issue:\n{issue_text}\n\n"
    "Repository context:\n{repo_context}\n\n"
    "Return JSON that matches this schema:\n{format_instructions}\n"
)

EDIT_PROMPT_TEMPLATE = (
    "You are a RepoOps code editor.\n"
    "Given the issue, plan, and full file contents below, propose concrete code edits.\n\n"
    "CRITICAL RULES:\n"
    "- `original_snippet` must be copied VERBATIM from the file contents below.\n"
    "  Include type annotations, docstrings, comments, and whitespace exactly as they appear.\n"
    "  The snippet will be used for exact string matching — even one wrong character will fail.\n"
    "- `proposed_snippet` is the replacement code that will substitute the original.\n"
    "- Keep snippets minimal: only include the lines that change plus enough surrounding\n"
    "  context (1-2 lines) to make the match unique within the file.\n"
    "- Do NOT invent code that is not in the file. Copy-paste from the file contents below.\n\n"
    "For each file that needs changing:\n"
    "- Set `path` to the relative file path (must match a path from the file contents section)\n"
    "- Set `description` to a short explanation of the change\n"
    "- Set `original_snippet` to the exact verbatim lines from the file\n"
    "- Set `proposed_snippet` to your replacement code\n\n"
    "Only include files that actually need changes. Write real, working code.\n\n"
    "Issue:\n{issue_text}\n\n"
    "Plan:\n{plan_summary}\n\n"
    "File contents:\n{file_contents}\n\n"
    "Return JSON that matches this schema:\n{format_instructions}\n"
)

RETRY_EDIT_PROMPT_TEMPLATE = (
    "You are a RepoOps code editor. Your previous edit attempt FAILED validation.\n\n"
    "CRITICAL RULES:\n"
    "- `original_snippet` must be copied VERBATIM from the file contents below.\n"
    "  Include type annotations, docstrings, comments, and whitespace exactly as they appear.\n"
    "  The snippet will be used for exact string matching — even one wrong character will fail.\n"
    "- Keep snippets minimal: only include the lines that change plus enough surrounding\n"
    "  context (1-2 lines) to make the match unique within the file.\n"
    "- Do NOT invent code that is not in the file. Copy-paste from the file contents below.\n\n"
    "Issue:\n{issue_text}\n\n"
    "Plan:\n{plan_summary}\n\n"
    "Your previous edit:\n{previous_edit}\n\n"
    "Test output (FAILED):\n{test_output}\n\n"
    "Current file contents (after rollback to original):\n{file_contents}\n\n"
    "Analyze the test failure, fix your edits, and return corrected JSON.\n"
    "Return JSON that matches this schema:\n{format_instructions}\n"
)

MAX_RETRIES = 2


def retry_edit_proposals(
    provider: str,
    repo: str,
    issue_text: str,
    plan_summary: str,
    previous_edit: str,
    test_output: str,
    repo_context: dict[str, object],
    file_contents: dict[str, str],
) -> list[FileEditModel]:
    """Re-invoke the LLM with test failure context to get corrected edits."""
    edit_parser = PydanticOutputParser(pydantic_object=EditPlanModel)
    retry_prompt = PromptTemplate.from_template(RETRY_EDIT_PROMPT_TEMPLATE)
    retry_input = {
        "issue_text": issue_text,
        "plan_summary": plan_summary,
        "previous_edit": previous_edit,
        "test_output": test_output,
        "file_contents": format_file_contents_for_prompt(file_contents),
        "format_instructions": edit_parser.get_format_instructions(),
    }

    edit_model, _ = build_edit_runnable(
        provider=provider, repo=repo, issue_text=issue_text,
        repo_context=repo_context, file_contents=file_contents,
    )
    retry_chain = retry_prompt | edit_model | edit_parser
    edit_plan: EditPlanModel = retry_chain.invoke(retry_input)
    return edit_plan.edit_proposals


def build_learning_chain(
    repo: str,
    issue_text: str,
    repo_context: dict[str, object],
    provider: str = "deterministic",
) -> tuple[str, PlanDraftModel, list[FileEditModel], list[str]]:
    """Two-step chain: (1) generate plan, (2) generate code-level edit proposals.

    Returns (prompt_preview, plan_draft, edit_proposals, chain_steps).
    """
    # --- Step 1: Plan ---
    plan_parser = PydanticOutputParser(pydantic_object=PlanDraftModel)
    plan_prompt = PromptTemplate.from_template(PLAN_PROMPT_TEMPLATE)
    plan_input = {
        "issue_text": issue_text,
        "repo_context": format_repo_context_for_prompt(repo_context),
        "format_instructions": plan_parser.get_format_instructions(),
    }
    prompt_preview = plan_prompt.invoke(plan_input).to_string()

    planner_model, chain_steps = build_planner_runnable(
        provider=provider, repo=repo, issue_text=issue_text,
    )
    plan_chain = plan_prompt | planner_model | plan_parser
    plan_draft: PlanDraftModel = plan_chain.invoke(plan_input)

    # --- Step 2: Edit proposals ---
    file_contents = collect_edit_context(repo, repo_context)
    plan_summary = "\n".join(
        f"- {step.step_id}: {step.description}" for step in plan_draft.plan_outline
    )

    edit_parser = PydanticOutputParser(pydantic_object=EditPlanModel)
    edit_prompt = PromptTemplate.from_template(EDIT_PROMPT_TEMPLATE)
    edit_input = {
        "issue_text": issue_text,
        "plan_summary": plan_summary,
        "file_contents": format_file_contents_for_prompt(file_contents),
        "format_instructions": edit_parser.get_format_instructions(),
    }

    edit_model, edit_steps = build_edit_runnable(
        provider=provider, repo=repo, issue_text=issue_text,
        repo_context=repo_context, file_contents=file_contents,
    )
    edit_chain = edit_prompt | edit_model | edit_parser
    edit_plan: EditPlanModel = edit_chain.invoke(edit_input)

    all_steps = chain_steps + edit_steps
    return prompt_preview, plan_draft, edit_plan.edit_proposals, all_steps


def build_langchain_artifact(
    repo: str,
    issue: str | None,
    dry_run: bool,
    approve_write: bool,
    provider: str = "deterministic",
) -> dict[str, object]:
    issue_text = load_issue_text(issue)
    repo_context = collect_repo_context(repo, issue_text=issue_text)
    prompt_preview, plan_draft, edit_proposals, chain_steps = build_learning_chain(
        repo=repo,
        issue_text=issue_text,
        repo_context=repo_context,
        provider=provider,
    )

    payload = build_repoops_run(
        implementation="langchain",
        repo=repo,
        issue=issue,
        issue_text=issue_text,
        dry_run=dry_run,
        approve_write=approve_write,
    )
    payload["repo_context"] = repo_context
    payload["issue_title"] = plan_draft.issue_title
    payload["issue_summary"] = plan_draft.issue_summary
    payload["acceptance_criteria"] = plan_draft.acceptance_criteria
    payload["plan_outline"] = [step.model_dump() for step in plan_draft.plan_outline]
    if edit_proposals:
        payload["edit_proposals"] = [ep.model_dump() for ep in edit_proposals]
    payload["learning_track"] = "langchain-basics"
    payload["provider"] = provider
    payload["chain_steps"] = chain_steps
    payload["prompt_preview"] = prompt_preview
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RepoOps LangChain learning demo")
    parser.add_argument("--repo", required=True, help="Path to the target repository")
    parser.add_argument("--issue", help="Path to the issue description")
    parser.add_argument("--dry-run", action="store_true", help="Do not perform any writes")
    parser.add_argument(
        "--provider",
        choices=list_providers(),
        default="deterministic",
        help="Planner backend used inside the LangChain learning demo",
    )
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

    repo = str(repo_path.resolve())
    issue = str(Path(args.issue).resolve()) if args.issue else None

    payload = build_langchain_artifact(
        repo=repo,
        issue=issue,
        dry_run=args.dry_run,
        approve_write=args.approve_write,
        provider=args.provider,
    )
    payload = prepare_write_action(payload)

    # --- Closed-loop: apply → validate → retry on failure ---
    can_retry = (
        is_llm_provider(args.provider)
        and not args.dry_run
        and args.approve_write
    )
    repo_context = payload.get("repo_context", {})
    issue_text = str(payload.get("issue_text", ""))
    plan_summary = "\n".join(
        f"- {s['step_id']}: {s['description']}"
        for s in payload.get("plan_outline", [])
        if isinstance(s, dict)
    )
    validation_cmd = detect_validation_command(repo)
    retry_history: list[dict[str, object]] = []

    for attempt in range(1 + MAX_RETRIES):
        # Backup files before applying edits so we can rollback.
        edit_proposals = payload.get("edit_proposals", [])
        backups = backup_repo_files(repo, edit_proposals) if can_retry else {}

        payload = apply_write_action(payload)
        payload = run_validation(payload, command=validation_cmd)

        test_report = payload.get("test_report", {})
        passed = test_report.get("passed", False) if isinstance(test_report, dict) else False

        if passed or not can_retry or attempt == MAX_RETRIES:
            break

        # --- Retry: rollback, re-generate edits, update payload ---
        print(
            f"[retry {attempt + 1}/{MAX_RETRIES}] Validation failed, "
            f"rolling back and asking LLM for corrected edits...",
            file=sys.stderr,
        )
        rollback_repo_files(repo, backups)

        previous_edit = json.dumps(edit_proposals, indent=2)
        test_stdout = test_report.get("stdout", "") if isinstance(test_report, dict) else ""
        test_stderr = test_report.get("stderr", "") if isinstance(test_report, dict) else ""
        test_output = f"STDOUT:\n{test_stdout}\n\nSTDERR:\n{test_stderr}"

        retry_history.append({
            "attempt": attempt + 1,
            "edit_proposals": edit_proposals,
            "test_report": test_report,
        })

        # Re-read file contents after rollback for accurate context.
        file_contents = collect_edit_context(repo, repo_context)
        new_edits = retry_edit_proposals(
            provider=args.provider,
            repo=repo,
            issue_text=issue_text,
            plan_summary=plan_summary,
            previous_edit=previous_edit,
            test_output=test_output,
            repo_context=repo_context,
            file_contents=file_contents,
        )

        # Patch payload with new edit proposals and re-prepare.
        payload["edit_proposals"] = [ep.model_dump() for ep in new_edits]
        payload = prepare_write_action(payload)

    if retry_history:
        payload["retry_history"] = retry_history

    payload = persist_run_artifacts(payload)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
