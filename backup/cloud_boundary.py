"""Managed cloud backup boundary with short-lived grants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from backup.core import BackupManifest, read_backup_manifest

CloudProvider = Literal["aws", "azure", "gcp"]
GrantOperation = Literal["upload", "download", "delete"]

ALLOWED_CLOUD_METADATA_KEYS = {
    "installation_id",
    "snapshot_id",
    "package_size_bytes",
    "package_hash",
    "created_at",
    "app_version",
    "upload_status",
}

FORBIDDEN_CLOUD_METADATA_KEYS = {
    "matter_name",
    "matter_names",
    "client_name",
    "client_names",
    "case_number",
    "case_numbers",
    "filename",
    "filenames",
    "ocr_text",
    "extracted_text",
    "recovery_key",
    "file_hash",
    "source_sha256",
}

CREDENTIAL_FIELD_NAMES = {
    "aws_access_key_id",
    "aws_secret_access_key",
    "aws_session_token",
    "azure_connection_string",
    "gcp_service_account_json",
    "private_key",
    "client_secret",
}


class CloudBoundaryError(Exception):
    """Base managed cloud boundary failure."""


@dataclass(frozen=True)
class CloudGrant:
    provider: CloudProvider
    operation: GrantOperation
    installation_id: str
    snapshot_id: str
    url: str
    expires_at: datetime
    required_headers: dict[str, str]

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= datetime.now(UTC)


@dataclass(frozen=True)
class CloudSnapshot:
    provider: CloudProvider
    metadata: dict[str, object]


@dataclass(frozen=True)
class UploadResult:
    provider: CloudProvider
    snapshot_id: str
    metadata: dict[str, object]
    uploaded_bytes: int


class InMemoryGrantBackend:
    """Local test double for the owner backend that issues short-lived grants."""

    def __init__(self) -> None:
        self._snapshots: dict[tuple[str, str], CloudSnapshot] = {}

    def create_upload_grant(
        self,
        provider: CloudProvider,
        installation_id: str,
        snapshot_id: str,
    ) -> CloudGrant:
        return _create_grant(provider, "upload", installation_id, snapshot_id)

    def create_download_grant(
        self,
        provider: CloudProvider,
        installation_id: str,
        snapshot_id: str,
    ) -> CloudGrant:
        return _create_grant(provider, "download", installation_id, snapshot_id)

    def register_upload(
        self,
        provider: CloudProvider,
        metadata: dict[str, object],
    ) -> None:
        safe_metadata = assert_cloud_metadata_safe(metadata)
        self._snapshots[(provider, str(safe_metadata["snapshot_id"]))] = CloudSnapshot(
            provider=provider,
            metadata=safe_metadata,
        )

    def list_snapshots(self, installation_id: str) -> list[CloudSnapshot]:
        return [
            snapshot
            for snapshot in self._snapshots.values()
            if snapshot.metadata["installation_id"] == installation_id
        ]

    def delete_snapshot(self, installation_id: str, snapshot_id: str) -> None:
        for key, snapshot in list(self._snapshots.items()):
            if (
                snapshot.metadata["installation_id"] == installation_id
                and snapshot.metadata["snapshot_id"] == snapshot_id
            ):
                del self._snapshots[key]


def create_upload_grant(
    provider: CloudProvider,
    installation_id: str,
    snapshot_id: str,
) -> CloudGrant:
    return _create_grant(provider, "upload", installation_id, snapshot_id)


def upload_encrypted_snapshot(
    grant: CloudGrant,
    encrypted_package: Path,
    *,
    backend: InMemoryGrantBackend | None = None,
) -> UploadResult:
    if grant.operation != "upload":
        raise CloudBoundaryError("grant is not an upload grant")
    if grant.is_expired:
        raise CloudBoundaryError("grant has expired")
    if encrypted_package.suffix.lower() != ".wakilibak":
        raise CloudBoundaryError("cloud upload boundary only accepts encrypted backup packages")

    manifest = read_backup_manifest(encrypted_package)
    if manifest.installation_id != grant.installation_id:
        raise CloudBoundaryError("grant installation does not match backup manifest")
    if manifest.snapshot_id != grant.snapshot_id:
        raise CloudBoundaryError("grant snapshot does not match backup manifest")

    metadata = cloud_metadata_from_manifest(manifest, upload_status="uploaded")
    safe_metadata = assert_cloud_metadata_safe(metadata)
    if backend is not None:
        backend.register_upload(grant.provider, safe_metadata)
    return UploadResult(
        provider=grant.provider,
        snapshot_id=manifest.snapshot_id,
        metadata=safe_metadata,
        uploaded_bytes=encrypted_package.stat().st_size,
    )


def list_snapshots(backend: InMemoryGrantBackend, installation_id: str) -> list[CloudSnapshot]:
    return backend.list_snapshots(installation_id)


def create_download_grant(
    provider: CloudProvider,
    installation_id: str,
    snapshot_id: str,
) -> CloudGrant:
    return _create_grant(provider, "download", installation_id, snapshot_id)


def delete_snapshot(
    backend: InMemoryGrantBackend,
    installation_id: str,
    snapshot_id: str,
) -> None:
    backend.delete_snapshot(installation_id, snapshot_id)


def cloud_metadata_from_manifest(
    manifest: BackupManifest,
    *,
    upload_status: str,
) -> dict[str, object]:
    return {
        "installation_id": manifest.installation_id,
        "snapshot_id": manifest.snapshot_id,
        "package_size_bytes": manifest.package_size_bytes,
        "package_hash": manifest.package_hash,
        "created_at": manifest.created_at.isoformat().replace("+00:00", "Z"),
        "app_version": manifest.app_version,
        "upload_status": upload_status,
    }


def assert_cloud_metadata_safe(metadata: dict[str, object]) -> dict[str, object]:
    keys = set(metadata)
    extra_keys = keys - ALLOWED_CLOUD_METADATA_KEYS
    if extra_keys:
        raise CloudBoundaryError(f"metadata contains non-allowlisted keys: {sorted(extra_keys)}")
    forbidden_keys = keys & FORBIDDEN_CLOUD_METADATA_KEYS
    if forbidden_keys:
        raise CloudBoundaryError(f"metadata contains forbidden keys: {sorted(forbidden_keys)}")
    credential_keys = keys & CREDENTIAL_FIELD_NAMES
    if credential_keys:
        raise CloudBoundaryError(f"metadata contains credential keys: {sorted(credential_keys)}")
    missing_keys = ALLOWED_CLOUD_METADATA_KEYS - keys
    if missing_keys:
        raise CloudBoundaryError(f"metadata is missing required keys: {sorted(missing_keys)}")
    return dict(metadata)


def assert_no_long_lived_credentials(payload: dict[str, object]) -> None:
    credential_keys = set(payload) & CREDENTIAL_FIELD_NAMES
    if credential_keys:
        raise CloudBoundaryError(f"payload contains cloud credentials: {sorted(credential_keys)}")


def _create_grant(
    provider: CloudProvider,
    operation: GrantOperation,
    installation_id: str,
    snapshot_id: str,
) -> CloudGrant:
    if provider not in {"aws", "azure", "gcp"}:
        raise CloudBoundaryError(f"unsupported provider: {provider}")
    expires_at = datetime.now(UTC) + timedelta(minutes=15)
    return CloudGrant(
        provider=provider,
        operation=operation,
        installation_id=installation_id,
        snapshot_id=snapshot_id,
        url=f"https://backup-grants.example.invalid/{provider}/{operation}/{snapshot_id}",
        expires_at=expires_at,
        required_headers={"x-wakili-installation-id": installation_id},
    )
