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
from repoops.claude_code_cli_provider import ClaudeCodeCLIProvider
from repoops.cli import load_issue_text, persist_run_artifacts
from repoops.codex_cli_provider import CodexCLIProvider
from repoops.gemini_cli_provider import GeminiCLIProvider
from repoops.read_only_tools import collect_repo_context


class PlanStepModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(description="Stable identifier for one plan step")
    description: str = Field(description="Human-readable step description")
    status: str = Field(description="Execution status for the step")


class PlanDraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_title: str = Field(description="Short issue title")
    issue_summary: str = Field(description="Single-sentence summary of the issue")
    acceptance_criteria: list[str] = Field(description="Acceptance criteria copied from the issue")
    plan_outline: list[PlanStepModel] = Field(description="Structured execution plan")


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

    if provider == "codex-cli":
        codex_provider = CodexCLIProvider(repo)

        def run_codex(prompt_value: object) -> str:
            prompt_text = prompt_value.to_string() if hasattr(prompt_value, "to_string") else str(prompt_value)
            return codex_provider.invoke_json(
                prompt_text=prompt_text,
                output_schema=PlanDraftModel.model_json_schema(),
            )

        return (
            RunnableLambda(run_codex),
            ["PromptTemplate", "CodexCLIProvider", "PydanticOutputParser"],
        )

    if provider == "claude-code-cli":
        claude_provider = ClaudeCodeCLIProvider(repo)

        def run_claude(prompt_value: object) -> str:
            prompt_text = prompt_value.to_string() if hasattr(prompt_value, "to_string") else str(prompt_value)
            return claude_provider.invoke_json(
                prompt_text=prompt_text,
                output_schema=PlanDraftModel.model_json_schema(),
            )

        return (
            RunnableLambda(run_claude),
            ["PromptTemplate", "ClaudeCodeCLIProvider", "PydanticOutputParser"],
        )

    if provider == "gemini-cli":
        gemini_provider = GeminiCLIProvider(repo)

        def run_gemini(prompt_value: object) -> str:
            prompt_text = prompt_value.to_string() if hasattr(prompt_value, "to_string") else str(prompt_value)
            return gemini_provider.invoke_json(
                prompt_text=prompt_text,
                output_schema=PlanDraftModel.model_json_schema(),
            )

        return (
            RunnableLambda(run_gemini),
            ["PromptTemplate", "GeminiCLIProvider", "PydanticOutputParser"],
        )

    raise ValueError(f"Unsupported provider: {provider}")


def build_learning_chain(
    repo: str,
    issue_text: str,
    repo_context: dict[str, object],
    provider: str = "deterministic",
) -> tuple[str, PlanDraftModel, list[str]]:
    parser = PydanticOutputParser(pydantic_object=PlanDraftModel)
    prompt = PromptTemplate.from_template(
        "You are a RepoOps planning component.\n"
        "Read the issue below and produce a structured execution plan.\n\n"
        "Use the repository context below as supporting evidence. Do not run shell commands.\n\n"
        "Issue:\n{issue_text}\n\n"
        "Repository context:\n{repo_context}\n\n"
        "Return JSON that matches this schema:\n{format_instructions}\n"
    )
    prompt_input = {
        "issue_text": issue_text,
        "repo_context": format_repo_context_for_prompt(repo_context),
        "format_instructions": parser.get_format_instructions(),
    }
    prompt_preview = prompt.invoke(prompt_input).to_string()

    # Swap only the model/provider step so the PromptTemplate and parser stay constant across
    # deterministic and Codex-backed runs.
    planner_model, chain_steps = build_planner_runnable(provider=provider, repo=repo, issue_text=issue_text)
    chain = prompt | planner_model | parser
    return prompt_preview, chain.invoke(prompt_input), chain_steps


def build_langchain_artifact(
    repo: str,
    issue: str | None,
    dry_run: bool,
    approve_write: bool,
    provider: str = "deterministic",
) -> dict[str, object]:
    issue_text = load_issue_text(issue)
    repo_context = collect_repo_context(repo)
    prompt_preview, plan_draft, chain_steps = build_learning_chain(
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
        choices=("deterministic", "codex-cli", "claude-code-cli", "gemini-cli"),
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

    payload = build_langchain_artifact(
        repo=str(repo_path.resolve()),
        issue=str(Path(args.issue).resolve()) if args.issue else None,
        dry_run=args.dry_run,
        approve_write=args.approve_write,
        provider=args.provider,
    )
    payload = persist_run_artifacts(payload)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
