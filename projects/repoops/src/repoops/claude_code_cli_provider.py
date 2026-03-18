from __future__ import annotations

import json
import subprocess
from typing import Any

from repoops.base_cli_provider import BaseCLIProvider


class ClaudeCodeCLIProvider(BaseCLIProvider):
    cli_name = "Claude Code"

    def __init__(self, repo_root: str, model: str = "claude-opus-4-6") -> None:
        super().__init__(repo_root, model)

    def _build_command(self, prompt_text: str, output_schema: dict[str, Any]) -> list[str]:
        return [
            "claude",
            "-p",
            prompt_text,
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(output_schema, separators=(",", ":")),
            "--permission-mode",
            "default",
            "--tools",
            "",
            "--model",
            self.model,
            "--no-session-persistence",
        ]

    def _extract_result(self, completed: subprocess.CompletedProcess[str]) -> str:
        stdout = completed.stdout.strip()
        if not stdout:
            raise RuntimeError("Claude Code CLI provider returned empty output")

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Claude Code CLI provider returned non-JSON output") from exc

        structured_output = payload.get("structured_output")
        if structured_output is None:
            raise RuntimeError("Claude Code CLI provider did not return structured_output")

        return json.dumps(structured_output, indent=2)
