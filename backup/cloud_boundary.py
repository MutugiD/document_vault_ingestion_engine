"""Managed cloud backup boundary with short-lived grants."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
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

    def to_mapping(self) -> dict[str, object]:
        payload = {
            "provider": self.provider,
            "operation": self.operation,
            "installation_id": self.installation_id,
            "snapshot_id": self.snapshot_id,
            "url": self.url,
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
            "required_headers": dict(sorted(self.required_headers.items())),
        }
        assert_no_long_lived_credentials(payload)
        assert_no_long_lived_credentials(self.required_headers)
        return payload


@dataclass(frozen=True)
class CloudGrantRequest:
    provider: CloudProvider
    operation: GrantOperation
    installation_id: str
    snapshot_id: str

    def to_mapping(self) -> dict[str, str]:
        payload = {
            "provider": self.provider,
            "operation": self.operation,
            "installation_id": self.installation_id,
            "snapshot_id": self.snapshot_id,
        }
        assert_no_long_lived_credentials(payload)
        return payload


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
    committed: bool = True


@dataclass(frozen=True)
class DownloadResult:
    provider: CloudProvider
    snapshot_id: str
    path: Path
    downloaded_bytes: int


@dataclass(frozen=True)
class CloudRestoreDrillResult:
    provider: CloudProvider
    snapshot_id: str
    downloaded_path: Path
    restored_path: Path
    restored_file_count: int
    verified: bool


class InMemoryGrantBackend:
    """Local test double for the owner backend that issues short-lived grants."""

    def __init__(self) -> None:
        self._snapshots: dict[tuple[str, str], CloudSnapshot] = {}
        self._packages: dict[tuple[str, str], bytes] = {}
        self._pending_packages: dict[tuple[str, str], tuple[dict[str, object], bytes]] = {}

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
        encrypted_package: bytes,
    ) -> None:
        self.stage_upload(provider, metadata, encrypted_package)
        self.commit_upload(
            provider,
            str(metadata["installation_id"]),
            str(metadata["snapshot_id"]),
            expected_package_hash=str(metadata["package_hash"]),
        )

    def stage_upload(
        self,
        provider: CloudProvider,
        metadata: dict[str, object],
        encrypted_package: bytes,
    ) -> None:
        safe_metadata = assert_cloud_metadata_safe(metadata)
        key = (provider, str(safe_metadata["snapshot_id"]))
        self._pending_packages[key] = (safe_metadata, encrypted_package)

    def commit_upload(
        self,
        provider: CloudProvider,
        installation_id: str,
        snapshot_id: str,
        *,
        expected_package_hash: str,
    ) -> None:
        key = (provider, snapshot_id)
        pending = self._pending_packages.get(key)
        if pending is None:
            raise CloudBoundaryError("no pending upload is available to commit")
        metadata, encrypted_package = pending
        if metadata["installation_id"] != installation_id:
            raise CloudBoundaryError("pending upload installation does not match commit")
        if _package_hash_from_bytes(encrypted_package) != expected_package_hash:
            self._pending_packages.pop(key, None)
            raise CloudBoundaryError("pending upload hash does not match manifest")
        committed_metadata = dict(metadata) | {"upload_status": "uploaded"}
        safe_metadata = assert_cloud_metadata_safe(committed_metadata)
        self._snapshots[key] = CloudSnapshot(provider=provider, metadata=safe_metadata)
        self._packages[key] = encrypted_package
        self._pending_packages.pop(key, None)

    def abort_upload(self, provider: CloudProvider, snapshot_id: str) -> None:
        self._pending_packages.pop((provider, snapshot_id), None)

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
                self._packages.pop(key, None)
                self._pending_packages.pop(key, None)

    def download_package(
        self,
        provider: CloudProvider,
        installation_id: str,
        snapshot_id: str,
    ) -> bytes:
        snapshot = self._snapshots.get((provider, snapshot_id))
        if snapshot is None or snapshot.metadata["installation_id"] != installation_id:
            raise CloudBoundaryError("snapshot is not available from owner backend")
        return self._packages[(provider, snapshot_id)]


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
    simulate_interruption_after_bytes: int | None = None,
) -> UploadResult:
    if grant.operation != "upload":
        raise CloudBoundaryError("grant is not an upload grant")
    if grant.is_expired:
        raise CloudBoundaryError("grant has expired")
    assert_no_long_lived_credentials(grant.required_headers)
    if encrypted_package.suffix.lower() != ".wakilibak":
        raise CloudBoundaryError("cloud upload boundary only accepts encrypted backup packages")

    manifest = read_backup_manifest(encrypted_package)
    if manifest.installation_id != grant.installation_id:
        raise CloudBoundaryError("grant installation does not match backup manifest")
    if manifest.snapshot_id != grant.snapshot_id:
        raise CloudBoundaryError("grant snapshot does not match backup manifest")

    package_bytes = encrypted_package.read_bytes()
    metadata = cloud_metadata_from_manifest(manifest, upload_status="uploading")
    safe_metadata = assert_cloud_metadata_safe(metadata)
    if backend is not None:
        if simulate_interruption_after_bytes is not None:
            interrupted_bytes = package_bytes[:simulate_interruption_after_bytes]
            backend.stage_upload(grant.provider, safe_metadata, interrupted_bytes)
            backend.abort_upload(grant.provider, manifest.snapshot_id)
            raise CloudBoundaryError("upload interrupted before commit")
        backend.stage_upload(grant.provider, safe_metadata, package_bytes)
        backend.commit_upload(
            grant.provider,
            manifest.installation_id,
            manifest.snapshot_id,
            expected_package_hash=manifest.package_hash,
        )
        safe_metadata = dict(safe_metadata) | {"upload_status": "uploaded"}
    return UploadResult(
        provider=grant.provider,
        snapshot_id=manifest.snapshot_id,
        metadata=assert_cloud_metadata_safe(safe_metadata),
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


def download_encrypted_snapshot(
    grant: CloudGrant,
    target_path: Path,
    *,
    backend: InMemoryGrantBackend,
) -> DownloadResult:
    if grant.operation != "download":
        raise CloudBoundaryError("grant is not a download grant")
    if grant.is_expired:
        raise CloudBoundaryError("grant has expired")
    assert_no_long_lived_credentials(grant.required_headers)
    if target_path.suffix.lower() != ".wakilibak":
        raise CloudBoundaryError("cloud download boundary only writes encrypted backup packages")

    package_bytes = backend.download_package(
        grant.provider,
        grant.installation_id,
        grant.snapshot_id,
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(package_bytes)
    manifest = read_backup_manifest(target_path)
    if manifest.installation_id != grant.installation_id:
        raise CloudBoundaryError("downloaded package installation does not match grant")
    if manifest.snapshot_id != grant.snapshot_id:
        raise CloudBoundaryError("downloaded package snapshot does not match grant")
    return DownloadResult(
        provider=grant.provider,
        snapshot_id=grant.snapshot_id,
        path=target_path,
        downloaded_bytes=len(package_bytes),
    )


def restore_cloud_snapshot_drill(
    grant: CloudGrant,
    download_path: Path,
    restore_root: Path,
    *,
    recovery_key: str,
    backend: InMemoryGrantBackend,
) -> CloudRestoreDrillResult:
    from backup.core import restore_backup_package

    download_result = download_encrypted_snapshot(
        grant,
        download_path,
        backend=backend,
    )
    restore_report = restore_backup_package(
        download_result.path,
        restore_root,
        recovery_key=recovery_key,
    )
    return CloudRestoreDrillResult(
        provider=grant.provider,
        snapshot_id=grant.snapshot_id,
        downloaded_path=download_result.path,
        restored_path=restore_report.restored_path,
        restored_file_count=restore_report.restored_file_count,
        verified=restore_report.verified,
    )


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
    for key_path, _value in _walk_mapping(payload):
        lowered = key_path.lower()
        if any(name in lowered for name in CREDENTIAL_FIELD_NAMES):
            raise CloudBoundaryError(f"payload contains cloud credentials: {key_path}")


def _create_grant(
    provider: CloudProvider,
    operation: GrantOperation,
    installation_id: str,
    snapshot_id: str,
) -> CloudGrant:
    if provider not in {"aws", "azure", "gcp"}:
        raise CloudBoundaryError(f"unsupported provider: {provider}")
    expires_at = datetime.now(UTC) + timedelta(minutes=15)
    url = {
        "aws": f"https://s3-presigned.example.invalid/upload/{snapshot_id}",
        "azure": f"https://blob-grants.example.invalid/container/{snapshot_id}",
        "gcp": f"https://storage.googleapis.example.invalid/upload/{snapshot_id}",
    }[provider]
    grant = CloudGrant(
        provider=provider,
        operation=operation,
        installation_id=installation_id,
        snapshot_id=snapshot_id,
        url=url,
        expires_at=expires_at,
        required_headers={"x-wakili-installation-id": installation_id},
    )
    assert_provider_grant_contract(grant)
    return grant


def assert_provider_grant_contract(grant: CloudGrant) -> None:
    expected_url_markers = {
        "aws": "s3-presigned.example.invalid",
        "azure": "blob-grants.example.invalid",
        "gcp": "storage.googleapis.example.invalid",
    }
    marker = expected_url_markers[grant.provider]
    if marker not in grant.url:
        raise CloudBoundaryError(f"{grant.provider} grant URL does not match provider contract")
    if grant.operation not in {"upload", "download", "delete"}:
        raise CloudBoundaryError(f"unsupported grant operation: {grant.operation}")
    if grant.is_expired:
        raise CloudBoundaryError("grant is expired")
    if "x-wakili-installation-id" not in grant.required_headers:
        raise CloudBoundaryError("grant is missing installation binding header")
    assert_no_long_lived_credentials(grant.to_mapping())


def _walk_mapping(value: object, *, prefix: str = "") -> tuple[tuple[str, object], ...]:
    items: list[tuple[str, object]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_path = f"{prefix}.{key}" if prefix else str(key)
            items.append((key_path, child))
            items.extend(_walk_mapping(child, prefix=key_path))
    elif isinstance(value, list | tuple):
        for index, child in enumerate(value):
            items.extend(_walk_mapping(child, prefix=f"{prefix}[{index}]"))
    return tuple(items)


def _package_hash_from_bytes(value: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(value)) as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    except (KeyError, OSError, ValueError, zipfile.BadZipFile) as exc:
        raise CloudBoundaryError("pending upload is not a readable backup package") from exc
    return str(manifest["package_hash"])
