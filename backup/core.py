"""Encrypted local backup packages and restore drills."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

APP_VERSION = "0.1.0"
BACKUP_SCHEMA_VERSION = "1"
KDF_ITERATIONS = 390_000
KEY_LENGTH_BYTES = 32


class BackupError(Exception):
    """Base backup failure."""


class InvalidBackupKeyError(BackupError):
    """Raised when a recovery key cannot decrypt a backup package."""


@dataclass(frozen=True)
class BackupManifest:
    installation_id: str
    snapshot_id: str
    schema_version: str
    app_version: str
    created_at: datetime
    package_hash: str
    payload_hash: str
    encrypted_payload_hash: str
    file_count: int
    package_size_bytes: int

    def to_mapping(self) -> dict[str, object]:
        return {
            "installation_id": self.installation_id,
            "snapshot_id": self.snapshot_id,
            "schema_version": self.schema_version,
            "app_version": self.app_version,
            "created_at": _datetime_to_text(self.created_at),
            "package_hash": self.package_hash,
            "payload_hash": self.payload_hash,
            "encrypted_payload_hash": self.encrypted_payload_hash,
            "file_count": self.file_count,
            "package_size_bytes": self.package_size_bytes,
        }


@dataclass(frozen=True)
class BackupPackage:
    path: Path
    manifest: BackupManifest


@dataclass(frozen=True)
class RestoreReport:
    snapshot_id: str
    restored_path: Path
    restored_file_count: int
    verified: bool


def create_local_backup(
    vault_root: Path,
    backup_path: Path,
    *,
    recovery_key: str,
    installation_id: str,
) -> BackupPackage:
    snapshot_id = str(uuid4())
    created_at = _utc_now()
    entries = _collect_vault_files(vault_root)
    payload = _build_payload_zip(vault_root, entries)
    payload_hash = _sha256(payload)
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_backup_key(recovery_key, salt)
    encrypted_payload = AESGCM(key).encrypt(nonce, payload, snapshot_id.encode("utf-8"))
    encrypted_payload_hash = _sha256(encrypted_payload)

    package_hash = _package_content_hash(
        salt=salt,
        nonce=nonce,
        encrypted_payload=encrypted_payload,
        payload_hash=payload_hash,
        encrypted_payload_hash=encrypted_payload_hash,
    )
    manifest_mapping = {
        "installation_id": installation_id,
        "snapshot_id": snapshot_id,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "app_version": APP_VERSION,
        "created_at": _datetime_to_text(created_at),
        "package_hash": package_hash,
        "payload_hash": payload_hash,
        "encrypted_payload_hash": encrypted_payload_hash,
        "file_count": len(entries),
        "package_size_bytes": 0,
    }
    package_bytes = b""
    for _ in range(5):
        package_bytes = _build_package_bytes(
            manifest=manifest_mapping,
            salt=salt,
            nonce=nonce,
            encrypted_payload=encrypted_payload,
        )
        package_size_bytes = len(package_bytes)
        if manifest_mapping["package_size_bytes"] == package_size_bytes:
            break
        manifest_mapping = manifest_mapping | {"package_size_bytes": package_size_bytes}
    else:
        raise BackupError("backup manifest package size did not stabilize")

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_bytes(package_bytes)
    manifest = _manifest_from_mapping(manifest_mapping)
    return BackupPackage(path=backup_path, manifest=manifest)


def restore_backup_package(
    backup_path: Path,
    restore_root: Path,
    *,
    recovery_key: str,
) -> RestoreReport:
    package_bytes = backup_path.read_bytes()
    with zipfile.ZipFile(BytesIO(package_bytes)) as archive:
        manifest_mapping = json.loads(archive.read("manifest.json").decode("utf-8"))
        salt = base64.b64decode(archive.read("salt.b64"), validate=True)
        nonce = base64.b64decode(archive.read("nonce.b64"), validate=True)
        encrypted_payload = archive.read("payload.bin")

    expected_package_hash = _package_content_hash(
        salt=salt,
        nonce=nonce,
        encrypted_payload=encrypted_payload,
        payload_hash=str(manifest_mapping["payload_hash"]),
        encrypted_payload_hash=str(manifest_mapping["encrypted_payload_hash"]),
    )
    if manifest_mapping["package_hash"] != expected_package_hash:
        raise BackupError("backup package hash does not match manifest")
    if manifest_mapping["encrypted_payload_hash"] != _sha256(encrypted_payload):
        raise BackupError("encrypted payload hash does not match manifest")

    key = _derive_backup_key(recovery_key, salt)
    try:
        payload = AESGCM(key).decrypt(
            nonce,
            encrypted_payload,
            str(manifest_mapping["snapshot_id"]).encode("utf-8"),
        )
    except InvalidTag as exc:
        raise InvalidBackupKeyError("recovery key could not decrypt backup package") from exc

    if manifest_mapping["payload_hash"] != _sha256(payload):
        raise BackupError("decrypted payload hash does not match manifest")

    target = restore_root / str(manifest_mapping["snapshot_id"])
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BytesIO(payload)) as payload_archive:
        payload_archive.extractall(target)

    restored_file_count = len([path for path in target.rglob("*") if path.is_file()])
    _verify_restored_metadata(target)
    _write_restore_report(target, manifest_mapping, restored_file_count)
    return RestoreReport(
        snapshot_id=str(manifest_mapping["snapshot_id"]),
        restored_path=target,
        restored_file_count=restored_file_count,
        verified=True,
    )


def read_backup_manifest(backup_path: Path) -> BackupManifest:
    with zipfile.ZipFile(backup_path) as archive:
        manifest_mapping = json.loads(archive.read("manifest.json").decode("utf-8"))
    return _manifest_from_mapping(manifest_mapping)


def _collect_vault_files(vault_root: Path) -> list[Path]:
    ignored_parts = {"backups", "restore-workspaces"}
    files: list[Path] = []
    for path in sorted(vault_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(vault_root)
        if relative.parts and relative.parts[0] in ignored_parts:
            continue
        files.append(relative)
    return files


def _build_payload_zip(vault_root: Path, entries: list[Path]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative_path in entries:
            archive.write(vault_root / relative_path, relative_path.as_posix())
    return output.getvalue()


def _build_package_bytes(
    *,
    manifest: dict[str, object],
    salt: bytes,
    nonce: bytes,
    encrypted_payload: bytes,
) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"),
        )
        archive.writestr("salt.b64", base64.b64encode(salt))
        archive.writestr("nonce.b64", base64.b64encode(nonce))
        archive.writestr("payload.bin", encrypted_payload)
    return output.getvalue()


def _derive_backup_key(recovery_key: str, salt: bytes) -> bytes:
    if not recovery_key:
        raise InvalidBackupKeyError("recovery key cannot be empty")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_LENGTH_BYTES,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(recovery_key.encode("utf-8"))


def _verify_restored_metadata(target: Path) -> None:
    database = target / "vault.sqlite"
    if not database.exists():
        raise BackupError("restored vault database is missing")
    with _connect(database) as connection:
        connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()


def _write_restore_report(
    target: Path,
    manifest_mapping: dict[str, object],
    restored_file_count: int,
) -> None:
    report = {
        "snapshot_id": manifest_mapping["snapshot_id"],
        "restored_file_count": restored_file_count,
        "verified": True,
        "created_at": _datetime_to_text(_utc_now()),
    }
    (target / "restore-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _manifest_from_mapping(value: dict[str, object]) -> BackupManifest:
    return BackupManifest(
        installation_id=str(value["installation_id"]),
        snapshot_id=str(value["snapshot_id"]),
        schema_version=str(value["schema_version"]),
        app_version=str(value["app_version"]),
        created_at=_parse_datetime(str(value["created_at"])),
        package_hash=str(value["package_hash"]),
        payload_hash=str(value["payload_hash"]),
        encrypted_payload_hash=str(value["encrypted_payload_hash"]),
        file_count=int(value["file_count"]),
        package_size_bytes=int(value["package_size_bytes"]),
    )


@contextmanager
def _connect(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database_path)
    try:
        yield connection
    finally:
        connection.close()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _package_content_hash(
    *,
    salt: bytes,
    nonce: bytes,
    encrypted_payload: bytes,
    payload_hash: str,
    encrypted_payload_hash: str,
) -> str:
    hasher = hashlib.sha256()
    hasher.update(b"document-vault-backup-v1")
    hasher.update(salt)
    hasher.update(nonce)
    hasher.update(encrypted_payload)
    hasher.update(payload_hash.encode("utf-8"))
    hasher.update(encrypted_payload_hash.encode("utf-8"))
    return hasher.hexdigest()


def _datetime_to_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)
