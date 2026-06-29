"""Validate F35 Wakili-Mkononi integration boundary behavior."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.wakili_mkononi_e2e import run_wakili_mkononi_e2e  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        report = run_wakili_mkononi_e2e(Path(temporary_dir))

    assert report["handoff_prepared"] is True
    assert report["schema_version"] == "1"
    assert report["integration"] == "wakili-mkononi"
    assert int(report["citation_count"]) >= 1
    assert 0 < float(report["confidence"]) <= 1
    assert report["contains_grounded_context"] is False
    assert report["contains_retrieval_results"] is False
    assert report["question_digest_length"] == 64
    assert report["blocked_without_approval"] is True
    assert report["blocked_without_entitlement"] is True
    assert report["local_access_after_block"] is True
    assert report["unsafe_payload_blocked"] is True
    assert report["audit_event_recorded"] is True

    print("WAKILI MKONONI INTEGRATION VALIDATION PASS")


if __name__ == "__main__":
    main()
