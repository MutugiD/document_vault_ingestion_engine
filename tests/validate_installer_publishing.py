"""Validate installer, code-signing, and publishing metadata."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from release import (  # noqa: E402
    APP_NAME,
    INSTALLER_MANIFEST_NAME,
    create_installer_manifest,
    load_installer_manifest,
    validate_installer_manifest,
)


def main() -> None:
    release_zip = _release_zip_path()
    release_manifest = _release_manifest_path()
    assert release_zip.exists(), "missing release ZIP; run validate_release_bundle first"
    assert release_manifest.exists(), "missing release manifest; run validate_release_bundle first"

    manifest = create_installer_manifest(
        release_zip,
        release_manifest,
        ROOT / "release-output",
        ROOT,
    )
    validate_installer_manifest(manifest, project_root=ROOT)

    manifest_path = ROOT / "release-output" / INSTALLER_MANIFEST_NAME
    loaded = load_installer_manifest(manifest_path)
    assert loaded.release_zip_sha256 == manifest.release_zip_sha256
    assert loaded.release_manifest_sha256 == manifest.release_manifest_sha256
    assert loaded.signature_required is True
    assert loaded.signature_verification_script == "tools/verify_windows_signature.ps1"
    assert {shortcut.location for shortcut in loaded.shortcuts} == {"Desktop", "Start Menu"}
    assert any("--native-workflow-e2e" in check for check in loaded.clean_windows_checks)

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload).lower()
    assert "private_key" not in serialized
    assert "credential" not in serialized
    assert "recovery-key" not in serialized
    assert "client-document" not in serialized

    signature_script = ROOT / "tools" / "verify_windows_signature.ps1"
    script_text = signature_script.read_text(encoding="utf-8")
    assert "Get-AuthenticodeSignature" in script_text
    assert "Set-AuthenticodeSignature" not in script_text

    print("INSTALLER PUBLISHING VALIDATION PASS")


def _release_zip_path() -> Path:
    return ROOT / "release-output" / f"{APP_NAME}-0.1.0-windows-x64.zip"


def _release_manifest_path() -> Path:
    return ROOT / "release-output" / f"{APP_NAME}-0.1.0-windows-x64.manifest.json"


if __name__ == "__main__":
    main()
