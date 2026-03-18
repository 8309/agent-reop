from __future__ import annotations

import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from repoops.base_cli_provider import BaseCLIProvider


class CodexCLIProvider(BaseCLIProvider):
    cli_name = "Codex"

    def __init__(self, repo_root: str, model: str = "gpt-5.4") -> None:
        super().__init__(repo_root, model)

    def invoke_json(self, prompt_text: str, output_schema: dict[str, Any]) -> str:
        """Override to handle Codex's file-based output flow."""
        with TemporaryDirectory(prefix="repoops-codex-cli-") as temp_dir:
            temp_dir_path = Path(temp_dir)
            schema_path = temp_dir_path / "output_schema.json"
            output_path = temp_dir_path / "last_message.json"
            schema_path.write_text(json.dumps(output_schema, indent=2) + "\n", encoding="utf-8")

            command = self._build_command_with_paths(prompt_text, schema_path, output_path)
            self._run_subprocess(command, stdin=prompt_text)

            if not output_path.exists():
                raise RuntimeError("Codex CLI provider did not produce an output message")

            return output_path.read_text(encoding="utf-8")

    def _build_command(self, prompt_text: str, output_schema: dict[str, Any]) -> list[str]:
        # Not used directly — Codex needs file paths, so invoke_json is overridden.
        raise NotImplementedError  # pragma: no cover

    def _build_command_with_paths(
        self, prompt_text: str, schema_path: Path, output_path: Path
    ) -> list[str]:
        return [
            "codex",
            "exec",
            "-",
            "-C",
            str(self.repo_root),
            "--model",
            self.model,
            "--ephemeral",
            "--color",
            "never",
            "-s",
            "read-only",
            "-c",
            'approval_policy="never"',
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
        ]

    def _extract_result(self, completed: subprocess.CompletedProcess[str]) -> str:
        # Not used — Codex reads from file instead.
        raise NotImplementedError  # pragma: no cover
