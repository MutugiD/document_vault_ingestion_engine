"""Wakili-Mkononi integration boundary for user-approved citation handoff."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from rag import Citation, RagAnswerPacket
from vault import VaultSession

HANDOFF_SCHEMA_VERSION = "1"
HANDOFF_AUDIT_EVENT = "wakili_mkononi_handoff_prepared"
ALLOWED_MATTER_LABELS = frozenset({"court", "station", "practice_area", "status"})
FORBIDDEN_KEY_MARKERS = (
    "client",
    "case",
    "party",
    "parties",
    "filename",
    "file_name",
    "original_name",
    "ocr",
    "extracted",
    "grounded_context",
    "retrieval_results",
    "source_sha256",
    "file_hash",
    "recovery",
    "credential",
    "secret",
    "api_key",
)


class WakiliIntegrationError(Exception):
    """Raised when a Wakili-Mkononi handoff violates the local boundary."""


@dataclass(frozen=True)
class WakiliIntegrationDecision:
    """Local entitlement and user-approval decision for a handoff."""

    enabled: bool
    user_approved: bool
    reason: str = ""

    def require_allowed(self) -> None:
        if not self.user_approved:
            raise WakiliIntegrationError("Wakili-Mkononi handoff requires user approval")
        if not self.enabled:
            raise WakiliIntegrationError(self.reason or "Wakili-Mkononi integration is not enabled")


@dataclass(frozen=True)
class MatterExportPacket:
    """Minimal user-approved matter reference sent outside the local vault."""

    matter_id: str
    safe_labels: dict[str, str]

    def to_mapping(self) -> dict[str, object]:
        unsafe_labels = set(self.safe_labels).difference(ALLOWED_MATTER_LABELS)
        if unsafe_labels:
            names = ", ".join(sorted(unsafe_labels))
            raise WakiliIntegrationError(f"unsafe matter export label(s): {names}")
        payload = {
            "matter_id": self.matter_id,
            "safe_labels": dict(sorted(self.safe_labels.items())),
        }
        assert_wakili_handoff_privacy(payload)
        return payload


@dataclass(frozen=True)
class CitationHandoff:
    """Citation metadata preserved for a user-approved Wakili-Mkononi handoff."""

    citation_id: str
    matter_id: str
    document_id: str
    version_id: str
    title: str
    chunk_index: int

    @classmethod
    def from_citation(cls, citation: Citation) -> CitationHandoff:
        return cls(
            citation_id=citation.citation_id,
            matter_id=citation.matter_id,
            document_id=citation.document_id,
            version_id=citation.version_id,
            title=citation.title,
            chunk_index=citation.chunk_index,
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "citation_id": self.citation_id,
            "matter_id": self.matter_id,
            "document_id": self.document_id,
            "version_id": self.version_id,
            "title": self.title,
            "chunk_index": self.chunk_index,
        }


@dataclass(frozen=True)
class WakiliMkononiHandoff:
    """Privacy-checked packet ready for an external Wakili-Mkononi transport."""

    schema_version: str
    integration: str
    created_at: datetime
    matter: MatterExportPacket
    question_digest: str
    confidence: float
    citations: tuple[CitationHandoff, ...]
    user_approved: bool
    payload_notice: str

    def to_mapping(self) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "integration": self.integration,
            "created_at": _datetime_to_text(self.created_at),
            "matter": self.matter.to_mapping(),
            "question_digest": self.question_digest,
            "confidence": self.confidence,
            "citations": [citation.to_mapping() for citation in self.citations],
            "user_approved": self.user_approved,
            "payload_notice": self.payload_notice,
        }
        assert_wakili_handoff_privacy(payload)
        return payload


def prepare_wakili_mkononi_handoff(
    *,
    vault_session: VaultSession,
    answer_packet: RagAnswerPacket,
    matter: MatterExportPacket,
    decision: WakiliIntegrationDecision,
    actor: str = "system",
    created_at: datetime | None = None,
) -> WakiliMkononiHandoff:
    """Prepare a user-approved citation packet and record a local audit event."""

    decision.require_allowed()
    if not answer_packet.citations:
        raise WakiliIntegrationError("handoff requires at least one local RAG citation")

    handoff = WakiliMkononiHandoff(
        schema_version=HANDOFF_SCHEMA_VERSION,
        integration="wakili-mkononi",
        created_at=created_at or datetime.now(UTC),
        matter=matter,
        question_digest=_digest_text(answer_packet.question),
        confidence=answer_packet.confidence,
        citations=tuple(
            CitationHandoff.from_citation(citation) for citation in answer_packet.citations
        ),
        user_approved=decision.user_approved,
        payload_notice=(
            "User-approved citation metadata only. Raw document text and vault secrets stay local."
        ),
    )
    payload = handoff.to_mapping()
    vault_session.record_audit_event(
        event_type=HANDOFF_AUDIT_EVENT,
        actor=actor,
        details={
            "integration": "wakili-mkononi",
            "matter_id": matter.matter_id,
            "citation_count": len(handoff.citations),
            "confidence": handoff.confidence,
            "question_digest": handoff.question_digest,
        },
    )
    return WakiliMkononiHandoff(
        schema_version=str(payload["schema_version"]),
        integration=str(payload["integration"]),
        created_at=handoff.created_at,
        matter=matter,
        question_digest=str(payload["question_digest"]),
        confidence=float(payload["confidence"]),
        citations=handoff.citations,
        user_approved=bool(payload["user_approved"]),
        payload_notice=str(payload["payload_notice"]),
    )


def assert_wakili_handoff_privacy(payload: dict[str, object]) -> dict[str, object]:
    """Reject fields that would leak uncontrolled legal content or vault secrets."""

    _walk_payload(payload)
    return payload


def _walk_payload(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = str(key).lower()
            if any(marker in normalized_key for marker in FORBIDDEN_KEY_MARKERS):
                raise WakiliIntegrationError(f"forbidden handoff field: {path}{key}")
            _walk_payload(nested, f"{path}{key}.")
        return
    if isinstance(value, list | tuple):
        for index, nested in enumerate(value):
            _walk_payload(nested, f"{path}{index}.")
        return
    if isinstance(value, str) and _looks_like_sensitive_material(value):
        raise WakiliIntegrationError(f"forbidden handoff value at {path.rstrip('.')}")


def _looks_like_sensitive_material(value: str) -> bool:
    lowered = value.lower()
    markers = (
        "recovery key",
        "aws_secret_access_key",
        "azure connection string",
        "gcp service account",
        "-----begin private key-----",
    )
    return any(marker in lowered for marker in markers)


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _datetime_to_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
