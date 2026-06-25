"""Document intake validation and quarantine records."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ACCEPTED_STATUS = "accepted"
DUPLICATE_STATUS = "duplicate"
REJECTED_STATUS = "rejected"
LARGE_FILE_WARNING_BYTES = 100 * 1024 * 1024

SUPPORTED_EXTENSIONS = {
    "pdf": {".pdf"},
    "docx": {".docx"},
    "jpeg": {".jpg", ".jpeg"},
    "png": {".png"},
    "tiff": {".tif", ".tiff"},
}


class IntakeError(Exception):
    """Base intake failure."""


@dataclass(frozen=True)
class IntakeRecord:
    intake_id: str
    source_sha256: str
    detected_file_type: str
    original_extension: str
    quarantine_path: Path
    status: str
    warnings: tuple[str, ...]
    size_bytes: int
    created_at: datetime


def import_document(vault_root: Path, source_path: Path) -> IntakeRecord:
    """Copy a source file to quarantine, validate it, and persist an intake record."""

    if not source_path.exists() or not source_path.is_file():
        raise IntakeError(f"source file does not exist: {source_path}")

    database_path = vault_root / "vault.sqlite"
    quarantine_root = vault_root / "quarantine"
    quarantine_root.mkdir(parents=True, exist_ok=True)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    source_bytes = source_path.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    detected_file_type, detection_warnings = detect_file_type(source_path, source_bytes)
    warnings = list(detection_warnings)
    size_bytes = len(source_bytes)

    if size_bytes == 0:
        warnings.append("empty_document")
    if size_bytes > LARGE_FILE_WARNING_BYTES:
        warnings.append("large_file")

    status = ACCEPTED_STATUS
    if detected_file_type == "unsupported" or "corrupt_file" in warnings or size_bytes == 0:
        status = REJECTED_STATUS

    with _connect(database_path) as connection:
        _create_schema(connection)
        duplicate_exists = _has_prior_accepted_hash(connection, source_sha256)
        if duplicate_exists:
            warnings.append("duplicate_source_hash")
            status = DUPLICATE_STATUS

        intake_id = str(uuid4())
        quarantine_relative_path = Path("quarantine") / f"{intake_id}{source_path.suffix.lower()}"
        quarantine_path = vault_root / quarantine_relative_path
        shutil.copy2(source_path, quarantine_path)

        record = IntakeRecord(
            intake_id=intake_id,
            source_sha256=source_sha256,
            detected_file_type=detected_file_type,
            original_extension=source_path.suffix.lower(),
            quarantine_path=quarantine_path,
            status=status,
            warnings=tuple(dict.fromkeys(warnings)),
            size_bytes=size_bytes,
            created_at=_utc_now(),
        )
        connection.execute(
            """
            INSERT INTO intake_records (
                intake_id, source_sha256, detected_file_type, original_extension,
                quarantine_path, status, warnings_json, size_bytes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.intake_id,
                record.source_sha256,
                record.detected_file_type,
                record.original_extension,
                str(quarantine_relative_path).replace("\\", "/"),
                record.status,
                json.dumps(list(record.warnings), separators=(",", ":")),
                record.size_bytes,
                _datetime_to_text(record.created_at),
            ),
        )

    return record


def detect_file_type(source_path: Path, source_bytes: bytes) -> tuple[str, tuple[str, ...]]:
    """Detect supported legal document file types by signature and extension."""

    warnings: list[str] = []
    extension = source_path.suffix.lower()
    detected_file_type, signature_warnings = _signature_type(source_path, source_bytes)
    warnings.extend(signature_warnings)
    if detected_file_type == "unsupported":
        warnings.append("unsupported_type")
        return detected_file_type, tuple(warnings)

    expected_extensions = SUPPORTED_EXTENSIONS[detected_file_type]
    if extension not in expected_extensions:
        warnings.append("extension_signature_mismatch")

    return detected_file_type, tuple(warnings)


def list_intake_records(vault_root: Path) -> list[IntakeRecord]:
    database_path = vault_root / "vault.sqlite"
    if not database_path.exists():
        return []
    with _connect(database_path) as connection:
        _create_schema(connection)
        rows = connection.execute(
            """
            SELECT intake_id, source_sha256, detected_file_type, original_extension,
                   quarantine_path, status, warnings_json, size_bytes, created_at
            FROM intake_records
            ORDER BY created_at ASC, intake_id ASC
            """
        ).fetchall()
    return [_row_to_record(vault_root, row) for row in rows]


def _signature_type(source_path: Path, source_bytes: bytes) -> tuple[str, tuple[str, ...]]:
    if source_bytes.startswith(b"%PDF-"):
        return "pdf", ()
    if source_bytes.startswith(b"\xff\xd8\xff"):
        return "jpeg", ()
    if source_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", ()
    if source_bytes.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff", ()
    if source_bytes.startswith(b"PK\x03\x04"):
        return _detect_docx(source_path)
    return "unsupported", ()


def _detect_docx(source_path: Path) -> tuple[str, tuple[str, ...]]:
    try:
        with zipfile.ZipFile(source_path) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        return "unsupported", ("corrupt_file",)
    if "[Content_Types].xml" in names and "word/document.xml" in names:
        return "docx", ()
    return "unsupported", ()


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS intake_records (
            intake_id TEXT PRIMARY KEY,
            source_sha256 TEXT NOT NULL,
            detected_file_type TEXT NOT NULL,
            original_extension TEXT NOT NULL,
            quarantine_path TEXT NOT NULL,
            status TEXT NOT NULL,
            warnings_json TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_intake_records_source_sha256
        ON intake_records (source_sha256)
        """
    )


def _has_prior_accepted_hash(connection: sqlite3.Connection, source_sha256: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM intake_records
        WHERE source_sha256 = ?
          AND status = ?
        LIMIT 1
        """,
        (source_sha256, ACCEPTED_STATUS),
    ).fetchone()
    return row is not None


def _row_to_record(vault_root: Path, row: sqlite3.Row) -> IntakeRecord:
    return IntakeRecord(
        intake_id=str(row["intake_id"]),
        source_sha256=str(row["source_sha256"]),
        detected_file_type=str(row["detected_file_type"]),
        original_extension=str(row["original_extension"]),
        quarantine_path=vault_root / str(row["quarantine_path"]),
        status=str(row["status"]),
        warnings=tuple(json.loads(str(row["warnings_json"]))),
        size_bytes=int(row["size_bytes"]),
        created_at=_parse_datetime(str(row["created_at"])),
    )


@contextmanager
def _connect(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _datetime_to_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)
