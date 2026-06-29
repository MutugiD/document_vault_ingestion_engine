"""Hosted AI boundary constrained by local RAG citations."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ai.providers import configured_provider_statuses, provider_env_var
from rag import Citation, RagAnswerPacket
from vault import VaultSession

HOSTED_AI_AUDIT_EVENT = "hosted_ai_answer_generated"
HOSTED_AI_FALLBACK_AUDIT_EVENT = "hosted_ai_local_fallback"
HOSTED_AI_SCHEMA_VERSION = "1"

FORBIDDEN_PROMPT_MARKERS = (
    "recovery key",
    "aws_secret_access_key",
    "azure connection string",
    "gcp service account",
    "-----begin private key-----",
)


class HostedAIError(Exception):
    """Raised when hosted AI would violate the local RAG boundary."""


@dataclass(frozen=True)
class HostedAIProviderHealth:
    provider: str
    configured: bool
    redacted_value: str

    def to_mapping(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "redacted_value": self.redacted_value,
        }


@dataclass(frozen=True)
class HostedAIDecision:
    hosted_ai_enabled: bool
    user_approved: bool
    reason: str = ""

    def require_allowed(self) -> None:
        if not self.user_approved:
            raise HostedAIError("hosted AI requires user approval")
        if not self.hosted_ai_enabled:
            raise HostedAIError(self.reason or "hosted AI entitlement is disabled")


@dataclass(frozen=True)
class HostedAIRequest:
    schema_version: str
    provider: str
    question: str
    prompt: str
    citation_ids: tuple[str, ...]
    confidence: float

    def to_mapping(self) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "question": self.question,
            "prompt": self.prompt,
            "citation_ids": list(self.citation_ids),
            "confidence": self.confidence,
        }
        assert_hosted_prompt_privacy(payload)
        return payload


@dataclass(frozen=True)
class HostedAITransportResponse:
    answer: str
    citation_ids: tuple[str, ...]


@dataclass(frozen=True)
class HostedAIResult:
    status: str
    provider: str
    answer: str
    citations: tuple[Citation, ...]
    confidence: float
    created_at: datetime
    fallback_reason: str = ""

    def to_mapping(self) -> dict[str, object]:
        return {
            "status": self.status,
            "provider": self.provider,
            "answer": self.answer,
            "citations": [
                {
                    "citation_id": citation.citation_id,
                    "matter_id": citation.matter_id,
                    "document_id": citation.document_id,
                    "version_id": citation.version_id,
                    "title": citation.title,
                    "chunk_index": citation.chunk_index,
                }
                for citation in self.citations
            ],
            "confidence": self.confidence,
            "created_at": self.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "fallback_reason": self.fallback_reason,
        }


HostedAITransport = Callable[[HostedAIRequest], HostedAITransportResponse]


def provider_health(
    provider: str,
    *,
    environment: dict[str, str] | None = None,
) -> HostedAIProviderHealth:
    env_var = provider_env_var(provider)
    status = next(
        item
        for item in configured_provider_statuses(environment)
        if item.provider == provider and item.env_var == env_var
    )
    return HostedAIProviderHealth(
        provider=status.provider,
        configured=status.configured,
        redacted_value=status.redacted_value,
    )


def build_hosted_ai_request(
    answer_packet: RagAnswerPacket,
    *,
    provider: str,
    decision: HostedAIDecision,
    environment: dict[str, str] | None = None,
) -> HostedAIRequest:
    """Build the only payload allowed to cross the hosted AI boundary."""

    decision.require_allowed()
    health = provider_health(provider, environment=environment)
    if not health.configured:
        raise HostedAIError(f"provider key is not configured for {provider}")
    if not answer_packet.citations or not answer_packet.grounded_context.strip():
        raise HostedAIError("hosted AI requires cited local context")
    prompt = (
        "Answer only from the cited local matter context below. "
        "Every answer must cite at least one provided citation ID. "
        "If the context is insufficient, say that the local context is insufficient.\n\n"
        f"Question: {answer_packet.question}\n\n"
        f"Cited local context:\n{answer_packet.grounded_context}\n\n"
        "Return a concise answer with citation IDs."
    )
    request = HostedAIRequest(
        schema_version=HOSTED_AI_SCHEMA_VERSION,
        provider=provider,
        question=answer_packet.question,
        prompt=prompt,
        citation_ids=tuple(citation.citation_id for citation in answer_packet.citations),
        confidence=answer_packet.confidence,
    )
    request.to_mapping()
    return request


def generate_hosted_ai_answer(
    *,
    vault_session: VaultSession,
    answer_packet: RagAnswerPacket,
    provider: str,
    decision: HostedAIDecision,
    transport: HostedAITransport,
    environment: dict[str, str] | None = None,
    actor: str = "system",
    created_at: datetime | None = None,
) -> HostedAIResult:
    request = build_hosted_ai_request(
        answer_packet,
        provider=provider,
        decision=decision,
        environment=environment,
    )
    response = transport(request)
    _validate_provider_response(response, request)
    result = HostedAIResult(
        status="hosted_answer",
        provider=provider,
        answer=response.answer,
        citations=tuple(
            citation
            for citation in answer_packet.citations
            if citation.citation_id in set(response.citation_ids)
        ),
        confidence=answer_packet.confidence,
        created_at=created_at or datetime.now(UTC),
    )
    _assert_result_has_citations(result)
    vault_session.record_audit_event(
        event_type=HOSTED_AI_AUDIT_EVENT,
        actor=actor,
        details={
            "provider": provider,
            "citation_count": len(result.citations),
            "confidence": result.confidence,
        },
    )
    return result


def local_rag_fallback(
    *,
    vault_session: VaultSession,
    answer_packet: RagAnswerPacket,
    provider: str,
    reason: str,
    actor: str = "system",
    created_at: datetime | None = None,
) -> HostedAIResult:
    result = HostedAIResult(
        status="local_rag_fallback",
        provider=provider,
        answer="",
        citations=answer_packet.citations,
        confidence=answer_packet.confidence,
        created_at=created_at or datetime.now(UTC),
        fallback_reason=reason,
    )
    vault_session.record_audit_event(
        event_type=HOSTED_AI_FALLBACK_AUDIT_EVENT,
        actor=actor,
        details={
            "provider": provider,
            "citation_count": len(result.citations),
            "confidence": result.confidence,
            "reason": reason,
        },
    )
    return result


def assert_hosted_prompt_privacy(payload: dict[str, object]) -> dict[str, object]:
    serialized = json.dumps(payload, sort_keys=True).lower()
    for marker in FORBIDDEN_PROMPT_MARKERS:
        if marker in serialized:
            raise HostedAIError(f"hosted AI payload contains forbidden material: {marker}")
    return payload


def _validate_provider_response(
    response: HostedAITransportResponse,
    request: HostedAIRequest,
) -> None:
    if not response.answer.strip():
        raise HostedAIError("hosted provider returned an empty answer")
    if not response.citation_ids:
        raise HostedAIError("hosted provider returned no citations")
    allowed = set(request.citation_ids)
    unexpected = set(response.citation_ids) - allowed
    if unexpected:
        raise HostedAIError(f"hosted provider returned unknown citations: {sorted(unexpected)}")


def _assert_result_has_citations(result: HostedAIResult) -> None:
    if not result.citations:
        raise HostedAIError("hosted answer must preserve local citations")
