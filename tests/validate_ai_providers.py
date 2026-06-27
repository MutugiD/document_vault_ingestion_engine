"""Validate AI provider API-key configuration status is redacted."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai import configured_provider_statuses, provider_env_var, redact_api_key  # noqa: E402


def main() -> None:
    environment = {
        "DOCUMENT_VAULT_OPENAI_API_KEY": "sk-test-openai-secret-123456",
        "DOCUMENT_VAULT_ANTHROPIC_API_KEY": "anthropic-secret-abcdef",
    }
    statuses = configured_provider_statuses(environment)
    assert len(statuses) == 5
    openai = next(status for status in statuses if status.provider == "openai")
    assert openai.configured
    assert openai.redacted_value == "sk-...3456"
    assert "secret" not in openai.redacted_value
    assert redact_api_key("short") == "*****"
    assert provider_env_var("google") == "DOCUMENT_VAULT_GOOGLE_API_KEY"

    cli = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--providers"],
        check=False,
        capture_output=True,
        text=True,
        env={**environment, "PYTHONPATH": str(ROOT)},
    )
    assert cli.returncode == 0, cli.stdout + cli.stderr
    payload = json.loads(cli.stdout)
    assert len(payload["providers"]) == 5
    assert "openai-secret" not in cli.stdout
    assert "anthropic-secret" not in cli.stdout

    print("AI PROVIDER VALIDATION PASS")


if __name__ == "__main__":
    main()
