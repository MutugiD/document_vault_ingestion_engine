"""Firm-hosted WakiliOS backend service layer."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from rag import build_answer_packet, build_rag_index
from search import (
    FILED_STATUS,
    add_document_version,
    create_document,
    create_matter,
    initialize_search_store,
)
from vault import initialize_vault

ADMIN_ROLE = "admin"
ADVOCATE_ROLE = "advocate"
CLERK_ROLE = "clerk"
ACCOUNTS_ROLE = "accounts"
READ_ONLY_ROLE = "read_only"
STANDARD_ROLES = frozenset(
    {ADMIN_ROLE, ADVOCATE_ROLE, CLERK_ROLE, ACCOUNTS_ROLE, READ_ONLY_ROLE}
)
WRITE_ROLES = frozenset({ADMIN_ROLE, ADVOCATE_ROLE, CLERK_ROLE, ACCOUNTS_ROLE})
SUMMARY_ROLES = frozenset({ADMIN_ROLE, ADVOCATE_ROLE})
DOCUMENT_ROLES = frozenset({ADMIN_ROLE, ADVOCATE_ROLE, CLERK_ROLE})
ACCOUNTS_ROLES = frozenset({ADMIN_ROLE, ACCOUNTS_ROLE})
SESSION_TTL_MINUTES = 90
OFFLINE_CACHE_SCHEMA_VERSION = "1"


class WakiliOSError(Exception):
    """Base WakiliOS failure."""


class PermissionDeniedError(WakiliOSError):
    """Raised when a role cannot perform an action."""


class AuthenticationError(WakiliOSError):
    """Raised when login or token validation fails."""


class SeatLimitError(WakiliOSError):
    """Raised when a firm has no remaining seats."""


@dataclass(frozen=True)
class AuthSession:
    token: str
    user_id: str
    username: str
    role: str
    expires_at: datetime


@dataclass(frozen=True)
class OfflineCache:
    schema_version: str
    created_at: datetime
    mode: str
    matters: tuple[dict[str, object], ...]

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "created_at": _datetime_to_text(self.created_at),
            "mode": self.mode,
            "matters": list(self.matters),
        }


class WakiliOSBackend:
    """Server-side firm backend backed by SQLite WAL and encrypted vault objects."""

    def __init__(self, root: Path, vault_passphrase: str) -> None:
        self.root = root
        self.vault_root = root / "firm-vault"
        self.database_path = self.vault_root / "vault.sqlite"
        self.root.mkdir(parents=True, exist_ok=True)
        self.vault_session = initialize_vault(self.vault_root, vault_passphrase)
        initialize_search_store(self.vault_root)
        with _connect(self.database_path) as connection:
            _create_schema(connection)
            connection.execute("PRAGMA journal_mode = WAL")

    def login(self, username: str, password: str) -> AuthSession:
        with _connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT user_id, username, role, password_hash, password_salt_b64, active
                FROM firm_users
                WHERE username = ?
                """,
                (username,),
            ).fetchone()
            if row is None or int(row["active"]) != 1:
                raise AuthenticationError("invalid username or password")
            if not _verify_password(
                password,
                str(row["password_salt_b64"]),
                str(row["password_hash"]),
            ):
                raise AuthenticationError("invalid username or password")
            expires_at = _utc_now() + timedelta(minutes=SESSION_TTL_MINUTES)
            token = _sign_session_token(
                connection,
                user_id=str(row["user_id"]),
                role=str(row["role"]),
                expires_at=expires_at,
            )
        return AuthSession(
            token=token,
            user_id=str(row["user_id"]),
            username=str(row["username"]),
            role=str(row["role"]),
            expires_at=expires_at,
        )

    def create_user(
        self,
        token: str,
        *,
        username: str,
        password: str,
        role: str,
        display_name: str,
    ) -> dict[str, object]:
        actor = self.require_role(token, {ADMIN_ROLE})
        if role not in STANDARD_ROLES:
            raise WakiliOSError(f"unsupported role: {role}")
        with _connect(self.database_path) as connection:
            _enforce_seat_limit(connection)
            user_id = str(uuid4())
            salt_b64, password_hash = _hash_password(password)
            connection.execute(
                """
                INSERT INTO firm_users (
                    user_id, username, display_name, role, password_hash,
                    password_salt_b64, active, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    user_id,
                    username,
                    display_name,
                    role,
                    password_hash,
                    salt_b64,
                    _datetime_to_text(_utc_now()),
                ),
            )
            _audit(
                connection,
                actor_id=actor["user_id"],
                event_type="firm_user_created",
                target_id=user_id,
                details={"role": role},
            )
        return {
            "user_id": user_id,
            "username": username,
            "role": role,
            "display_name": display_name,
        }

    def create_litigation_matter(
        self,
        token: str,
        *,
        internal_reference: str,
        client_name: str,
        parties: str,
        court: str,
        station: str,
        case_number: str,
        practice_area: str,
        responsible_advocate: str,
        filing_status: str,
        filing_date: str,
        summary: str = "",
    ) -> dict[str, object]:
        actor = self.require_role(token, WRITE_ROLES)
        matter = create_matter(
            self.vault_root,
            internal_reference=internal_reference,
            client_name=client_name,
            parties=parties,
            court=court,
            station=station,
            case_number=case_number,
            practice_area=practice_area,
            responsible_advocate=responsible_advocate,
            status="active",
        )
        with _connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO wakilios_matter_details (
                    matter_id, filing_status, filing_date, summary, created_by
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (matter.matter_id, filing_status, filing_date, summary, actor["user_id"]),
            )
            connection.execute(
                """
                INSERT INTO matter_assignments (assignment_id, matter_id, user_id, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    matter.matter_id,
                    actor["user_id"],
                    actor["role"],
                    _datetime_to_text(_utc_now()),
                ),
            )
            _audit(
                connection,
                actor_id=actor["user_id"],
                event_type="matter_created",
                target_id=matter.matter_id,
                details={"internal_reference": internal_reference},
            )
        return self.get_matter(token, matter.matter_id)

    def get_matter(self, token: str, matter_id: str) -> dict[str, object]:
        self.require_authenticated(token)
        with _connect(self.database_path) as connection:
            row = _matter_row(connection, matter_id)
            if row is None:
                raise WakiliOSError(f"matter does not exist: {matter_id}")
            return _matter_mapping(row)

    def update_matter_summary(self, token: str, matter_id: str, summary: str) -> dict[str, object]:
        actor = self.require_role(token, SUMMARY_ROLES)
        with _connect(self.database_path) as connection:
            _require_existing_matter(connection, matter_id)
            connection.execute(
                "UPDATE wakilios_matter_details SET summary = ? WHERE matter_id = ?",
                (summary, matter_id),
            )
            _audit(
                connection,
                actor_id=actor["user_id"],
                event_type="matter_summary_updated",
                target_id=matter_id,
                details={"source": "manual"},
            )
        return self.get_matter(token, matter_id)

    def add_party(self, token: str, matter_id: str, **fields: str) -> dict[str, object]:
        return self._insert_tab_record(
            token,
            matter_id,
            required_roles=WRITE_ROLES,
            table="matter_parties",
            id_column="party_id",
            event_type="matter_party_created",
            fields={
                "name": fields["name"],
                "party_role": fields["party_role"],
                "contact_details": fields.get("contact_details", ""),
                "representative": fields.get("representative", ""),
                "notes": fields.get("notes", ""),
            },
        )

    def add_activity(self, token: str, matter_id: str, **fields: object) -> dict[str, object]:
        return self._insert_tab_record(
            token,
            matter_id,
            required_roles=WRITE_ROLES,
            table="matter_activities",
            id_column="activity_id",
            event_type="matter_activity_created",
            fields={
                "activity_type": str(fields["activity_type"]),
                "title": str(fields["title"]),
                "starts_at": str(fields["starts_at"]),
                "court_session": str(fields.get("court_session", "")),
                "status": str(fields.get("status", "scheduled")),
                "notes": str(fields.get("notes", "")),
                "calendar_visible": 1 if bool(fields.get("calendar_visible", True)) else 0,
            },
        )

    def add_lodging(self, token: str, matter_id: str, **fields: str) -> dict[str, object]:
        return self._insert_tab_record(
            token,
            matter_id,
            required_roles=DOCUMENT_ROLES,
            table="lodgings",
            id_column="lodging_id",
            event_type="lodging_created",
            fields={
                "document_kind": fields["document_kind"],
                "party": fields.get("party", ""),
                "due_date": fields.get("due_date", ""),
                "lodged_date": fields.get("lodged_date", ""),
                "filing_status": fields.get("filing_status", "pending"),
                "linked_document_id": fields.get("linked_document_id", ""),
                "filing_reference": fields.get("filing_reference", ""),
            },
        )

    def add_court_decision(self, token: str, matter_id: str, **fields: str) -> dict[str, object]:
        return self._insert_tab_record(
            token,
            matter_id,
            required_roles=SUMMARY_ROLES,
            table="court_decisions",
            id_column="decision_id",
            event_type="court_decision_created",
            fields={
                "decision_type": fields["decision_type"],
                "decision_date": fields["decision_date"],
                "court": fields.get("court", ""),
                "decision_maker": fields.get("decision_maker", ""),
                "outcome": fields.get("outcome", ""),
                "notes": fields.get("notes", ""),
                "linked_document_id": fields.get("linked_document_id", ""),
            },
        )

    def add_fee(self, token: str, matter_id: str, **fields: object) -> dict[str, object]:
        return self._insert_tab_record(
            token,
            matter_id,
            required_roles=ACCOUNTS_ROLES,
            table="fee_entries",
            id_column="fee_id",
            event_type="fee_entry_created",
            fields={
                "fee_type": str(fields["fee_type"]),
                "amount": float(fields["amount"]),
                "currency": str(fields.get("currency", "KES")),
                "paid_by": str(fields.get("paid_by", "")),
                "paid_to": str(fields.get("paid_to", "")),
                "status": str(fields.get("status", "pending")),
                "linked_activity_id": str(fields.get("linked_activity_id", "")),
                "linked_lodging_id": str(fields.get("linked_lodging_id", "")),
            },
        )

    def add_receipt(self, token: str, matter_id: str, **fields: object) -> dict[str, object]:
        return self._insert_tab_record(
            token,
            matter_id,
            required_roles=ACCOUNTS_ROLES,
            table="receipts",
            id_column="receipt_id",
            event_type="receipt_created",
            fields={
                "receipt_number": str(fields["receipt_number"]),
                "issuer": str(fields.get("issuer", "")),
                "payer": str(fields.get("payer", "")),
                "amount": float(fields["amount"]),
                "currency": str(fields.get("currency", "KES")),
                "receipt_date": str(fields["receipt_date"]),
                "linked_fee_id": str(fields.get("linked_fee_id", "")),
                "linked_document_id": str(fields.get("linked_document_id", "")),
            },
        )

    def upload_document(
        self,
        token: str,
        matter_id: str,
        *,
        title: str,
        document_type: str,
        content: bytes,
        original_name: str,
        content_type: str,
        extracted_text: str,
    ) -> dict[str, object]:
        actor = self.require_role(token, DOCUMENT_ROLES)
        with _connect(self.database_path) as connection:
            _require_existing_matter(connection, matter_id)
        stored_object = self.vault_session.write_object(
            content,
            original_name=original_name,
            content_type=content_type,
            actor=str(actor["username"]),
        )
        document = create_document(
            self.vault_root,
            matter_id=matter_id,
            title=title,
            document_type=document_type,
            lifecycle_status=FILED_STATUS,
        )
        version = add_document_version(
            self.vault_root,
            document_id=document.document_id,
            object_id=stored_object.object_id,
            source_sha256=stored_object.sha256,
            extracted_text=extracted_text,
            lifecycle_status=FILED_STATUS,
        )
        build_rag_index(self.vault_root, matter_id=matter_id)
        with _connect(self.database_path) as connection:
            _audit(
                connection,
                actor_id=actor["user_id"],
                event_type="document_uploaded",
                target_id=document.document_id,
                details={"matter_id": matter_id, "document_type": document_type},
            )
        return {
            "document_id": document.document_id,
            "version_id": version.version_id,
            "object_id": stored_object.object_id,
            "title": title,
            "document_type": document_type,
        }

    def generate_ai_summary(
        self,
        token: str,
        matter_id: str,
        *,
        document_id: str,
        question: str = "Summarize the key information in this matter.",
    ) -> dict[str, object]:
        actor = self.require_role(token, SUMMARY_ROLES)
        build_rag_index(self.vault_root, matter_id=matter_id)
        packet = build_answer_packet(self.vault_root, question, matter_id=matter_id, top_k=5)
        if not packet.citations or not packet.grounded_context.strip():
            raise WakiliOSError("AI summary requires cited local matter context")
        summary = _summary_from_context(packet.grounded_context)
        summary_id = str(uuid4())
        with _connect(self.database_path) as connection:
            _require_existing_matter(connection, matter_id)
            connection.execute(
                """
                INSERT INTO document_summaries (
                    summary_id, document_id, matter_id, manual_summary, ai_draft_summary,
                    approval_status, citation_ids_json, generated_by, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary_id,
                    document_id,
                    matter_id,
                    "",
                    summary,
                    "draft",
                    json.dumps([citation.citation_id for citation in packet.citations]),
                    actor["user_id"],
                    _datetime_to_text(_utc_now()),
                ),
            )
            _audit(
                connection,
                actor_id=actor["user_id"],
                event_type="ai_summary_generated",
                target_id=summary_id,
                details={"matter_id": matter_id, "citation_count": len(packet.citations)},
            )
        return {
            "summary_id": summary_id,
            "document_id": document_id,
            "matter_id": matter_id,
            "ai_draft_summary": summary,
            "approval_status": "draft",
            "citation_ids": [citation.citation_id for citation in packet.citations],
        }

    def workspace(self, token: str, matter_id: str) -> dict[str, object]:
        self.require_authenticated(token)
        with _connect(self.database_path) as connection:
            matter = _matter_row(connection, matter_id)
            if matter is None:
                raise WakiliOSError(f"matter does not exist: {matter_id}")
            return {
                "matter": _matter_mapping(matter),
                "parties": _select_tab(connection, "matter_parties", "matter_id", matter_id),
                "activities": _select_tab(connection, "matter_activities", "matter_id", matter_id),
                "lodgings": _select_tab(connection, "lodgings", "matter_id", matter_id),
                "court_decisions": _select_tab(
                    connection,
                    "court_decisions",
                    "matter_id",
                    matter_id,
                ),
                "fees": _select_tab(connection, "fee_entries", "matter_id", matter_id),
                "receipts": _select_tab(connection, "receipts", "matter_id", matter_id),
                "documents": _select_tab(connection, "documents", "matter_id", matter_id),
                "summaries": _select_tab(connection, "document_summaries", "matter_id", matter_id),
            }

    def export_calendar_ics(self, token: str, matter_id: str) -> str:
        actor = self.require_authenticated(token)
        with _connect(self.database_path) as connection:
            matter = _matter_row(connection, matter_id)
            if matter is None:
                raise WakiliOSError(f"matter does not exist: {matter_id}")
            activities = connection.execute(
                """
                SELECT activity_id, title, starts_at, court_session, notes
                FROM matter_activities
                WHERE matter_id = ? AND calendar_visible = 1 AND starts_at <> ''
                """,
                (matter_id,),
            ).fetchall()
            lodgings = connection.execute(
                """
                SELECT lodging_id, document_kind, due_date, filing_reference
                FROM lodgings
                WHERE matter_id = ? AND due_date <> ''
                """,
                (matter_id,),
            ).fetchall()
            decisions = connection.execute(
                """
                SELECT decision_id, decision_type, decision_date, outcome
                FROM court_decisions
                WHERE matter_id = ? AND decision_date <> ''
                """,
                (matter_id,),
            ).fetchall()
            _audit(
                connection,
                actor_id=actor["user_id"],
                event_type="calendar_exported",
                target_id=matter_id,
                details={"format": "ics"},
            )
        events: list[dict[str, str]] = []
        for row in activities:
            events.append(
                {
                    "uid": str(row["activity_id"]),
                    "summary": str(row["title"]),
                    "date": str(row["starts_at"]),
                    "description": f"{row['court_session']} {row['notes']}".strip(),
                }
            )
        for row in lodgings:
            events.append(
                {
                    "uid": str(row["lodging_id"]),
                    "summary": f"Lodging due: {row['document_kind']}",
                    "date": str(row["due_date"]),
                    "description": str(row["filing_reference"]),
                }
            )
        for row in decisions:
            events.append(
                {
                    "uid": str(row["decision_id"]),
                    "summary": f"Court decision: {row['decision_type']}",
                    "date": str(row["decision_date"]),
                    "description": str(row["outcome"]),
                }
            )
        return _build_ics(events)

    def build_offline_cache(self, token: str) -> OfflineCache:
        self.require_authenticated(token)
        with _connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT m.*, d.filing_status, d.filing_date, d.summary
                FROM matters m
                LEFT JOIN wakilios_matter_details d ON d.matter_id = m.matter_id
                ORDER BY m.created_at ASC
                """
            ).fetchall()
        return OfflineCache(
            schema_version=OFFLINE_CACHE_SCHEMA_VERSION,
            created_at=_utc_now(),
            mode="read_only",
            matters=tuple(_matter_mapping(row) for row in rows),
        )

    def audit_events(self, token: str) -> list[dict[str, object]]:
        self.require_role(token, {ADMIN_ROLE})
        with _connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT audit_id, actor_id, event_type, target_id, details_json, created_at
                FROM wakilios_audit_events
                ORDER BY created_at ASC, audit_id ASC
                """
            ).fetchall()
        return [
            _row_mapping(row) | {"details": json.loads(str(row["details_json"]))}
            for row in rows
        ]

    def require_authenticated(self, token: str) -> dict[str, str]:
        with _connect(self.database_path) as connection:
            payload = _verify_session_token(connection, token)
            row = connection.execute(
                """
                SELECT user_id, username, role, active
                FROM firm_users
                WHERE user_id = ?
                """,
                (payload["user_id"],),
            ).fetchone()
        if row is None or int(row["active"]) != 1:
            raise AuthenticationError("session user is inactive")
        return {
            "user_id": str(row["user_id"]),
            "username": str(row["username"]),
            "role": str(row["role"]),
        }

    def require_role(self, token: str, roles: frozenset[str] | set[str]) -> dict[str, str]:
        actor = self.require_authenticated(token)
        if actor["role"] not in roles:
            raise PermissionDeniedError(f"role cannot perform this action: {actor['role']}")
        return actor

    def _insert_tab_record(
        self,
        token: str,
        matter_id: str,
        *,
        required_roles: frozenset[str],
        table: str,
        id_column: str,
        event_type: str,
        fields: dict[str, object],
    ) -> dict[str, object]:
        actor = self.require_role(token, required_roles)
        record_id = str(uuid4())
        created_at = _datetime_to_text(_utc_now())
        columns = [id_column, "matter_id", *fields.keys(), "created_at"]
        values = [record_id, matter_id, *fields.values(), created_at]
        placeholders = ", ".join("?" for _ in columns)
        with _connect(self.database_path) as connection:
            _require_existing_matter(connection, matter_id)
            connection.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
            _audit(
                connection,
                actor_id=actor["user_id"],
                event_type=event_type,
                target_id=record_id,
                details={"matter_id": matter_id},
            )
            row = connection.execute(
                f"SELECT * FROM {table} WHERE {id_column} = ?",
                (record_id,),
            ).fetchone()
        return _row_mapping(row)


def initialize_firm_backend(
    root: Path,
    *,
    firm_name: str,
    admin_username: str,
    admin_password: str,
    vault_passphrase: str,
    max_seats: int = 5,
) -> WakiliOSBackend:
    backend = WakiliOSBackend(root, vault_passphrase)
    with _connect(backend.database_path) as connection:
        if _config(connection, "firm_name") is None:
            secret = os.urandom(32)
            values = {
                "firm_name": firm_name,
                "max_seats": str(max_seats),
                "session_secret_b64": _b64encode(secret),
                "created_at": _datetime_to_text(_utc_now()),
            }
            connection.executemany(
                "INSERT OR REPLACE INTO firm_config (key, value) VALUES (?, ?)",
                values.items(),
            )
        admin_exists = connection.execute(
            "SELECT 1 FROM firm_users WHERE username = ?",
            (admin_username,),
        ).fetchone()
        if admin_exists is None:
            salt_b64, password_hash = _hash_password(admin_password)
            user_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO firm_users (
                    user_id, username, display_name, role, password_hash,
                    password_salt_b64, active, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    user_id,
                    admin_username,
                    "Firm administrator",
                    ADMIN_ROLE,
                    password_hash,
                    salt_b64,
                    _datetime_to_text(_utc_now()),
                ),
            )
            _audit(
                connection,
                actor_id=user_id,
                event_type="firm_initialized",
                target_id=user_id,
                details={"firm_name": firm_name},
            )
    return backend


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS firm_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS firm_users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            password_salt_b64 TEXT NOT NULL,
            active INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS matter_assignments (
            assignment_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS wakilios_matter_details (
            matter_id TEXT PRIMARY KEY,
            filing_status TEXT NOT NULL,
            filing_date TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_by TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS matter_parties (
            party_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            name TEXT NOT NULL,
            party_role TEXT NOT NULL,
            contact_details TEXT NOT NULL,
            representative TEXT NOT NULL,
            notes TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS matter_activities (
            activity_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            title TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            court_session TEXT NOT NULL,
            status TEXT NOT NULL,
            notes TEXT NOT NULL,
            calendar_visible INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS lodgings (
            lodging_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            document_kind TEXT NOT NULL,
            party TEXT NOT NULL,
            due_date TEXT NOT NULL,
            lodged_date TEXT NOT NULL,
            filing_status TEXT NOT NULL,
            linked_document_id TEXT NOT NULL,
            filing_reference TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS court_decisions (
            decision_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            decision_type TEXT NOT NULL,
            decision_date TEXT NOT NULL,
            court TEXT NOT NULL,
            decision_maker TEXT NOT NULL,
            outcome TEXT NOT NULL,
            notes TEXT NOT NULL,
            linked_document_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fee_entries (
            fee_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            fee_type TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            paid_by TEXT NOT NULL,
            paid_to TEXT NOT NULL,
            status TEXT NOT NULL,
            linked_activity_id TEXT NOT NULL,
            linked_lodging_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS receipts (
            receipt_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            receipt_number TEXT NOT NULL,
            issuer TEXT NOT NULL,
            payer TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            receipt_date TEXT NOT NULL,
            linked_fee_id TEXT NOT NULL,
            linked_document_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS document_summaries (
            summary_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            matter_id TEXT NOT NULL,
            manual_summary TEXT NOT NULL,
            ai_draft_summary TEXT NOT NULL,
            approval_status TEXT NOT NULL,
            citation_ids_json TEXT NOT NULL,
            generated_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS wakilios_audit_events (
            audit_id TEXT PRIMARY KEY,
            actor_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )


def _hash_password(password: str) -> tuple[str, str]:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return _b64encode(salt), _b64encode(digest)


def _verify_password(password: str, salt_b64: str, expected_hash: str) -> bool:
    salt = _b64decode(salt_b64)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return hmac.compare_digest(_b64encode(digest), expected_hash)


def _sign_session_token(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    role: str,
    expires_at: datetime,
) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "expires_at": _datetime_to_text(expires_at),
        "nonce": str(uuid4()),
    }
    encoded_payload = _urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(
        _session_secret(connection),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_urlsafe_b64encode(signature)}"


def _verify_session_token(connection: sqlite3.Connection, token: str) -> dict[str, str]:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
    except ValueError as exc:
        raise AuthenticationError("invalid session token") from exc
    expected_signature = hmac.new(
        _session_secret(connection),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(_urlsafe_b64encode(expected_signature), encoded_signature):
        raise AuthenticationError("invalid session token")
    payload = json.loads(_urlsafe_b64decode(encoded_payload).decode("utf-8"))
    expires_at = _parse_datetime(str(payload["expires_at"]))
    if expires_at <= _utc_now():
        raise AuthenticationError("session token expired")
    return {"user_id": str(payload["user_id"]), "role": str(payload["role"])}


def _enforce_seat_limit(connection: sqlite3.Connection) -> None:
    max_seats = int(_require_config(connection, "max_seats"))
    active = connection.execute(
        "SELECT COUNT(*) AS active_count FROM firm_users WHERE active = 1"
    ).fetchone()
    if int(active["active_count"]) >= max_seats:
        raise SeatLimitError("firm seat limit reached")


def _session_secret(connection: sqlite3.Connection) -> bytes:
    return _b64decode(_require_config(connection, "session_secret_b64"))


def _config(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute("SELECT value FROM firm_config WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row is not None else None


def _require_config(connection: sqlite3.Connection, key: str) -> str:
    value = _config(connection, key)
    if value is None:
        raise WakiliOSError(f"missing firm config: {key}")
    return value


def _matter_row(connection: sqlite3.Connection, matter_id: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT m.*, d.filing_status, d.filing_date, d.summary
        FROM matters m
        LEFT JOIN wakilios_matter_details d ON d.matter_id = m.matter_id
        WHERE m.matter_id = ?
        """,
        (matter_id,),
    ).fetchone()


def _require_existing_matter(connection: sqlite3.Connection, matter_id: str) -> None:
    if _matter_row(connection, matter_id) is None:
        raise WakiliOSError(f"matter does not exist: {matter_id}")


def _matter_mapping(row: sqlite3.Row) -> dict[str, object]:
    return {
        "matter_id": str(row["matter_id"]),
        "internal_reference": str(row["internal_reference"]),
        "client_name": str(row["client_name"]),
        "parties": str(row["parties"]),
        "court": str(row["court"]),
        "station": str(row["station"]),
        "case_number": str(row["case_number"]),
        "practice_area": str(row["practice_area"]),
        "responsible_advocate": str(row["responsible_advocate"]),
        "status": str(row["status"]),
        "filing_status": str(row["filing_status"] or ""),
        "filing_date": str(row["filing_date"] or ""),
        "summary": str(row["summary"] or ""),
        "created_at": str(row["created_at"]),
    }


def _select_tab(
    connection: sqlite3.Connection,
    table: str,
    field: str,
    value: str,
) -> list[dict[str, object]]:
    rows = connection.execute(
        f"SELECT * FROM {table} WHERE {field} = ? ORDER BY created_at ASC",
        (value,),
    ).fetchall()
    return [_row_mapping(row) for row in rows]


def _row_mapping(row: sqlite3.Row | None) -> dict[str, object]:
    if row is None:
        return {}
    return {key: row[key] for key in row.keys()}


def _audit(
    connection: sqlite3.Connection,
    *,
    actor_id: str,
    event_type: str,
    target_id: str,
    details: dict[str, object],
) -> None:
    connection.execute(
        """
        INSERT INTO wakilios_audit_events (
            audit_id, actor_id, event_type, target_id, details_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            actor_id,
            event_type,
            target_id,
            json.dumps(details, sort_keys=True, separators=(",", ":")),
            _datetime_to_text(_utc_now()),
        ),
    )


def _summary_from_context(context: str) -> str:
    compact = " ".join(context.split())
    if len(compact) <= 420:
        return compact
    return f"{compact[:417].rstrip()}..."


def _build_ics(events: list[dict[str, str]]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//WakiliOS//Matter Calendar//EN",
        "CALSCALE:GREGORIAN",
    ]
    now = _ics_datetime(_utc_now())
    for event in events:
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{_escape_ics(event['uid'])}@wakilios",
                f"DTSTAMP:{now}",
                f"DTSTART:{_ics_date_or_datetime(event['date'])}",
                f"SUMMARY:{_escape_ics(event['summary'])}",
                f"DESCRIPTION:{_escape_ics(event['description'])}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _ics_date_or_datetime(value: str) -> str:
    if "T" in value:
        return _ics_datetime(_parse_datetime(value))
    return value.replace("-", "")


def _ics_datetime(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _escape_ics(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


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


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _datetime_to_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)
