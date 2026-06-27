"""Validate the shared native app workflow boundary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import run_native_app_workflow  # noqa: E402


def main() -> None:
    provider_environment = {
        "DOCUMENT_VAULT_OPENAI_API_KEY": "sk-native-secret-123456",
        "DOCUMENT_VAULT_ANTHROPIC_API_KEY": "anthropic-native-secret-abcdef",
    }
    with tempfile.TemporaryDirectory() as temporary_dir:
        report = run_native_app_workflow(
            Path(temporary_dir),
            provider_environment=provider_environment,
        )
    payload = report.to_mapping()
    assert payload["setup_completed"] is True
    assert payload["license_status"] == "active"
    assert "document_intake" in payload["enabled_features"]
    assert payload["vault_initialized"] is True
    assert payload["accepted_imports"] == 1
    assert payload["duplicate_detected"] is True
    assert payload["matter_created"] is True
    assert payload["search_results"] >= 1
    assert payload["rag_citations"] >= 1
    assert payload["rag_confidence"] > 0
    assert payload["backup_created"] is True
    assert payload["restore_verified"] is True

    serialized = json.dumps(payload)
    assert "native-secret" not in serialized
    assert "invoice default evidence" not in serialized

    cli = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--native-workflow-e2e"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **provider_environment, "PYTHONPATH": str(ROOT)},
    )
    assert cli.returncode == 0, cli.stdout + cli.stderr
    cli_payload = json.loads(cli.stdout)
    assert cli_payload["rag_citations"] >= 1
    assert cli_payload["restore_verified"] is True
    assert "native-secret" not in cli.stdout
    assert "invoice default evidence" not in cli.stdout

    print("NATIVE WORKFLOW VALIDATION PASS")


if __name__ == "__main__":
    main()
