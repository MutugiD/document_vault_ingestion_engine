"""Managed cloud backup boundary E2E runner with redacted output."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from backup import (
    ALLOWED_CLOUD_METADATA_KEYS,
    CloudBoundaryError,
    InMemoryGrantBackend,
    assert_provider_grant_contract,
    create_download_grant,
    create_local_backup,
    create_upload_grant,
    list_snapshots,
    restore_cloud_snapshot_drill,
    upload_encrypted_snapshot,
)
from vault import initialize_vault, open_vault


def run_managed_cloud_backup_e2e(workspace: Path | None = None) -> dict[str, object]:
    """Run AWS/Azure/GCP grant, upload, download, restore, and interruption checks."""

    if workspace is None:
        with tempfile.TemporaryDirectory(prefix="dv-managed-cloud-backup-") as temporary_dir:
            return run_managed_cloud_backup_e2e(Path(temporary_dir))

    workspace.mkdir(parents=True, exist_ok=True)
    recovery_key = "managed cloud backup e2e passphrase"
    installation_id = "install-managed-cloud-backup-e2e"
    vault_root = workspace / "vault"
    backup_path = workspace / "snapshot.wakilibak"

    vault_session = initialize_vault(vault_root, recovery_key)
    stored_object = vault_session.write_object(
        b"Managed cloud backup legal content must remain encrypted.",
        original_name="managed-cloud-affidavit.pdf",
        content_type="application/pdf",
    )
    package = create_local_backup(
        vault_root,
        backup_path,
        recovery_key=recovery_key,
        installation_id=installation_id,
    )
    backend = InMemoryGrantBackend()
    provider_reports: list[dict[str, object]] = []
    for provider in ("aws", "azure", "gcp"):
        upload_grant = create_upload_grant(provider, installation_id, package.manifest.snapshot_id)
        assert_provider_grant_contract(upload_grant)
        upload_result = upload_encrypted_snapshot(upload_grant, backup_path, backend=backend)
        assert set(upload_result.metadata) == ALLOWED_CLOUD_METADATA_KEYS

        restore_result = restore_cloud_snapshot_drill(
            create_download_grant(provider, installation_id, package.manifest.snapshot_id),
            workspace / f"{provider}-download.wakilibak",
            workspace / f"{provider}-restore",
            recovery_key=recovery_key,
            backend=backend,
        )
        restored_session = open_vault(restore_result.restored_path, recovery_key)
        assert (
            restored_session.read_object(stored_object.object_id)
            == b"Managed cloud backup legal content must remain encrypted."
        )
        provider_reports.append(
            {
                "provider": provider,
                "metadata_keys": sorted(upload_result.metadata),
                "uploaded_bytes": upload_result.uploaded_bytes,
                "restore_verified": restore_result.verified,
            }
        )

    interrupted_backup_path = workspace / "interrupted.wakilibak"
    interrupted_package = create_local_backup(
        vault_root,
        interrupted_backup_path,
        recovery_key=recovery_key,
        installation_id=installation_id,
    )
    try:
        upload_encrypted_snapshot(
            create_upload_grant("aws", installation_id, interrupted_package.manifest.snapshot_id),
            interrupted_backup_path,
            backend=backend,
            simulate_interruption_after_bytes=64,
        )
    except CloudBoundaryError:
        interrupted_upload_blocked = True
    else:
        interrupted_upload_blocked = False

    snapshot_ids = {
        str(snapshot.metadata["snapshot_id"])
        for snapshot in list_snapshots(backend, installation_id)
    }
    report = {
        "providers": provider_reports,
        "snapshot_count": len(list_snapshots(backend, installation_id)),
        "original_snapshot_id_present": package.manifest.snapshot_id in snapshot_ids,
        "interrupted_snapshot_id_present": interrupted_package.manifest.snapshot_id in snapshot_ids,
        "interrupted_upload_blocked": interrupted_upload_blocked,
    }
    _assert_report_safe(report)
    return report


def _assert_report_safe(report: dict[str, object]) -> None:
    serialized = json.dumps(report, sort_keys=True).lower()
    for forbidden in (
        "client_name",
        "matter_name",
        "case_number",
        "filename",
        "ocr_text",
        "prompt",
        "recovery",
        "secret",
        "credential",
        "managed cloud backup legal content",
    ):
        if forbidden in serialized:
            raise AssertionError(f"managed cloud report contains forbidden material: {forbidden}")


if __name__ == "__main__":
    print(json.dumps(run_managed_cloud_backup_e2e(), indent=2, sort_keys=True))
