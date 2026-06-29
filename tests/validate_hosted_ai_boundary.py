"""Validate F36 hosted AI/LLM boundary behavior."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.hosted_ai_e2e import run_hosted_ai_e2e  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        report = run_hosted_ai_e2e(Path(temporary_dir))

    assert report["hosted_answer_status"] == "hosted_answer"
    assert report["hosted_answer_has_citations"] is True
    assert 0 < float(report["hosted_answer_confidence"]) <= 1
    assert report["request_provider"] == "openai"
    assert int(report["request_citation_count"]) >= 1
    assert report["prompt_contains_context"] is True
    assert report["prompt_contains_provider_key"] is False
    assert report["provider_configured"] is True
    assert report["provider_redacted_value"] == "sk-...-key"
    assert report["disabled_blocked"] is True
    assert report["unapproved_blocked"] is True
    assert report["missing_key_blocked"] is True
    assert report["no_context_blocked"] is True
    assert report["fallback_status"] == "local_rag_fallback"
    assert report["fallback_has_no_hosted_answer"] is True
    assert report["unsafe_prompt_blocked"] is True
    assert report["hosted_audit_recorded"] is True
    assert report["fallback_audit_recorded"] is True

    print("HOSTED AI BOUNDARY VALIDATION PASS")


if __name__ == "__main__":
    main()
