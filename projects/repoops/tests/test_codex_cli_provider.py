import json
from pathlib import Path
import unittest
from unittest.mock import patch

from repoops.codex_cli_provider import CodexCLIProvider


class CodexCLIProviderTest(unittest.TestCase):
    @patch("repoops.base_cli_provider.subprocess.run")
    def test_invoke_json_reads_structured_output_file(self, mock_run: object) -> None:
        provider = CodexCLIProvider(repo_root=".")

        def fake_run(command: list[str], **_: object) -> object:
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text('{"status":"ok"}\n', encoding="utf-8")

            class Result:
                returncode = 0
                stdout = ""
                stderr = ""

            return Result()

        mock_run.side_effect = fake_run
        response_text = provider.invoke_json(
            prompt_text="hello",
            output_schema={"type": "object", "properties": {"status": {"type": "string"}}},
        )

        self.assertEqual(json.loads(response_text)["status"], "ok")
        called_command = mock_run.call_args.kwargs.get("args") or mock_run.call_args.args[0]
        self.assertIn("--model", called_command)
        self.assertIn("gpt-5.4", called_command)

    @patch("repoops.base_cli_provider.subprocess.run")
    def test_invoke_json_raises_on_failure(self, mock_run: object) -> None:
        provider = CodexCLIProvider(repo_root=".")

        class Result:
            returncode = 1
            stdout = ""
            stderr = "boom"

        mock_run.return_value = Result()

        with self.assertRaisesRegex(RuntimeError, "Codex CLI provider failed"):
            provider.invoke_json(
                prompt_text="hello",
                output_schema={"type": "object"},
            )
