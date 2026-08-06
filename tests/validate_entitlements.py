"""Validate that a licence's paid features are actually enforced.

`FeatureEntitlements` has been carried on every signed licence, parsed on
activation, printed in the admin panel -- and never consulted. Every plan
behaved like enterprise, so the commercial tiers were decoration.

The important assertions here are the negative ones: a licence without a
feature must leave that feature switched off, and a role must never be able to
widen what a licence grants.
"""

from __future__ import annotations

import base64
import os
import sys
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402
from PySide6.QtWidgets import QLineEdit, QPushButton  # noqa: E402

import licensing.core as licensing_core  # noqa: E402
from licensing import (  # noqa: E402
    FeatureEntitlements,
    LicenseDocument,
    canonical_license_bytes,
    ensure_installation_identity,
    write_license_file,
)
from ui import MainWindow, create_app  # noqa: E402
from ui.app import ENTITLEMENT_CONTROLS  # noqa: E402


def issue(root: Path, features: FeatureEntitlements, plan: str) -> tuple[Path, bytes]:
    """Sign a licence for this installation with a throwaway key."""
    identity = ensure_installation_identity(
        root / "appdata" / "WakiliOS" / "settings" / "installation.json"
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    document = LicenseDocument(
        installation_id=identity.installation_id,
        license_id=f"LIC-{plan.upper()}",
        firm_display_name="Entitlement Test Advocates",
        plan=plan,
        features=features,
        expiry=date.today() + timedelta(days=30),
        issued_at=datetime.now(UTC),
        signature="",
    )
    signature = key.sign(
        canonical_license_bytes(document),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    path = root / f"{plan}.key"
    write_license_file(
        path,
        LicenseDocument(
            installation_id=document.installation_id,
            license_id=document.license_id,
            firm_display_name=document.firm_display_name,
            plan=document.plan,
            features=document.features,
            expiry=document.expiry,
            issued_at=document.issued_at,
            signature=base64.b64encode(signature).decode("ascii"),
        ),
    )
    return path, public_pem


def activate(app, window, license_path: Path) -> None:
    window.findChild(QLineEdit, "licenseFileInput").setText(str(license_path))
    window.findChild(QPushButton, "activateLicenseButton").click()
    app.processEvents()


def enabled(window, object_name: str) -> bool | None:
    control = window.findChild(QPushButton, object_name)
    return None if control is None else control.isEnabled()


def main() -> None:
    original_key = licensing_core._PUBLIC_KEY_PEM
    app = create_app(["validate_entitlements"])

    # ── A solo plan: intake only ─────────────────────────────────────────
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        os.environ["APPDATA"] = str(root / "appdata")
        solo_features = FeatureEntitlements(
            document_intake=True,
            cloud_backup=False,
            managed_restore=False,
            matter_rag=False,
            hosted_ai=False,
        )
        path, public_pem = issue(root, solo_features, "solo")
        licensing_core._PUBLIC_KEY_PEM = public_pem
        try:
            window = MainWindow(workspace=root / "workspace")
            activate(app, window, path)
            assert window._license_active is True, "a valid licence must open the gate"

            for name, granted in (
                ("document_intake", True),
                ("cloud_backup", False),
                ("managed_restore", False),
                ("matter_rag", False),
                ("hosted_ai", False),
            ):
                for object_name in ENTITLEMENT_CONTROLS[name]:
                    state = enabled(window, object_name)
                    assert state is not None, f"missing control: {object_name}"
                    assert state is granted, (
                        f"{object_name}: expected enabled={granted} for a solo licence, got {state}"
                    )

            # A withheld feature says why, rather than being silently dead.
            backup = window.findChild(QPushButton, "createBackupButton")
            assert "not included" in backup.toolTip(), backup.toolTip()

            # And the status names what was withheld, so the firm can act.
            status = window.status_label.text()
            assert "Cloud backup" in status, status

            # A role change must not re-enable an unpaid feature.
            window._apply_role_permissions("admin")
            assert enabled(window, "createBackupButton") is False, (
                "a role must never widen what a licence grants"
            )
            window.close()
            app.processEvents()
        finally:
            licensing_core._PUBLIC_KEY_PEM = original_key

    # ── An enterprise plan: everything on ────────────────────────────────
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        os.environ["APPDATA"] = str(root / "appdata")
        path, public_pem = issue(
            root, FeatureEntitlements(True, True, True, True, True), "enterprise"
        )
        licensing_core._PUBLIC_KEY_PEM = public_pem
        try:
            window = MainWindow(workspace=root / "workspace")
            activate(app, window, path)
            for controls in ENTITLEMENT_CONTROLS.values():
                for object_name in controls:
                    assert enabled(window, object_name) is True, (
                        f"{object_name} must be available on an enterprise licence"
                    )
            assert "includes every feature" in window.status_label.text()
            window.close()
            app.processEvents()
        finally:
            licensing_core._PUBLIC_KEY_PEM = original_key

    print("ENTITLEMENTS VALIDATION PASS")


if __name__ == "__main__":
    main()
