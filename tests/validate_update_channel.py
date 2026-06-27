"""Validate signed update manifest behavior."""

from __future__ import annotations

import base64
import sys
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from release import (  # noqa: E402
    UPDATE_AVAILABLE,
    UPDATE_CURRENT,
    UPDATE_OFFLINE,
    UpdateArtifact,
    UpdateManifest,
    UpdateManifestError,
    canonical_update_manifest_bytes,
    check_for_update,
    update_manifest_from_mapping,
    verify_update_manifest,
)


def main() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    manifest = _signed_manifest(private_key, "0.2.0")
    result = verify_update_manifest(
        manifest,
        public_key_pem,
        current_version="0.1.0",
    )
    assert result.status == UPDATE_AVAILABLE
    assert result.update_available is True
    assert result.requires_user_approval is True
    assert result.artifact is not None
    assert result.artifact.platform == "windows-x64"

    current = verify_update_manifest(
        _signed_manifest(private_key, "0.1.0"),
        public_key_pem,
        current_version="0.1.0",
    )
    assert current.status == UPDATE_CURRENT
    assert current.update_available is False
    assert current.artifact is None

    payload = manifest.to_mapping()
    payload["latest_version"] = "9.9.9"
    try:
        verify_update_manifest(
            update_manifest_from_mapping(payload),
            public_key_pem,
            current_version="0.1.0",
        )
    except UpdateManifestError as exc:
        assert "signature" in str(exc)
    else:  # pragma: no cover - defensive branch
        raise AssertionError("tampered manifest was accepted")

    unsigned = UpdateManifest(
        app_name=manifest.app_name,
        channel=manifest.channel,
        latest_version=manifest.latest_version,
        published_at=manifest.published_at,
        requires_user_approval=manifest.requires_user_approval,
        artifacts=manifest.artifacts,
        signature="",
    )
    try:
        verify_update_manifest(unsigned, public_key_pem, current_version="0.1.0")
    except Exception:
        pass
    else:  # pragma: no cover - defensive branch
        raise AssertionError("unsigned manifest was accepted")

    silent = _signed_manifest(private_key, "0.2.0", requires_user_approval=False)
    try:
        verify_update_manifest(silent, public_key_pem, current_version="0.1.0")
    except UpdateManifestError as exc:
        assert "user approval" in str(exc)
    else:  # pragma: no cover - defensive branch
        raise AssertionError("silent update manifest was accepted")

    offline = check_for_update(
        lambda: (_ for _ in ()).throw(OSError("offline")),
        public_key_pem,
        current_version="0.1.0",
    )
    assert offline.status == UPDATE_OFFLINE
    assert offline.update_available is False
    assert offline.requires_user_approval is True

    print("UPDATE CHANNEL VALIDATION PASS")


def _signed_manifest(
    private_key,
    latest_version: str,
    *,
    requires_user_approval: bool = True,
) -> UpdateManifest:
    unsigned = UpdateManifest(
        app_name="DocumentVaultIngestionEngine",
        channel="stable",
        latest_version=latest_version,
        published_at=datetime(2026, 6, 28, 10, 0, tzinfo=UTC).isoformat(),
        requires_user_approval=requires_user_approval,
        artifacts=(
            UpdateArtifact(
                platform="windows-x64",
                url="https://updates.example.invalid/document-vault/0.2.0/windows.zip",
                sha256="a" * 64,
                size_bytes=123456,
            ),
        ),
        signature="",
    )
    signature = private_key.sign(
        canonical_update_manifest_bytes(unsigned),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return UpdateManifest(
        app_name=unsigned.app_name,
        channel=unsigned.channel,
        latest_version=unsigned.latest_version,
        published_at=unsigned.published_at,
        requires_user_approval=unsigned.requires_user_approval,
        artifacts=unsigned.artifacts,
        signature=base64.b64encode(signature).decode("ascii"),
    )


if __name__ == "__main__":
    main()
