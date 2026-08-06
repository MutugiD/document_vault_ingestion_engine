"""Firm-hosted WakiliOS backend service layer."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
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
STANDARD_ROLES = frozenset({ADMIN_ROLE, ADVOCATE_ROLE, CLERK_ROLE, ACCOUNTS_ROLE, READ_ONLY_ROLE})
WRITE_ROLES = frozenset({ADMIN_ROLE, ADVOCATE_ROLE, CLERK_ROLE, ACCOUNTS_ROLE})
SUMMARY_ROLES = frozenset({ADMIN_ROLE, ADVOCATE_ROLE})
DOCUMENT_ROLES = frozenset({ADMIN_ROLE, ADVOCATE_ROLE, CLERK_ROLE})
ACCOUNTS_ROLES = frozenset({ADMIN_ROLE, ACCOUNTS_ROLE})
SESSION_TTL_MINUTES = 90
OFFLINE_CACHE_SCHEMA_VERSION = "1"

NAIROBI = timezone(timedelta(hours=3), "EAT")
"""Kenyan civil time.

Fixed rather than looked up: Kenya has never observed daylight saving, and a
frozen build cannot rely on ``tzdata`` being present.
"""

CALENDAR_DATE_COLUMNS: dict[str, tuple[str, ...]] = {
    "matter_activities": ("starts_at",),
    "lodgings": ("due_date", "lodged_date"),
    "court_decisions": ("decision_date",),
    "receipts": ("receipt_date",),
    "matter_filing_records": ("filed_at", "next_action_date"),
    "wakilios_matter_details": ("filing_date",),
}
"""Columns holding a date a firm cares about, as opposed to a log timestamp.

These are stored as **Nairobi local wall time with no offset** -- ``YYYY-MM-DD``
when only the day is known, ``YYYY-MM-DDTHH:MM:SS`` when a time is. Log columns
(``created_at``, audit rows) keep UTC ``...Z`` via :func:`_datetime_to_text`.

The split is deliberate and matters when reading queries here. Within a single
timezone, lexicographic order over these strings *is* chronological order, so
``ORDER BY`` and range comparisons work directly on TEXT. It also means the
half-open day range ``col >= '2026-08-06' AND col < '2026-08-07'`` catches both
shapes on the same day, because::

    '2026-08-06' < '2026-08-06T09:00:00' < '2026-08-07'

That property is what lets date-only and date-time columns share one query
instead of needing a union of two. Storing UTC here would buy nothing and would
put a 06:00 EAT hearing on the previous day.
"""

SESSION_TOKEN_TYPE = "session"
DEVICE_TOKEN_TYPE = "device"
PAIRING_CODE_TTL_MINUTES = 10
DEVICE_TOKEN_TTL_DAYS = 90
DEVICE_SNAPSHOT_LIMIT = 500
DEVICE_CALENDAR_HORIZON_DAYS = 120
PAIRING_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
"""Unambiguous when read aloud or copied by hand.

No I/1, O/0, or L: a pairing code is typed from a screen into a phone across a
desk, and a transcription failure looks identical to a rejected code.
"""

REMINDER_UNREAD = "unread"
REMINDER_READ = "read"
REMINDER_ACKNOWLEDGED = "acknowledged"
REMINDER_DISMISSED = "dismissed"
REMINDER_STATES = frozenset(
    {REMINDER_UNREAD, REMINDER_READ, REMINDER_ACKNOWLEDGED, REMINDER_DISMISSED}
)
REMINDER_PRIORITIES = frozenset({"normal", "urgent"})
REMINDER_DAILY_LIMIT = 50

_DATE_ONLY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SLASHED_DATE_PATTERN = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_ACCEPTED_DATE_FORMATS = "YYYY-MM-DD, DD/MM/YYYY, or YYYY-MM-DDTHH:MM:SS"


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
            _migrate_schema(connection)
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
        filing_date = normalize_matter_date(filing_date, field="filing_date")
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
                "starts_at": normalize_matter_date(fields["starts_at"], field="starts_at"),
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
                "due_date": normalize_matter_date(fields.get("due_date", ""), field="due_date"),
                "lodged_date": normalize_matter_date(
                    fields.get("lodged_date", ""), field="lodged_date"
                ),
                "filing_status": fields.get("filing_status", "pending"),
                "linked_document_id": fields.get("linked_document_id", ""),
                "filing_reference": fields.get("filing_reference", ""),
                # The portal's own actioning state, e.g. "Not Actioned".
                "actioning_status": fields.get("actioning_status", ""),
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
                "decision_date": normalize_matter_date(
                    fields["decision_date"], field="decision_date"
                ),
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
                # Payment Reference Number: what an MPESA or KCB payment is
                # reconciled against on the portal.
                "prn": str(fields.get("prn", "")),
            },
        )

    def add_filing_record(self, token: str, matter_id: str, **fields: object) -> dict[str, object]:
        """Record what was filed, what came back, and what happens next."""
        return self._insert_tab_record(
            token,
            matter_id,
            required_roles=DOCUMENT_ROLES,
            table="matter_filing_records",
            id_column="filing_record_id",
            event_type="filing_record_created",
            fields={
                "tracking_number": str(fields.get("tracking_number", "")),
                "station": str(fields.get("station", "")),
                "case_number": str(fields.get("case_number", "")),
                "filed_at": normalize_matter_date(fields.get("filed_at", ""), field="filed_at"),
                "filed_by": str(fields.get("filed_by", "")),
                "what_was_filed": str(fields.get("what_was_filed", "")),
                "what_was_served": str(fields.get("what_was_served", "")),
                "what_was_received": str(fields.get("what_was_received", "")),
                "next_action": str(fields.get("next_action", "")),
                "next_action_date": normalize_matter_date(
                    fields.get("next_action_date", ""), field="next_action_date"
                ),
                "portal_status": str(fields.get("portal_status", "")),
                "linked_lodging_id": str(fields.get("linked_lodging_id", "")),
                "linked_receipt_id": str(fields.get("linked_receipt_id", "")),
            },
        )

    def list_filing_records(self, token: str, matter_id: str) -> list[dict[str, object]]:
        self.require_authenticated(token)
        with _connect(self.database_path) as connection:
            _require_existing_matter(connection, matter_id)
            return _select_tab(connection, "matter_filing_records", "matter_id", matter_id)

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
                "receipt_date": normalize_matter_date(fields["receipt_date"], field="receipt_date"),
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
                "filing_records": _select_tab(
                    connection,
                    "matter_filing_records",
                    "matter_id",
                    matter_id,
                ),
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
            next_actions = connection.execute(
                """
                SELECT filing_record_id, next_action, next_action_date, tracking_number
                FROM matter_filing_records
                WHERE matter_id = ? AND next_action_date <> ''
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
        for row in next_actions:
            events.append(
                {
                    "uid": str(row["filing_record_id"]),
                    "summary": f"Next action: {row['next_action'] or 'follow up'}",
                    "date": str(row["next_action_date"]),
                    "description": str(row["tracking_number"]),
                }
            )
        return _build_ics(events)

    def upcoming_dates(
        self,
        token: str,
        *,
        start: str,
        end: str,
        matter_id: str = "",
        limit: int = 500,
    ) -> list[dict[str, object]]:
        """Every dated obligation across the firm between ``start`` and ``end``.

        Half-open: ``start`` is included, ``end`` is not, so one day is
        ``start="2026-08-06", end="2026-08-07"``. See
        :data:`CALENDAR_DATE_COLUMNS` for why that range catches both date-only
        and date-time rows without a second query shape.

        ``require_authenticated`` rather than a write role: a diary is a read,
        and a read-only seat asking "what is on today" is the whole point.

        Deliberately writes no audit row. The desktop polls this on a timer and
        the phone on every sync; ``wakilios_audit_events`` has no retention
        policy and no index on ``created_at``, so a row per poll would degrade
        the admin view a little more each day for no investigative value.
        """
        self.require_authenticated(token, allow_device=True)
        window_start = normalize_matter_date(start, field="start")
        window_end = normalize_matter_date(end, field="end")
        parameters: list[object] = [window_start, window_end]
        matter_filter = ""
        if matter_id:
            matter_filter = "AND entries.matter_id = ?"
            parameters.append(matter_id)
        parameters.append(int(limit))
        with _connect(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    entries.*,
                    m.internal_reference AS matter_reference,
                    m.case_number AS case_number,
                    m.client_name AS client_name
                FROM ({_UPCOMING_ENTRIES_SQL}) AS entries
                JOIN matters m ON m.matter_id = entries.matter_id
                WHERE entries.entry_date >= ? AND entries.entry_date < ?
                {matter_filter}
                ORDER BY entries.entry_date ASC, entries.title ASC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [_upcoming_mapping(row) for row in rows]

    # ── Reminders between colleagues ─────────────────────────────────────

    def list_firm_users(self, token: str) -> list[dict[str, object]]:
        """Who is in the firm, so a reminder can be addressed to someone.

        No route listed users before this, which meant a send dialog had nobody
        to name. It does newly expose the roster to every seat; inside one firm
        that is unremarkable, but it is a change worth stating. Password hashes
        and salts are never included.
        """
        self.require_authenticated(token, allow_device=True)
        with _connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT user_id, username, display_name, role, active
                FROM firm_users
                ORDER BY display_name ASC, username ASC
                """
            ).fetchall()
        return [
            {
                "user_id": str(row["user_id"]),
                "username": str(row["username"]),
                "display_name": str(row["display_name"]),
                "role": str(row["role"]),
                "active": bool(int(row["active"])),
            }
            for row in rows
        ]

    def send_reminder(
        self,
        token: str,
        *,
        recipient_ids: list[str] | tuple[str, ...],
        subject: str,
        body: str = "",
        matter_id: str = "",
        due_date: str = "",
        priority: str = "normal",
    ) -> list[dict[str, object]]:
        """Put something on a colleague's desk about a matter.

        Any writing role may send, including clerks and accounts. A clerk who
        notices a filing deadline is exactly the person who needs to prompt the
        advocate, so restricting this to advocates would remove the main use.
        Read-only seats may not.

        Deliberately not gated on ``matter_assignments``. That table is written
        once at matter creation and enforced nowhere, so gating on it would
        silently refuse most legitimate sends -- the worst kind of permission
        check, because it looks principled and behaves arbitrarily.
        """
        actor = self.require_role(token, WRITE_ROLES, allow_device=True)
        subject = subject.strip()
        if not subject:
            raise WakiliOSError("a reminder needs a subject")
        if priority not in REMINDER_PRIORITIES:
            raise WakiliOSError(f"unsupported priority: {priority}")
        recipients = [str(value) for value in dict.fromkeys(recipient_ids) if str(value).strip()]
        if not recipients:
            raise WakiliOSError("a reminder needs at least one recipient")
        due_date = normalize_matter_date(due_date, field="due_date")

        created: list[dict[str, object]] = []
        with _connect(self.database_path) as connection:
            if matter_id:
                _require_existing_matter(connection, matter_id)
            self._enforce_reminder_rate_limit(connection, actor["user_id"])
            for recipient_id in recipients:
                row = connection.execute(
                    "SELECT active FROM firm_users WHERE user_id = ?", (recipient_id,)
                ).fetchone()
                if row is None or int(row["active"]) != 1:
                    raise WakiliOSError(f"not an active firm user: {recipient_id}")
                reminder_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO matter_reminders (
                        reminder_id, matter_id, sender_id, recipient_id, subject,
                        body, due_date, priority, state, acknowledged_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?)
                    """,
                    (
                        reminder_id,
                        matter_id,
                        actor["user_id"],
                        recipient_id,
                        subject,
                        body,
                        due_date,
                        priority,
                        REMINDER_UNREAD,
                        _datetime_to_text(_utc_now()),
                    ),
                )
                created.append(
                    _row_mapping(
                        connection.execute(
                            "SELECT * FROM matter_reminders WHERE reminder_id = ?",
                            (reminder_id,),
                        ).fetchone()
                    )
                )
            _audit(
                connection,
                actor_id=actor["user_id"],
                event_type="reminder_sent",
                target_id=matter_id or "firm",
                details={"recipients": len(recipients), "priority": priority},
            )
        return created

    def list_reminders(
        self, token: str, *, state: str = "", since: str = "", limit: int = 200
    ) -> list[dict[str, object]]:
        """The caller's own inbox.

        The recipient is always the caller, and an administrator gets no
        override. Reading a colleague's reminders in a law firm is a
        confidentiality problem, and there is no consent model here that would
        make it defensible -- so the capability simply does not exist.
        """
        actor = self.require_authenticated(token, allow_device=True)
        clauses = ["r.recipient_id = ?"]
        parameters: list[object] = [actor["user_id"]]
        if state:
            clauses.append("r.state = ?")
            parameters.append(state)
        if since:
            clauses.append("r.created_at > ?")
            parameters.append(since)
        parameters.append(int(limit))
        with _connect(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT r.*, u.display_name AS sender_name, u.username AS sender_username,
                       m.internal_reference AS matter_reference
                FROM matter_reminders r
                LEFT JOIN firm_users u ON u.user_id = r.sender_id
                LEFT JOIN matters m ON m.matter_id = r.matter_id
                WHERE {" AND ".join(clauses)}
                ORDER BY r.created_at DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [_row_mapping(row) for row in rows]

    def list_sent_reminders(self, token: str, *, limit: int = 200) -> list[dict[str, object]]:
        """What the caller has sent, so acknowledgement is visible to them."""
        actor = self.require_authenticated(token)
        with _connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT r.*, u.display_name AS recipient_name, u.username AS recipient_username
                FROM matter_reminders r
                LEFT JOIN firm_users u ON u.user_id = r.recipient_id
                WHERE r.sender_id = ?
                ORDER BY r.created_at DESC
                LIMIT ?
                """,
                (actor["user_id"], int(limit)),
            ).fetchall()
        return [_row_mapping(row) for row in rows]

    def acknowledge_reminder(
        self, token: str, reminder_id: str, *, state: str = REMINDER_ACKNOWLEDGED
    ) -> dict[str, object]:
        """Mark one of the caller's own reminders read, acknowledged or dismissed."""
        actor = self.require_authenticated(token, allow_device=True)
        if state not in REMINDER_STATES:
            raise WakiliOSError(f"unsupported reminder state: {state}")
        with _connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT recipient_id FROM matter_reminders WHERE reminder_id = ?",
                (reminder_id,),
            ).fetchone()
            if row is None:
                raise WakiliOSError(f"reminder does not exist: {reminder_id}")
            if str(row["recipient_id"]) != actor["user_id"]:
                raise PermissionDeniedError("only the recipient can act on a reminder")
            connection.execute(
                "UPDATE matter_reminders SET state = ?, acknowledged_at = ? WHERE reminder_id = ?",
                (
                    state,
                    _datetime_to_text(_utc_now()) if state == REMINDER_ACKNOWLEDGED else "",
                    reminder_id,
                ),
            )
            _audit(
                connection,
                actor_id=actor["user_id"],
                event_type="reminder_acknowledged",
                target_id=reminder_id,
                details={"state": state},
            )
            return _row_mapping(
                connection.execute(
                    "SELECT * FROM matter_reminders WHERE reminder_id = ?", (reminder_id,)
                ).fetchone()
            )

    def _enforce_reminder_rate_limit(self, connection: sqlite3.Connection, sender_id: str) -> None:
        """Cap what one seat can send in a day.

        Not an abuse problem at five seats so much as an accident one: a loop in
        a future integration, or a stuck button, should not fill every
        colleague's inbox before anyone notices.
        """
        since = _datetime_to_text(_utc_now() - timedelta(days=1))
        sent = connection.execute(
            "SELECT COUNT(*) FROM matter_reminders WHERE sender_id = ? AND created_at > ?",
            (sender_id, since),
        ).fetchone()[0]
        if int(sent) >= REMINDER_DAILY_LIMIT:
            raise WakiliOSError(
                f"reminder limit reached: {REMINDER_DAILY_LIMIT} in 24 hours. "
                f"If this is legitimate, wait or raise it with the administrator."
            )

    # ── Paired devices ───────────────────────────────────────────────────

    def create_pairing_code(self, token: str) -> dict[str, object]:
        """Mint a short-lived code that a phone can exchange for a token.

        The code is displayed on the desktop and typed into the phone. It is
        deliberately not a QR image: a QR needs a new dependency, a bundling
        entry and an image path, and eight characters read aloud across a desk
        works today. A QR is a later convenience, not a prerequisite.
        """
        actor = self.require_authenticated(token)
        code = _pairing_code()
        expires_at = _utc_now() + timedelta(minutes=PAIRING_CODE_TTL_MINUTES)
        with _connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO device_pairings (
                    pairing_code, user_id, expires_at, consumed, created_at
                ) VALUES (?, ?, ?, 0, ?)
                """,
                (
                    code,
                    actor["user_id"],
                    _datetime_to_text(expires_at),
                    _datetime_to_text(_utc_now()),
                ),
            )
            _audit(
                connection,
                actor_id=actor["user_id"],
                event_type="device_pairing_offered",
                target_id=actor["user_id"],
                details={"expires_in_minutes": PAIRING_CODE_TTL_MINUTES},
            )
        return {
            "pairing_code": code,
            "expires_at": _datetime_to_text(expires_at),
            "expires_in_minutes": PAIRING_CODE_TTL_MINUTES,
        }

    def claim_pairing_code(
        self, pairing_code: str, *, device_name: str, platform: str = "android"
    ) -> dict[str, object]:
        """Exchange a pairing code for a device token.

        Unauthenticated on purpose: the short-lived, single-use code *is* the
        credential, and requiring a password here would mean typing a firm
        password into a phone, which is the thing pairing exists to avoid.
        """
        code = pairing_code.strip().upper()
        with _connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT user_id, expires_at, consumed FROM device_pairings WHERE pairing_code = ?",
                (code,),
            ).fetchone()
            if row is None:
                raise AuthenticationError("unknown pairing code")
            if int(row["consumed"]) != 0:
                raise AuthenticationError("this pairing code has already been used")
            if _parse_datetime(str(row["expires_at"])) <= _utc_now():
                raise AuthenticationError("this pairing code has expired")

            user = connection.execute(
                "SELECT user_id, username, role, active FROM firm_users WHERE user_id = ?",
                (row["user_id"],),
            ).fetchone()
            if user is None or int(user["active"]) != 1:
                raise AuthenticationError("the user this code belongs to is inactive")

            connection.execute(
                "UPDATE device_pairings SET consumed = 1 WHERE pairing_code = ?", (code,)
            )
            device_id = str(uuid4())
            now = _datetime_to_text(_utc_now())
            connection.execute(
                """
                INSERT INTO paired_devices (
                    device_id, user_id, device_name, platform, created_at, last_seen_at, revoked
                ) VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (device_id, str(user["user_id"]), device_name, platform, now, now),
            )
            expires_at = _utc_now() + timedelta(days=DEVICE_TOKEN_TTL_DAYS)
            device_token = _sign_device_token(
                connection,
                device_id=device_id,
                user_id=str(user["user_id"]),
                role=str(user["role"]),
                expires_at=expires_at,
            )
            _audit(
                connection,
                actor_id=str(user["user_id"]),
                event_type="device_paired",
                target_id=device_id,
                details={"device_name": device_name, "platform": platform},
            )
        return {
            "device_id": device_id,
            "device_token": device_token,
            "username": str(user["username"]),
            "role": str(user["role"]),
            "expires_at": _datetime_to_text(expires_at),
        }

    def list_paired_devices(self, token: str) -> list[dict[str, object]]:
        """The caller's own devices, so a lost phone can be found and revoked."""
        actor = self.require_authenticated(token)
        with _connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT device_id, device_name, platform, created_at, last_seen_at, revoked
                FROM paired_devices
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (actor["user_id"],),
            ).fetchall()
        return [_row_mapping(row) | {"revoked": bool(int(row["revoked"]))} for row in rows]

    def revoke_device(self, token: str, device_id: str) -> dict[str, object]:
        """Unpair a device. Takes effect on its next request.

        Permitted to the device's owner and to an administrator. Unlike reading
        a colleague's reminders, an administrator revoking a device is a
        security action with no confidentiality cost -- and a firm whose
        administrator cannot cut off a stolen phone is worse off than one whose
        administrator can.
        """
        actor = self.require_authenticated(token)
        with _connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT user_id FROM paired_devices WHERE device_id = ?", (device_id,)
            ).fetchone()
            if row is None:
                raise WakiliOSError(f"device does not exist: {device_id}")
            if str(row["user_id"]) != actor["user_id"] and actor["role"] != ADMIN_ROLE:
                raise PermissionDeniedError("only the device owner or an administrator may unpair")
            connection.execute(
                "UPDATE paired_devices SET revoked = 1 WHERE device_id = ?", (device_id,)
            )
            _audit(
                connection,
                actor_id=actor["user_id"],
                event_type="device_revoked",
                target_id=device_id,
                details={"owner": str(row["user_id"])},
            )
        return {"device_id": device_id, "revoked": True}

    def build_device_snapshot(
        self, token: str, *, since: str = "", limit: int = DEVICE_SNAPSHOT_LIMIT
    ) -> dict[str, object]:
        """Everything a phone needs, and deliberately nothing more.

        Documents and extracted text are excluded. They are what would make
        this large, and they are what one least wants sitting on a phone that
        can be left in a taxi. The phone shows what is happening and when; the
        documents stay in the vault.

        ``since`` filters on ``created_at`` and therefore returns **appends
        only**. The schema has no ``updated_at`` and no soft delete, so a
        rescheduled hearing or a closed matter cannot appear in a delta. The
        client is expected to take a full snapshot periodically rather than
        trust a chain of deltas, and this is named here rather than described
        as complete delta sync, which it is not.
        """
        actor = self.require_authenticated(token, allow_device=True)
        horizon_start = (datetime.now(NAIROBI).date() - timedelta(days=7)).isoformat()
        horizon_end = (
            datetime.now(NAIROBI).date() + timedelta(days=DEVICE_CALENDAR_HORIZON_DAYS)
        ).isoformat()

        with _connect(self.database_path) as connection:
            clauses = []
            parameters: list[object] = []
            if since:
                clauses.append("m.created_at > ?")
                parameters.append(since)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            parameters.append(int(limit))
            matters = connection.execute(
                f"""
                SELECT m.*, d.filing_status, d.filing_date, d.summary
                FROM matters m
                LEFT JOIN wakilios_matter_details d ON d.matter_id = m.matter_id
                {where}
                ORDER BY m.created_at DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()

        calendar = self.upcoming_dates(
            token, start=horizon_start, end=horizon_end, limit=DEVICE_SNAPSHOT_LIMIT
        )
        reminders = self.list_reminders(token, since=since, limit=DEVICE_SNAPSHOT_LIMIT)
        people = [
            {
                "user_id": person["user_id"],
                "display_name": person["display_name"],
                "role": person["role"],
            }
            for person in self.list_firm_users(token)
            if person.get("active")
        ]

        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _datetime_to_text(_utc_now()),
            "since": since,
            "complete": not since,
            "user": {"username": actor["username"], "role": actor["role"]},
            "matters": [_snapshot_matter(row) for row in matters],
            "calendar": calendar,
            "reminders": reminders,
            "users": people,
        }

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

    def firm_overview(self, token: str) -> dict[str, object]:
        """Firm-wide counts and money, for the Reports destination.

        Mirrors what the Judiciary portal dashboard shows a firm: how many
        matters sit at each station and by status, and what has been charged
        against what has been receipted.
        """
        self.require_authenticated(token)
        with _connect(self.database_path) as connection:

            def scalar(sql: str) -> float:
                row = connection.execute(sql).fetchone()
                value = row[0] if row is not None else 0
                return float(value or 0)

            by_station = [
                {"station": str(row["station"] or "unassigned"), "matters": int(row["total"])}
                for row in connection.execute(
                    "SELECT station, COUNT(*) AS total FROM matters"
                    " GROUP BY station ORDER BY total DESC"
                )
            ]
            by_status = [
                {"status": str(row["status"] or "unknown"), "matters": int(row["total"])}
                for row in connection.execute(
                    "SELECT status, COUNT(*) AS total FROM matters"
                    " GROUP BY status ORDER BY total DESC"
                )
            ]
            fees_raised = scalar("SELECT SUM(amount) FROM fee_entries")
            receipts_total = scalar("SELECT SUM(amount) FROM receipts")
            return {
                "matters": int(scalar("SELECT COUNT(*) FROM matters")),
                "documents": int(scalar("SELECT COUNT(*) FROM documents")),
                "filing_records": int(scalar("SELECT COUNT(*) FROM matter_filing_records")),
                "fees_raised": fees_raised,
                "receipts_total": receipts_total,
                "balance": round(fees_raised - receipts_total, 2),
                "by_station": by_station,
                "by_status": by_status,
            }

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
            _row_mapping(row) | {"details": json.loads(str(row["details_json"]))} for row in rows
        ]

    def require_authenticated(self, token: str, *, allow_device: bool = False) -> dict[str, str]:
        """Resolve a token to an actor, refusing paired devices by default.

        ``allow_device`` is opt-in rather than opt-out, and that direction is
        the point. A device token lives on a phone for months and is the one
        credential here likely to be lost with the hardware, so a phone must
        reach only the handful of things it has been reasoned about. A method
        added later is device-denied until someone decides otherwise, which is
        the safe way for that decision to be forgotten.
        """
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
        if payload["typ"] == DEVICE_TOKEN_TYPE and not allow_device:
            raise PermissionDeniedError(
                "a paired device cannot do this. Sign in on a desktop seat."
            )
        return {
            "user_id": str(row["user_id"]),
            "username": str(row["username"]),
            "role": str(row["role"]),
            "typ": payload["typ"],
            "device_id": payload["device_id"],
        }

    def require_role(
        self, token: str, roles: frozenset[str] | set[str], *, allow_device: bool = False
    ) -> dict[str, str]:
        actor = self.require_authenticated(token, allow_device=allow_device)
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


SCHEMA_VERSION = 5
"""Current schema generation.

Bump this and add a matching entry to ``_MIGRATIONS`` whenever a column or
table is added to an existing table's shape.
"""


def _add_column(connection: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    """Add a column if the table does not already have it.

    ``ALTER TABLE ... ADD COLUMN`` has no ``IF NOT EXISTS`` form in SQLite, and
    migrations must tolerate being re-run against a database that a newer build
    already touched.

    A missing table is skipped rather than an error. This database is shared
    with the search store, which owns ``documents`` and creates it separately,
    so the table a migration targets may legitimately not be there yet.
    """
    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if not existing or column in existing:
        return
    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _migration_1_filing_record(connection: sqlite3.Connection) -> None:
    """Mirror the fields the Judiciary e-filing portal exposes per case.

    The portal shows a Payment Reference Number against each fee and an
    actioning state against each lodged document. Without them a firm cannot
    reconcile an MPESA/KCB payment back to a filing, which is the whole point
    of keeping an independent record.
    """
    _add_column(connection, "fee_entries", "prn", "TEXT NOT NULL DEFAULT ''")
    _add_column(connection, "lodgings", "actioning_status", "TEXT NOT NULL DEFAULT ''")


def _migration_2_filing_ledger(connection: sqlite3.Connection) -> None:
    """Add the independent record of what was filed.

    A portal submission proves a filing was made; it does not give the firm a
    recoverable account of what was filed, when, by whom, what was served, what
    came back, and what must happen next. Lodgings, receipts and activities each
    hold a fragment of that, keyed to how the portal models a case rather than
    how a firm has to answer "where is this matter". This table is the firm's
    own continuity ledger over those fragments, and it survives the portal.
    """
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS matter_filing_records (
            filing_record_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            tracking_number TEXT NOT NULL,
            station TEXT NOT NULL,
            case_number TEXT NOT NULL,
            filed_at TEXT NOT NULL,
            filed_by TEXT NOT NULL,
            what_was_filed TEXT NOT NULL,
            what_was_served TEXT NOT NULL,
            what_was_received TEXT NOT NULL,
            next_action TEXT NOT NULL,
            next_action_date TEXT NOT NULL,
            portal_status TEXT NOT NULL,
            linked_lodging_id TEXT NOT NULL,
            linked_receipt_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_filing_records_matter
            ON matter_filing_records (matter_id);
        """
    )
    # Which role a document plays in the filing trail: the filed copy, the
    # payment receipt, or proof of service. Distinct from document_type, which
    # says what the document is rather than what it evidences.
    _add_column(connection, "documents", "filing_role", "TEXT NOT NULL DEFAULT ''")


_CALENDAR_INDEXES = (
    ("matter_activities", "idx_activities_starts_at", "starts_at"),
    ("lodgings", "idx_lodgings_due_date", "due_date"),
    ("court_decisions", "idx_decisions_date", "decision_date"),
    ("matter_filing_records", "idx_filing_next_action", "next_action_date"),
    ("receipts", "idx_receipts_date", "receipt_date"),
)


def _migration_3_calendar_dates(connection: sqlite3.Connection) -> None:
    """Canonicalise every matter date, and make date ranges indexable.

    These columns are ``TEXT NOT NULL`` and nothing has ever validated them, so
    a database can hold ``2026-08-06``, ``2026-08-06T09:00:00Z`` and ``06/08/2026``
    in the same column. That is survivable for display and fatal for a query:
    "what is due today" has no answer over three formats, and the ``.ics``
    export corrupted the whole file on the first value it could not parse.

    See :data:`CALENDAR_DATE_COLUMNS` for the stored format and why it is
    Nairobi local rather than UTC.

    A value that will not parse is **left exactly as it was** and reported in an
    audit row. A firm's record of what it typed is worth more than our
    preference for a tidy column, and a lost date cannot be recovered from a
    migration that has already run.
    """
    for table, columns in CALENDAR_DATE_COLUMNS.items():
        present = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if not present:
            continue
        for column in columns:
            if column not in present:
                continue
            rows = connection.execute(
                f"SELECT rowid AS rid, {column} AS value FROM {table} WHERE {column} <> ''"
            ).fetchall()
            unparsed: list[str] = []
            for row in rows:
                original = str(row["value"])
                coerced = _coerce_matter_date(original)
                if coerced is None:
                    unparsed.append(original)
                elif coerced != original:
                    connection.execute(
                        f"UPDATE {table} SET {column} = ? WHERE rowid = ?",
                        (coerced, row["rid"]),
                    )
            if unparsed:
                _audit(
                    connection,
                    actor_id="system",
                    event_type="date_backfill_unparsed",
                    target_id=f"{table}.{column}",
                    details={"count": len(unparsed), "samples": sorted(set(unparsed))[:5]},
                )

    # A missing table is skipped rather than an error, for the same reason
    # _add_column tolerates one: this database file is shared with the search
    # store, and a migration may run against a shape that does not have every
    # table yet.
    for table, index, column in _CALENDAR_INDEXES:
        if not connection.execute(f"PRAGMA table_info({table})").fetchone():
            continue
        connection.execute(f"CREATE INDEX IF NOT EXISTS {index} ON {table} ({column})")


def _migration_4_matter_reminders(connection: sqlite3.Connection) -> None:
    """Let one person in the firm put something on another's desk.

    This is the first user-to-user surface in a product that has only ever been
    one user per session, so it is also the first place where one seat's data is
    addressed to another. The shape reflects that: one row per recipient, so
    read and acknowledged state is per-person by construction rather than by
    convention. A reminder sent to five advocates is five rows, which at this
    scale costs nothing and removes an entire class of "who has seen this" bug.
    """
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS matter_reminders (
            reminder_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            recipient_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            due_date TEXT NOT NULL,
            priority TEXT NOT NULL,
            state TEXT NOT NULL,
            acknowledged_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_reminders_recipient
            ON matter_reminders (recipient_id, state);
        CREATE INDEX IF NOT EXISTS idx_reminders_due
            ON matter_reminders (due_date);
        CREATE INDEX IF NOT EXISTS idx_reminders_sender
            ON matter_reminders (sender_id);
        """
    )


def _migration_5_device_pairing(connection: sqlite3.Connection) -> None:
    """Let a phone be paired to a person, and unpaired again.

    ``revoked`` is the column that matters. A device token is long-lived by
    necessity -- a phone that syncs weekly cannot re-authenticate every ninety
    minutes -- and a long-lived credential with no way to withdraw it is an
    unbounded one. A lost phone has to be answerable in the minute it is
    reported, not in ninety days.
    """
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS device_pairings (
            pairing_code TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS paired_devices (
            device_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            device_name TEXT NOT NULL,
            platform TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_paired_devices_user
            ON paired_devices (user_id, revoked);
        """
    )


_MIGRATIONS: tuple[Callable[[sqlite3.Connection], None], ...] = (
    _migration_1_filing_record,
    _migration_2_filing_ledger,
    _migration_3_calendar_dates,
    _migration_4_matter_reminders,
    _migration_5_device_pairing,
)


def _migrate_schema(connection: sqlite3.Connection) -> None:
    """Bring an existing database up to ``SCHEMA_VERSION``.

    ``_create_schema`` is all ``CREATE TABLE IF NOT EXISTS``, so it is a no-op
    against a database that already exists -- new columns on existing tables
    would never appear, and the first query touching one would fail with
    ``no such column``. Every schema change after the first release therefore
    has to run through here.
    """
    current = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current >= SCHEMA_VERSION:
        return
    for version in range(current + 1, SCHEMA_VERSION + 1):
        _MIGRATIONS[version - 1](connection)
    # PRAGMA does not accept bound parameters.
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _create_schema(connection: sqlite3.Connection) -> None:
    """Create the baseline schema.

    This is the version-0 shape and should not be edited to add columns to
    existing tables: it is all ``CREATE TABLE IF NOT EXISTS``, so edits here
    reach new databases only. Evolve the schema in ``_MIGRATIONS`` instead,
    which runs against new and existing databases alike.
    """
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


def _sign_device_token(
    connection: sqlite3.Connection,
    *,
    device_id: str,
    user_id: str,
    role: str,
    expires_at: datetime,
) -> str:
    """A long-lived credential for one paired phone.

    Same signature scheme and same firm secret as a session token, with
    ``typ`` set so the two can never be confused. A device token is not a
    session: it lasts months rather than minutes, and it carries a narrower set
    of capabilities than the person it belongs to.
    """
    payload = {
        "typ": DEVICE_TOKEN_TYPE,
        "device_id": device_id,
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

    device_id = str(payload.get("device_id", ""))
    if str(payload.get("typ", "")) == DEVICE_TOKEN_TYPE:
        # The only revocable credential in the product. A session token expires
        # in ninety minutes and needs no withdrawal path; a device token lasts
        # months, so a lost phone must be answerable the minute it is reported.
        row = connection.execute(
            "SELECT revoked FROM paired_devices WHERE device_id = ?", (device_id,)
        ).fetchone()
        if row is None or int(row["revoked"]) != 0:
            raise AuthenticationError("this device has been unpaired")
        connection.execute(
            "UPDATE paired_devices SET last_seen_at = ? WHERE device_id = ?",
            (_datetime_to_text(_utc_now()), device_id),
        )

    return {
        "user_id": str(payload["user_id"]),
        "role": str(payload["role"]),
        "typ": str(payload.get("typ", SESSION_TOKEN_TYPE)),
        "device_id": device_id,
    }


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


_UPCOMING_ENTRIES_SQL = """
SELECT
    a.activity_id       AS entry_id,
    'hearing'           AS kind,
    a.matter_id         AS matter_id,
    a.starts_at         AS entry_date,
    a.title             AS title,
    a.status            AS status,
    a.court_session     AS detail,
    'matter_activities' AS source_table
FROM matter_activities a
WHERE a.calendar_visible = 1 AND a.starts_at <> ''
UNION ALL
SELECT
    l.lodging_id,
    'lodging_due',
    l.matter_id,
    l.due_date,
    'Lodging due: ' || l.document_kind,
    l.filing_status,
    l.filing_reference,
    'lodgings'
FROM lodgings l
WHERE l.due_date <> ''
UNION ALL
SELECT
    d.decision_id,
    'decision',
    d.matter_id,
    d.decision_date,
    'Court decision: ' || d.decision_type,
    '',
    d.outcome,
    'court_decisions'
FROM court_decisions d
WHERE d.decision_date <> ''
UNION ALL
SELECT
    f.filing_record_id,
    'next_action',
    f.matter_id,
    f.next_action_date,
    'Next action: ' || CASE WHEN f.next_action <> '' THEN f.next_action ELSE 'follow up' END,
    f.portal_status,
    f.tracking_number,
    'matter_filing_records'
FROM matter_filing_records f
WHERE f.next_action_date <> ''
"""
"""The four things that put a date in an advocate's diary.

One shape across four tables, so callers -- the daily reminder, the phone
snapshot, the calendar destination -- ask one question instead of four. Each
branch filters on a non-empty date so the indexes from migration 3 apply.
"""


def _pairing_code() -> str:
    return "".join(secrets.choice(PAIRING_CODE_ALPHABET) for _ in range(8))


def _snapshot_matter(row: sqlite3.Row) -> dict[str, object]:
    """A matter as a phone needs it: enough to recognise, not enough to weigh.

    The summary is truncated. A phone screen cannot show more, and the whole
    point of the snapshot's size budget is that nobody later adds document text
    to it one field at a time.
    """
    mapping = _matter_mapping(row)
    summary = str(mapping.get("summary") or "")
    mapping["summary"] = summary if len(summary) <= 500 else f"{summary[:497].rstrip()}..."
    return mapping


def _upcoming_mapping(row: sqlite3.Row) -> dict[str, object]:
    """Split the stored date into day and time for display.

    ``time`` is empty for an all-day entry, which is the difference between "in
    court at 09:00" and "due sometime on the 6th" -- a distinction the UI has to
    make and the storage format deliberately preserves.
    """
    stored = str(row["entry_date"])
    day, _, clock = stored.partition("T")
    return {
        "entry_id": str(row["entry_id"]),
        "kind": str(row["kind"]),
        "matter_id": str(row["matter_id"]),
        "matter_reference": str(row["matter_reference"]),
        "case_number": str(row["case_number"]),
        "client_name": str(row["client_name"]),
        "title": str(row["title"]),
        "date": day,
        "time": clock[:5],
        "status": str(row["status"] or ""),
        "detail": str(row["detail"] or ""),
        "source_table": str(row["source_table"]),
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
        "PRODID:-//JurisNuru//Matter Calendar//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:JurisNuru matters",
    ]
    now = _ics_datetime(_utc_now())
    for event in events:
        bounds = _ics_event_bounds(event["date"])
        if bounds is None:
            # Skip rather than emit the raw value. A date that will not parse
            # used to be written through verbatim, producing "DTSTART:TBC" --
            # which is not a parse failure for that one event, it is a parse
            # failure for the file, so no event at all reached the calendar.
            continue
        start, end = bounds
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{_escape_ics(event['uid'])}@jurisnuru",
                f"DTSTAMP:{now}",
                start,
                end,
                f"SUMMARY:{_escape_ics(event['summary'])}",
                f"DESCRIPTION:{_escape_ics(event['description'])}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    folded = [folded_line for line in lines for folded_line in _fold_ics(line)]
    return "\r\n".join(folded) + "\r\n"


def _ics_event_bounds(value: str) -> tuple[str, str] | None:
    """Build DTSTART/DTEND for one event, or ``None`` if the date is unusable.

    An all-day entry gets ``VALUE=DATE`` with an exclusive end on the next day,
    which is how RFC 5545 spells "occupies this whole day". A timed entry is
    written in Nairobi local time with an explicit TZID rather than converted to
    UTC, so a 09:00 mention still reads 09:00 in the advocate's calendar.
    """
    coerced = _coerce_matter_date(value)
    if not coerced:
        return None
    if "T" in coerced:
        start = datetime.fromisoformat(coerced)
        end = start + timedelta(hours=1)
        return (
            f"DTSTART;TZID=Africa/Nairobi:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND;TZID=Africa/Nairobi:{end.strftime('%Y%m%dT%H%M%S')}",
        )
    day = date.fromisoformat(coerced)
    return (
        f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}",
    )


def _fold_ics(line: str) -> list[str]:
    """Wrap a content line to 75 octets, per RFC 5545 section 3.1.

    Octets, not characters: the limit is on the encoded length, and a matter
    title carrying a Kiswahili diacritic would otherwise be measured short and
    emitted over-long. Continuation lines begin with a single space, which the
    parser strips when unfolding.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return [line]
    chunks: list[bytes] = []
    limit = 75
    while encoded:
        head, encoded = encoded[:limit], encoded[limit:]
        # Never split a multi-byte character: continuation bytes are 10xxxxxx,
        # so push them back until the boundary sits on a lead byte.
        while head and encoded and (encoded[0] & 0xC0) == 0x80:
            encoded = head[-1:] + encoded
            head = head[:-1]
        chunks.append(head)
        limit = 74  # the leading space costs one octet
    return [chunks[0].decode("utf-8")] + [f" {chunk.decode('utf-8')}" for chunk in chunks[1:]]


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


def _coerce_matter_date(value: str) -> str | None:
    """Return the canonical stored form of a matter date, or ``None``.

    ``None`` means "this is not a date", and callers differ on what to do about
    it: :func:`normalize_matter_date` refuses the write, while the backfill
    migration leaves the row alone. Returning a sentinel rather than raising is
    what lets the migration keep a value it cannot understand instead of
    destroying a firm's record.

    A naive datetime is taken to already be Nairobi local -- that is what the
    UI's own forms produce -- while anything carrying an offset is converted.
    """
    text = value.strip()
    if not text:
        return ""
    slashed = _SLASHED_DATE_PATTERN.match(text)
    if slashed is not None:
        # Day-first: the convention on the Judiciary portal and on every
        # Kenyan court form. Month-first would silently transpose 06/08.
        day, month, year = (int(part) for part in slashed.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    if _DATE_ONLY_PATTERN.match(text):
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            return None
    if "T" not in text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(NAIROBI)
    return parsed.strftime("%Y-%m-%dT%H:%M:%S")


def normalize_matter_date(value: object, *, field: str) -> str:
    """Canonicalise a date on the way in, or refuse it.

    Empty is allowed: these columns are legitimately optional, and a lodging
    with no due date yet is an ordinary state rather than an error.
    """
    coerced = _coerce_matter_date(str(value))
    if coerced is None:
        raise WakiliOSError(f"{field} is not a date: {str(value)!r}. Use {_ACCEPTED_DATE_FORMATS}.")
    return coerced


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)
