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
    CloudGrant,
    CloudGrantRequest,
    InMemoryGrantBackend,
    assert_cloud_metadata_safe,
    assert_no_long_lived_credentials,
    assert_provider_grant_contract,
    create_download_grant,
    create_local_backup,
    create_upload_grant,
    delete_snapshot,
    download_encrypted_snapshot,
    list_snapshots,
    restore_cloud_snapshot_drill,
    upload_encrypted_snapshot,
)
from scripts.managed_cloud_backup_e2e import run_managed_cloud_backup_e2e  # noqa: E402
from vault import initialize_vault, open_vault  # noqa: E402


def main() -> None:
    recovery_key = "cloud boundary recovery key"
    installation_id = "install-cloud-boundary"

    with tempfile.TemporaryDirectory() as temporary_dir:
        workspace = Path(temporary_dir)
        vault_root = workspace / "vault"
        backup_path = workspace / "snapshot.wakilibak"

        vault_session = initialize_vault(vault_root, recovery_key)
        stored_object = vault_session.write_object(
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
        for provider in ("aws", "azure", "gcp"):
            request = CloudGrantRequest(
                provider=provider,
                operation="upload",
                installation_id=installation_id,
                snapshot_id=package.manifest.snapshot_id,
            )
            assert request.to_mapping()["provider"] == provider
            upload_grant = create_upload_grant(
                provider,
                installation_id,
                package.manifest.snapshot_id,
            )
            assert_provider_grant_contract(upload_grant)
            assert upload_grant.to_mapping()["provider"] == provider
            upload_result = upload_encrypted_snapshot(
                upload_grant,
                backup_path,
                backend=backend,
            )
            assert set(upload_result.metadata) == ALLOWED_CLOUD_METADATA_KEYS
            assert upload_result.metadata["installation_id"] == installation_id
            assert upload_result.metadata["snapshot_id"] == package.manifest.snapshot_id
            assert upload_result.uploaded_bytes == backup_path.stat().st_size

            download_grant = create_download_grant(
                provider,
                installation_id,
                package.manifest.snapshot_id,
            )
            assert download_grant.operation == "download"
            assert download_grant.url.startswith("https://")
            downloaded_path = workspace / f"downloaded-{provider}.wakilibak"
            download_result = download_encrypted_snapshot(
                download_grant,
                downloaded_path,
                backend=backend,
            )
            assert download_result.downloaded_bytes == backup_path.stat().st_size
            assert downloaded_path.read_bytes() == backup_path.read_bytes()

        snapshots = list_snapshots(backend, installation_id)
        assert len(snapshots) == 3

        clean_restore = restore_cloud_snapshot_drill(
            create_download_grant("aws", installation_id, package.manifest.snapshot_id),
            workspace / "clean-machine-download.wakilibak",
            workspace / "clean-machine-restore",
            recovery_key=recovery_key,
            backend=backend,
        )
        assert clean_restore.verified
        restored_session = open_vault(clean_restore.restored_path, recovery_key)
        assert (
            restored_session.read_object(stored_object.object_id)
            == b"Cloud boundary legal document content"
        )

        second_backup_path = workspace / "second-snapshot.wakilibak"
        second_package = create_local_backup(
            vault_root,
            second_backup_path,
            recovery_key=recovery_key,
            installation_id=installation_id,
        )
        try:
            upload_encrypted_snapshot(
                create_upload_grant("aws", installation_id, second_package.manifest.snapshot_id),
                second_backup_path,
                backend=backend,
                simulate_interruption_after_bytes=32,
            )
        except CloudBoundaryError:
            pass
        else:
            raise AssertionError("interrupted upload unexpectedly committed")
        assert all(
            snapshot.metadata["snapshot_id"] != second_package.manifest.snapshot_id
            for snapshot in list_snapshots(backend, installation_id)
        )
        assert len(list_snapshots(backend, installation_id)) == 3

        try:
            assert_cloud_metadata_safe(upload_result.metadata | {"client_name": "Forbidden"})
        except CloudBoundaryError:
            pass
        else:
            raise AssertionError("forbidden client metadata was accepted")

        try:
            assert_no_long_lived_credentials(
                {"grant": {"aws_secret_access_key": "do-not-store"}}
            )
        except CloudBoundaryError:
            pass
        else:
            raise AssertionError("long-lived credential payload was accepted")

        try:
            upload_encrypted_snapshot(
                CloudGrant(
                    provider="aws",
                    operation="upload",
                    installation_id=installation_id,
                    snapshot_id=package.manifest.snapshot_id,
                    url="https://s3-presigned.example.invalid/upload/test",
                    expires_at=upload_grant.expires_at,
                    required_headers={"aws_secret_access_key": "do-not-store"},
                ),
                backup_path,
                backend=backend,
            )
        except CloudBoundaryError:
            pass
        else:
            raise AssertionError("credential-bearing grant was accepted")

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

        managed_report = run_managed_cloud_backup_e2e(workspace / "managed-e2e")
        assert managed_report["snapshot_count"] == 3
        assert managed_report["original_snapshot_id_present"]
        assert not managed_report["interrupted_snapshot_id_present"]
        assert managed_report["interrupted_upload_blocked"]

    print("CLOUD BOUNDARY VALIDATION PASS")


if __name__ == "__main__":
    main()
