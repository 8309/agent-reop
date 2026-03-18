from __future__ import annotations

import abc
import json
import subprocess
from pathlib import Path
from typing import Any


class BaseCLIProvider(abc.ABC):
    """Base class for CLI-based LLM providers.

    Subclasses implement ``_build_command`` and ``_extract_result`` to
    customise how each external CLI tool is invoked and how the structured
    JSON output is extracted from its response.
    """

    cli_name: str = "cli"

    def __init__(self, repo_root: str, model: str) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.model = model

    @abc.abstractmethod
    def _build_command(self, prompt_text: str, output_schema: dict[str, Any]) -> list[str]:
        """Return the CLI command to execute."""

    @abc.abstractmethod
    def _extract_result(self, completed: subprocess.CompletedProcess[str]) -> str:
        """Extract the JSON string from a successful CLI response."""

    def _run_subprocess(self, command: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        """Execute *command* and raise on failure."""
        try:
            completed = subprocess.run(
                command,
                input=stdin,
                text=True,
                capture_output=True,
                check=False,
                cwd=str(self.repo_root),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"{self.cli_name} CLI is not installed or not on PATH") from exc

        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            details = stderr or stdout or f"exit code {completed.returncode}"
            raise RuntimeError(f"{self.cli_name} CLI provider failed: {details}")

        return completed

    def invoke_json(self, prompt_text: str, output_schema: dict[str, Any]) -> str:
        """Invoke the CLI and return the structured JSON string."""
        command = self._build_command(prompt_text, output_schema)
        completed = self._run_subprocess(command)
        return self._extract_result(completed)
