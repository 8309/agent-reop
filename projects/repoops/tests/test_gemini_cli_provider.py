import json
import unittest
from unittest.mock import patch

from repoops.gemini_cli_provider import GeminiCLIProvider


class GeminiCLIProviderTest(unittest.TestCase):
    @patch("repoops.base_cli_provider.subprocess.run")
    def test_invoke_json_reads_response_field(self, mock_run: object) -> None:
        provider = GeminiCLIProvider(repo_root=".")

        class Result:
            returncode = 0
            stdout = '{"response":"{\\"status\\":\\"ok\\"}","stats":{}}\n'
            stderr = ""

        mock_run.return_value = Result()
        response_text = provider.invoke_json(
            prompt_text="hello",
            output_schema={"type": "object", "properties": {"status": {"type": "string"}}},
        )

        self.assertEqual(json.loads(response_text)["status"], "ok")
        called_command = mock_run.call_args.kwargs.get("args") or mock_run.call_args.args[0]
        self.assertIn("--model", called_command)
        self.assertIn("gemini-3.1-pro-preview", called_command)

    @patch("repoops.base_cli_provider.subprocess.run")
    def test_invoke_json_raises_on_failure(self, mock_run: object) -> None:
        provider = GeminiCLIProvider(repo_root=".")

        class Result:
            returncode = 1
            stdout = ""
            stderr = "boom"

        mock_run.return_value = Result()

        with self.assertRaisesRegex(RuntimeError, "Gemini CLI provider failed"):
            provider.invoke_json(
                prompt_text="hello",
                output_schema={"type": "object"},
            )
