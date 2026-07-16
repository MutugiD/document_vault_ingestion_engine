"""Validate WakiliOS multi-seat backend behavior."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.wakilios_backend_e2e import run_wakilios_backend_e2e  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        report = run_wakilios_backend_e2e(Path(temporary_dir))

    assert report["product"] == "WakiliOS"
    assert report["workspace_tabs_present"] is True
    assert report["seat_limit_blocked"] is True
    assert report["permission_blocked"] is True
    assert report["document_uploaded"] is True
    assert report["summary_has_citations"] is True
    assert report["ics_contains_activity"] is True
    assert report["ics_contains_lodging"] is True
    assert report["offline_cache_mode"] == "read_only"
    assert int(report["offline_cache_matter_count"]) >= 1
    assert int(report["audit_event_count"]) >= 8
    assert report["raw_document_text_in_audit"] is False

    print("WAKILIOS BACKEND VALIDATION PASS")


if __name__ == "__main__":
    main()
