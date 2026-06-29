"""Encrypted local vault storage."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

SCHEMA_VERSION = "1"
KDF_ITERATIONS = 390_000
KEY_LENGTH_BYTES = 32
VERIFIER_PLAINTEXT = b"document-vault-ingestion-engine-v1"


class VaultError(Exception):
    """Base vault failure."""


class InvalidRecoveryKeyError(VaultError):
    """Raised when a recovery key cannot unlock the vault."""


class ObjectNotFoundError(VaultError):
    """Raised when an encrypted vault object cannot be found."""


@dataclass(frozen=True)
class VaultPaths:
    root: Path
    database: Path
    objects: Path
    search: Path
    quarantine: Path
    backups: Path
    restore_workspaces: Path
    logs: Path

    @classmethod
    def from_root(cls, root: Path) -> VaultPaths:
        return cls(
            root=root,
            database=root / "vault.sqlite",
            objects=root / "objects",
            search=root / "search",
            quarantine=root / "quarantine",
            backups=root / "backups",
            restore_workspaces=root / "restore-workspaces",
            logs=root / "logs",
        )

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for path in (
            self.objects,
            self.search,
            self.quarantine,
            self.backups,
            self.restore_workspaces,
            self.logs,
        ):
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class StoredObject:
    object_id: str
    sha256: str
    size_bytes: int
    content_type: str
    original_name: str
    object_path: Path
    created_at: datetime


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    event_type: str
    object_id: str | None
    actor: str
    created_at: datetime
    details: dict[str, object]


class VaultSession:
    """Unlocked vault session backed by SQLite metadata and AES-GCM objects."""

    def __init__(self, paths: VaultPaths, key: bytes) -> None:
        self.paths = paths
        self._key = key

    def write_object(
        self,
        plaintext: bytes,
        *,
        original_name: str,
        content_type: str,
        actor: str = "system",
    ) -> StoredObject:
        object_id = str(uuid4())
        now = _utc_now()
        sha256 = hashlib.sha256(plaintext).hexdigest()
        nonce = os.urandom(12)
        encrypted = AESGCM(self._key).encrypt(nonce, plaintext, object_id.encode("utf-8"))
        relative_path = Path(object_id[:2]) / f"{object_id}.vaultobj"
        object_path = self.paths.objects / relative_path
        object_path.parent.mkdir(parents=True, exist_ok=True)
        object_path.write_bytes(encrypted)

        with _connect(self.paths.database) as connection:
            connection.execute(
                """
                INSERT INTO vault_objects (
                    object_id, sha256, size_bytes, content_type, original_name,
                    object_path, nonce_b64, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    object_id,
                    sha256,
                    len(plaintext),
                    content_type,
                    original_name,
                    str(relative_path).replace("\\", "/"),
                    _b64encode(nonce),
                    _datetime_to_text(now),
                ),
            )
            _append_audit_event(
                connection,
                event_type="object_stored",
                object_id=object_id,
                actor=actor,
                details={
                    "sha256": sha256,
                    "size_bytes": len(plaintext),
                    "content_type": content_type,
                },
            )

        return StoredObject(
            object_id=object_id,
            sha256=sha256,
            size_bytes=len(plaintext),
            content_type=content_type,
            original_name=original_name,
            object_path=object_path,
            created_at=now,
        )

    def read_object(self, object_id: str) -> bytes:
        with _connect(self.paths.database) as connection:
            row = connection.execute(
                """
                SELECT object_path, nonce_b64
                FROM vault_objects
                WHERE object_id = ?
                """,
                (object_id,),
            ).fetchone()

        if row is None:
            raise ObjectNotFoundError(f"vault object does not exist: {object_id}")

        object_path = self.paths.objects / str(row["object_path"])
        try:
            encrypted = object_path.read_bytes()
            nonce = _b64decode(str(row["nonce_b64"]))
            return AESGCM(self._key).decrypt(nonce, encrypted, object_id.encode("utf-8"))
        except (InvalidTag, FileNotFoundError) as exc:
            raise InvalidRecoveryKeyError("vault object could not be decrypted") from exc

    def get_object(self, object_id: str) -> StoredObject:
        with _connect(self.paths.database) as connection:
            row = connection.execute(
                """
                SELECT object_id, sha256, size_bytes, content_type, original_name,
                       object_path, created_at
                FROM vault_objects
                WHERE object_id = ?
                """,
                (object_id,),
            ).fetchone()

        if row is None:
            raise ObjectNotFoundError(f"vault object does not exist: {object_id}")

        return StoredObject(
            object_id=str(row["object_id"]),
            sha256=str(row["sha256"]),
            size_bytes=int(row["size_bytes"]),
            content_type=str(row["content_type"]),
            original_name=str(row["original_name"]),
            object_path=self.paths.objects / str(row["object_path"]),
            created_at=_parse_datetime(str(row["created_at"])),
        )

    def audit_events(self) -> list[AuditEvent]:
        with _connect(self.paths.database) as connection:
            rows = connection.execute(
                """
                SELECT event_id, event_type, object_id, actor, created_at, details_json
                FROM audit_events
                ORDER BY created_at ASC, event_id ASC
                """
            ).fetchall()

        return [
            AuditEvent(
                event_id=str(row["event_id"]),
                event_type=str(row["event_type"]),
                object_id=str(row["object_id"]) if row["object_id"] is not None else None,
                actor=str(row["actor"]),
                created_at=_parse_datetime(str(row["created_at"])),
                details=json.loads(str(row["details_json"])),
            )
            for row in rows
        ]

    def record_audit_event(
        self,
        *,
        event_type: str,
        object_id: str | None = None,
        actor: str = "system",
        details: dict[str, object] | None = None,
    ) -> None:
        """Record a non-object workflow event in the local audit ledger."""

        with _connect(self.paths.database) as connection:
            _append_audit_event(
                connection,
                event_type=event_type,
                object_id=object_id,
                actor=actor,
                details=details or {},
            )


def initialize_vault(root: Path, recovery_key: str) -> VaultSession:
    """Create or unlock a vault at the supplied root path."""

    paths = VaultPaths.from_root(root)
    paths.ensure()
    new_database = not paths.database.exists()
    with _connect(paths.database) as connection:
        _create_schema(connection)
        if new_database or _get_config(connection, "schema_version") is None:
            _bootstrap_config(connection, recovery_key)
            _append_audit_event(
                connection,
                event_type="vault_initialized",
                object_id=None,
                actor="system",
                details={"schema_version": SCHEMA_VERSION},
            )
        key = _unlock_key(connection, recovery_key)
    return VaultSession(paths, key)


def open_vault(root: Path, recovery_key: str) -> VaultSession:
    """Unlock an existing vault."""

    paths = VaultPaths.from_root(root)
    if not paths.database.exists():
        raise VaultError(f"vault database does not exist: {paths.database}")
    with _connect(paths.database) as connection:
        key = _unlock_key(connection, recovery_key)
    return VaultSession(paths, key)


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS vault_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vault_objects (
            object_id TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            content_type TEXT NOT NULL,
            original_name TEXT NOT NULL,
            object_path TEXT NOT NULL,
            nonce_b64 TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            object_id TEXT,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL,
            details_json TEXT NOT NULL
        );
        """
    )


def _bootstrap_config(connection: sqlite3.Connection, recovery_key: str) -> None:
    salt = os.urandom(16)
    key = _derive_key(recovery_key, salt)
    verifier_nonce = os.urandom(12)
    verifier_ciphertext = AESGCM(key).encrypt(verifier_nonce, VERIFIER_PLAINTEXT, None)
    values = {
        "schema_version": SCHEMA_VERSION,
        "kdf_name": "PBKDF2HMAC-SHA256",
        "kdf_iterations": str(KDF_ITERATIONS),
        "salt_b64": _b64encode(salt),
        "verifier_nonce_b64": _b64encode(verifier_nonce),
        "verifier_ciphertext_b64": _b64encode(verifier_ciphertext),
        "created_at": _datetime_to_text(_utc_now()),
    }
    connection.executemany(
        """
        INSERT OR REPLACE INTO vault_config (key, value)
        VALUES (?, ?)
        """,
        values.items(),
    )


def _unlock_key(connection: sqlite3.Connection, recovery_key: str) -> bytes:
    salt = _b64decode(_require_config(connection, "salt_b64"))
    key = _derive_key(recovery_key, salt)
    verifier_nonce = _b64decode(_require_config(connection, "verifier_nonce_b64"))
    verifier_ciphertext = _b64decode(_require_config(connection, "verifier_ciphertext_b64"))
    try:
        plaintext = AESGCM(key).decrypt(verifier_nonce, verifier_ciphertext, None)
    except InvalidTag as exc:
        raise InvalidRecoveryKeyError("recovery key could not unlock the vault") from exc
    if plaintext != VERIFIER_PLAINTEXT:
        raise InvalidRecoveryKeyError("recovery key verifier mismatch")
    return key


def _derive_key(recovery_key: str, salt: bytes) -> bytes:
    if not recovery_key:
        raise InvalidRecoveryKeyError("recovery key cannot be empty")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_LENGTH_BYTES,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(recovery_key.encode("utf-8"))


def _append_audit_event(
    connection: sqlite3.Connection,
    *,
    event_type: str,
    object_id: str | None,
    actor: str,
    details: dict[str, object],
) -> None:
    connection.execute(
        """
        INSERT INTO audit_events (
            event_id, event_type, object_id, actor, created_at, details_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            event_type,
            object_id,
            actor,
            _datetime_to_text(_utc_now()),
            json.dumps(details, sort_keys=True, separators=(",", ":")),
        ),
    )


@contextmanager
def _connect(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _get_config(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute("SELECT value FROM vault_config WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    return str(row["value"])


def _require_config(connection: sqlite3.Connection, key: str) -> str:
    value = _get_config(connection, key)
    if value is None:
        raise VaultError(f"vault config missing required key: {key}")
    return value


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _datetime_to_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)
