"""Matter, document versioning, and SQLite FTS search."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

IMPORTED_STATUS = "imported"
DRAFT_STATUS = "draft"
REVIEWED_STATUS = "reviewed"
APPROVED_STATUS = "approved"
SIGNED_STATUS = "signed"
FILED_STATUS = "filed"
SERVED_STATUS = "served"
COURT_RETURNED_STATUS = "court_returned"
SUPERSEDED_STATUS = "superseded"
ARCHIVED_STATUS = "archived"

PROTECTED_STATUSES = {FILED_STATUS, SERVED_STATUS, COURT_RETURNED_STATUS, ARCHIVED_STATUS}


class MatterSearchError(Exception):
    """Base matter/search failure."""


@dataclass(frozen=True)
class MatterRecord:
    matter_id: str
    internal_reference: str
    client_name: str
    parties: str
    court: str
    station: str
    case_number: str
    practice_area: str
    responsible_advocate: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    matter_id: str
    title: str
    document_type: str
    lifecycle_status: str
    created_at: datetime


@dataclass(frozen=True)
class DocumentVersionRecord:
    version_id: str
    document_id: str
    version_number: int
    object_id: str
    source_sha256: str
    extracted_text: str
    lifecycle_status: str
    created_at: datetime


@dataclass(frozen=True)
class SearchResult:
    matter_id: str
    document_id: str
    version_id: str
    title: str
    document_type: str
    lifecycle_status: str
    snippet: str


def initialize_search_store(vault_root: Path) -> None:
    with _connect(_database_path(vault_root)) as connection:
        _create_schema(connection)


def create_matter(
    vault_root: Path,
    *,
    internal_reference: str,
    client_name: str,
    parties: str,
    court: str,
    station: str,
    case_number: str,
    practice_area: str,
    responsible_advocate: str,
    status: str = "active",
) -> MatterRecord:
    now = _utc_now()
    matter = MatterRecord(
        matter_id=str(uuid4()),
        internal_reference=internal_reference,
        client_name=client_name,
        parties=parties,
        court=court,
        station=station,
        case_number=case_number,
        practice_area=practice_area,
        responsible_advocate=responsible_advocate,
        status=status,
        created_at=now,
    )
    with _connect(_database_path(vault_root)) as connection:
        _create_schema(connection)
        connection.execute(
            """
            INSERT INTO matters (
                matter_id, internal_reference, client_name, parties, court, station,
                case_number, practice_area, responsible_advocate, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                matter.matter_id,
                matter.internal_reference,
                matter.client_name,
                matter.parties,
                matter.court,
                matter.station,
                matter.case_number,
                matter.practice_area,
                matter.responsible_advocate,
                matter.status,
                _datetime_to_text(matter.created_at),
            ),
        )
    return matter


def create_document(
    vault_root: Path,
    *,
    matter_id: str,
    title: str,
    document_type: str,
    lifecycle_status: str = IMPORTED_STATUS,
) -> DocumentRecord:
    now = _utc_now()
    document = DocumentRecord(
        document_id=str(uuid4()),
        matter_id=matter_id,
        title=title,
        document_type=document_type,
        lifecycle_status=lifecycle_status,
        created_at=now,
    )
    with _connect(_database_path(vault_root)) as connection:
        _create_schema(connection)
        _require_matter(connection, matter_id)
        connection.execute(
            """
            INSERT INTO documents (
                document_id, matter_id, title, document_type, lifecycle_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                document.document_id,
                document.matter_id,
                document.title,
                document.document_type,
                document.lifecycle_status,
                _datetime_to_text(document.created_at),
            ),
        )
    return document


def add_document_version(
    vault_root: Path,
    *,
    document_id: str,
    object_id: str,
    source_sha256: str,
    extracted_text: str,
    lifecycle_status: str,
) -> DocumentVersionRecord:
    now = _utc_now()
    with _connect(_database_path(vault_root)) as connection:
        _create_schema(connection)
        document_row = _require_document(connection, document_id)
        version_number = _next_version_number(connection, document_id)
        version = DocumentVersionRecord(
            version_id=str(uuid4()),
            document_id=document_id,
            version_number=version_number,
            object_id=object_id,
            source_sha256=source_sha256,
            extracted_text=extracted_text,
            lifecycle_status=lifecycle_status,
            created_at=now,
        )
        connection.execute(
            """
            INSERT INTO document_versions (
                version_id, document_id, version_number, object_id, source_sha256,
                extracted_text, lifecycle_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version.version_id,
                version.document_id,
                version.version_number,
                version.object_id,
                version.source_sha256,
                version.extracted_text,
                version.lifecycle_status,
                _datetime_to_text(version.created_at),
            ),
        )
        connection.execute(
            """
            UPDATE documents
            SET lifecycle_status = ?
            WHERE document_id = ?
            """,
            (lifecycle_status, document_id),
        )
        _index_version(connection, version, document_row)
    return version


def search_documents(
    vault_root: Path,
    query: str,
    *,
    matter_id: str | None = None,
    limit: int = 20,
) -> list[SearchResult]:
    with _connect(_database_path(vault_root)) as connection:
        _create_schema(connection)
        if matter_id is None:
            rows = connection.execute(
                """
                SELECT matter_id, document_id, version_id, title, document_type,
                       lifecycle_status,
                       snippet(search_index, 7, '[', ']', ' ... ', 12) AS snippet
                FROM search_index
                WHERE search_index MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT matter_id, document_id, version_id, title, document_type,
                       lifecycle_status,
                       snippet(search_index, 7, '[', ']', ' ... ', 12) AS snippet
                FROM search_index
                WHERE search_index MATCH ?
                  AND matter_id = ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, matter_id, limit),
            ).fetchall()
    return [_row_to_search_result(row) for row in rows]


def rebuild_search_index(vault_root: Path) -> None:
    with _connect(_database_path(vault_root)) as connection:
        _create_schema(connection)
        connection.execute("DELETE FROM search_index")
        rows = connection.execute(
            """
            SELECT dv.version_id, dv.document_id, dv.object_id, dv.source_sha256,
                   dv.extracted_text, dv.lifecycle_status, d.matter_id, d.title,
                   d.document_type, m.internal_reference, m.client_name, m.parties,
                   m.court, m.station, m.case_number, m.practice_area
            FROM document_versions dv
            JOIN documents d ON d.document_id = dv.document_id
            JOIN matters m ON m.matter_id = d.matter_id
            """
        ).fetchall()
        for row in rows:
            _index_version_row(connection, row)


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS matters (
            matter_id TEXT PRIMARY KEY,
            internal_reference TEXT NOT NULL,
            client_name TEXT NOT NULL,
            parties TEXT NOT NULL,
            court TEXT NOT NULL,
            station TEXT NOT NULL,
            case_number TEXT NOT NULL,
            practice_area TEXT NOT NULL,
            responsible_advocate TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS documents (
            document_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL REFERENCES matters(matter_id),
            title TEXT NOT NULL,
            document_type TEXT NOT NULL,
            lifecycle_status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS document_versions (
            version_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES documents(document_id),
            version_number INTEGER NOT NULL,
            object_id TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            extracted_text TEXT NOT NULL,
            lifecycle_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(document_id, version_number)
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
            matter_id UNINDEXED,
            document_id UNINDEXED,
            version_id UNINDEXED,
            title,
            document_type,
            lifecycle_status,
            matter_metadata,
            extracted_text
        );
        """
    )


def _index_version(
    connection: sqlite3.Connection,
    version: DocumentVersionRecord,
    document_row: sqlite3.Row,
) -> None:
    matter_row = _require_matter(connection, str(document_row["matter_id"]))
    connection.execute(
        """
        INSERT INTO search_index (
            matter_id, document_id, version_id, title, document_type,
            lifecycle_status, matter_metadata, extracted_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(matter_row["matter_id"]),
            version.document_id,
            version.version_id,
            str(document_row["title"]),
            str(document_row["document_type"]),
            version.lifecycle_status,
            _matter_metadata(matter_row),
            version.extracted_text,
        ),
    )


def _index_version_row(connection: sqlite3.Connection, row: sqlite3.Row) -> None:
    metadata = " ".join(
        [
            str(row["internal_reference"]),
            str(row["client_name"]),
            str(row["parties"]),
            str(row["court"]),
            str(row["station"]),
            str(row["case_number"]),
            str(row["practice_area"]),
        ]
    )
    connection.execute(
        """
        INSERT INTO search_index (
            matter_id, document_id, version_id, title, document_type,
            lifecycle_status, matter_metadata, extracted_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(row["matter_id"]),
            str(row["document_id"]),
            str(row["version_id"]),
            str(row["title"]),
            str(row["document_type"]),
            str(row["lifecycle_status"]),
            metadata,
            str(row["extracted_text"]),
        ),
    )


def _matter_metadata(matter_row: sqlite3.Row) -> str:
    return " ".join(
        [
            str(matter_row["internal_reference"]),
            str(matter_row["client_name"]),
            str(matter_row["parties"]),
            str(matter_row["court"]),
            str(matter_row["station"]),
            str(matter_row["case_number"]),
            str(matter_row["practice_area"]),
        ]
    )


def _next_version_number(connection: sqlite3.Connection, document_id: str) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(MAX(version_number), 0) + 1 AS next_version
        FROM document_versions
        WHERE document_id = ?
        """,
        (document_id,),
    ).fetchone()
    return int(row["next_version"])


def _require_matter(connection: sqlite3.Connection, matter_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM matters WHERE matter_id = ?",
        (matter_id,),
    ).fetchone()
    if row is None:
        raise MatterSearchError(f"matter does not exist: {matter_id}")
    return row


def _require_document(connection: sqlite3.Connection, document_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM documents WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    if row is None:
        raise MatterSearchError(f"document does not exist: {document_id}")
    return row


def _row_to_search_result(row: sqlite3.Row) -> SearchResult:
    return SearchResult(
        matter_id=str(row["matter_id"]),
        document_id=str(row["document_id"]),
        version_id=str(row["version_id"]),
        title=str(row["title"]),
        document_type=str(row["document_type"]),
        lifecycle_status=str(row["lifecycle_status"]),
        snippet=str(row["snippet"]),
    )


def _database_path(vault_root: Path) -> Path:
    return vault_root / "vault.sqlite"


@contextmanager
def _connect(database_path: Path) -> Iterator[sqlite3.Connection]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _datetime_to_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(UTC)
