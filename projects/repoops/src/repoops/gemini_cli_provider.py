from __future__ import annotations

import json
import subprocess
from typing import Any

from repoops.base_cli_provider import BaseCLIProvider


class GeminiCLIProvider(BaseCLIProvider):
    cli_name = "Gemini"

    def __init__(self, repo_root: str, model: str = "gemini-3.1-pro-preview") -> None:
        super().__init__(repo_root, model)

    def _build_command(self, prompt_text: str, output_schema: dict[str, Any]) -> list[str]:
        schema_hint = json.dumps(output_schema, indent=2)
        full_prompt = (
            f"{prompt_text}\n\n"
            "Return only a raw JSON object with no markdown fences, no commentary, and no prose.\n"
            "The JSON must conform to this schema:\n"
            f"{schema_hint}\n"
        )
        return [
            "gemini",
            "-p",
            full_prompt,
            "--output-format",
            "json",
            "--approval-mode",
            "plan",
            "--model",
            self.model,
        ]

    def _extract_result(self, completed: subprocess.CompletedProcess[str]) -> str:
        stdout = completed.stdout.strip()
        if not stdout:
            raise RuntimeError("Gemini CLI provider returned empty output")

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Gemini CLI provider returned non-JSON output") from exc

        response = payload.get("response")
        if not isinstance(response, str) or not response.strip():
            raise RuntimeError("Gemini CLI provider did not return a JSON response payload")

        return response.strip()
