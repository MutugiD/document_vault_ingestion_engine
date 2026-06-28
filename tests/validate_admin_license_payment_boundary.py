"""Validate enterprise admin/license/payment boundary behavior."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.admin_license_payment_e2e import run_admin_license_payment_e2e  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        report = run_admin_license_payment_e2e(Path(temporary_dir))

    active = report["active_decision"]
    disabled = report["disabled_decision"]
    suspended = report["suspended_payment_decision"]
    expired = report["expired_payment_decision"]
    assert isinstance(active, dict)
    assert isinstance(disabled, dict)
    assert isinstance(suspended, dict)
    assert isinstance(expired, dict)
    assert active["cloud_backup_enabled"]
    assert active["matter_rag_enabled"]
    assert not active["hosted_ai_enabled"]
    assert not disabled["paid_features_enabled"]
    assert disabled["local_export_allowed"]
    assert disabled["local_restore_allowed"]
    assert not suspended["paid_features_enabled"]
    assert suspended["local_restore_allowed"]
    assert not expired["paid_features_enabled"]
    assert expired["local_export_allowed"]
    assert report["missing_payment_paid_features_enabled"] is False
    assert report["tampered_license_local_export_allowed"] is False
    assert report["privacy_rejections_verified"] is True

    print("ADMIN LICENSE PAYMENT BOUNDARY VALIDATION PASS")


if __name__ == "__main__":
    main()
