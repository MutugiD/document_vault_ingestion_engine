"""Validate F7 managed cloud backup boundary."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backup import (  # noqa: E402
    ALLOWED_CLOUD_METADATA_KEYS,
    CloudBoundaryError,
    InMemoryGrantBackend,
    assert_cloud_metadata_safe,
    assert_no_long_lived_credentials,
    create_download_grant,
    create_local_backup,
    create_upload_grant,
    delete_snapshot,
    list_snapshots,
    upload_encrypted_snapshot,
)
from vault import initialize_vault  # noqa: E402


def main() -> None:
    recovery_key = "cloud boundary recovery key"
    installation_id = "install-cloud-boundary"

    with tempfile.TemporaryDirectory() as temporary_dir:
        workspace = Path(temporary_dir)
        vault_root = workspace / "vault"
        backup_path = workspace / "snapshot.wakilibak"

        vault_session = initialize_vault(vault_root, recovery_key)
        vault_session.write_object(
            b"Cloud boundary legal document content",
            original_name="cloud-affidavit.pdf",
            content_type="application/pdf",
        )
        package = create_local_backup(
            vault_root,
            backup_path,
            recovery_key=recovery_key,
            installation_id=installation_id,
        )

        backend = InMemoryGrantBackend()
        upload_grant = create_upload_grant(
            "aws",
            installation_id,
            package.manifest.snapshot_id,
        )
        upload_result = upload_encrypted_snapshot(
            upload_grant,
            backup_path,
            backend=backend,
        )
        assert set(upload_result.metadata) == ALLOWED_CLOUD_METADATA_KEYS
        assert upload_result.metadata["installation_id"] == installation_id
        assert upload_result.metadata["snapshot_id"] == package.manifest.snapshot_id
        assert upload_result.uploaded_bytes == backup_path.stat().st_size

        snapshots = list_snapshots(backend, installation_id)
        assert len(snapshots) == 1
        assert snapshots[0].metadata == upload_result.metadata

        download_grant = create_download_grant(
            "aws",
            installation_id,
            package.manifest.snapshot_id,
        )
        assert download_grant.operation == "download"
        assert download_grant.url.startswith("https://")

        try:
            assert_cloud_metadata_safe(upload_result.metadata | {"client_name": "Forbidden"})
        except CloudBoundaryError:
            pass
        else:
            raise AssertionError("forbidden client metadata was accepted")

        try:
            assert_no_long_lived_credentials({"aws_secret_access_key": "do-not-store"})
        except CloudBoundaryError:
            pass
        else:
            raise AssertionError("long-lived credential payload was accepted")

        plaintext_path = workspace / "plain.zip"
        plaintext_path.write_bytes(b"not an encrypted backup package")
        try:
            upload_encrypted_snapshot(upload_grant, plaintext_path, backend=backend)
        except CloudBoundaryError:
            pass
        else:
            raise AssertionError("non-backup package upload was accepted")

        delete_snapshot(backend, installation_id, package.manifest.snapshot_id)
        assert list_snapshots(backend, installation_id) == []

    print("CLOUD BOUNDARY VALIDATION PASS")


if __name__ == "__main__":
    main()
