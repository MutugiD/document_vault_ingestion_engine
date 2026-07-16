"""Redacted hosted AI boundary smoke workflow."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from ai import (
    HostedAIDecision,
    HostedAIError,
    HostedAIRequest,
    HostedAITransportResponse,
    assert_hosted_prompt_privacy,
    build_hosted_ai_request,
    generate_hosted_ai_answer,
    local_rag_fallback,
    provider_health,
)
from rag import build_answer_packet, build_rag_index
from search import FILED_STATUS, add_document_version, create_document, create_matter
from vault import initialize_vault


def run_hosted_ai_e2e(workspace: Path | None = None) -> dict[str, object]:
    """Run a local-only hosted AI boundary check with redacted output."""

    if workspace is None:
        with tempfile.TemporaryDirectory(prefix="dv-hosted-ai-e2e-") as temporary_dir:
            return run_hosted_ai_e2e(Path(temporary_dir))

    vault_root = workspace / "vault"
    provider_environment = {"DOCUMENT_VAULT_OPENAI_API_KEY": "sk-hosted-ai-validator-key"}
    vault_session = initialize_vault(vault_root, "hosted ai validator passphrase")
    matter = create_matter(
        vault_root,
        internal_reference="HAI-001",
        client_name="Redacted Hosted AI Client",
        parties="Redacted Applicant v Redacted Respondent",
        court="High Court",
        station="Nairobi",
        case_number="HCOMM-HOSTED-AI",
        practice_area="Commercial",
        responsible_advocate="M. Mutugi",
    )
    stored = vault_session.write_object(
        b"invoice injunction affidavit",
        original_name="redacted-hosted-ai.pdf",
        content_type="application/pdf",
    )
    document = create_document(
        vault_root,
        matter_id=matter.matter_id,
        title="Invoice Injunction Affidavit",
        document_type="Affidavit",
    )
    add_document_version(
        vault_root,
        document_id=document.document_id,
        object_id=stored.object_id,
        source_sha256=stored.sha256,
        extracted_text=(
            "The affidavit supports an injunction because the invoice default created "
            "commercial urgency and the goods may be dissipated before hearing."
        ),
        lifecycle_status=FILED_STATUS,
    )
    build_rag_index(vault_root, matter_id=matter.matter_id)
    answer_packet = build_answer_packet(
        vault_root,
        "Why does the affidavit support injunctive relief?",
        matter_id=matter.matter_id,
    )
    decision = HostedAIDecision(hosted_ai_enabled=True, user_approved=True)
    request = build_hosted_ai_request(
        answer_packet,
        provider="openai",
        decision=decision,
        environment=provider_environment,
    )
    result = generate_hosted_ai_answer(
        vault_session=vault_session,
        answer_packet=answer_packet,
        provider="openai",
        decision=decision,
        transport=_fake_transport,
        environment=provider_environment,
        actor="hosted-ai-validator",
    )
    disabled_blocked = _raises_boundary_error(
        lambda: build_hosted_ai_request(
            answer_packet,
            provider="openai",
            decision=HostedAIDecision(
                hosted_ai_enabled=False,
                user_approved=True,
                reason="hosted AI entitlement disabled",
            ),
            environment=provider_environment,
        )
    )
    unapproved_blocked = _raises_boundary_error(
        lambda: build_hosted_ai_request(
            answer_packet,
            provider="openai",
            decision=HostedAIDecision(hosted_ai_enabled=True, user_approved=False),
            environment=provider_environment,
        )
    )
    missing_key_blocked = _raises_boundary_error(
        lambda: build_hosted_ai_request(
            answer_packet,
            provider="openai",
            decision=decision,
            environment={},
        )
    )
    no_context_packet = build_answer_packet(
        vault_root,
        "Question with no matching local matter context",
        matter_id="missing-matter",
    )
    no_context_blocked = _raises_boundary_error(
        lambda: build_hosted_ai_request(
            no_context_packet,
            provider="openai",
            decision=decision,
            environment=provider_environment,
        )
    )
    fallback = local_rag_fallback(
        vault_session=vault_session,
        answer_packet=answer_packet,
        provider="openai",
        reason="provider unavailable",
        actor="hosted-ai-validator",
    )
    unsafe_prompt_blocked = _raises_boundary_error(
        lambda: assert_hosted_prompt_privacy({"prompt": "contains recovery key material"})
    )
    health = provider_health("openai", environment=provider_environment)
    audit_events = vault_session.audit_events()

    return {
        "hosted_answer_status": result.status,
        "hosted_answer_has_citations": bool(result.citations),
        "hosted_answer_confidence": result.confidence,
        "request_provider": request.provider,
        "request_citation_count": len(request.citation_ids),
        "prompt_contains_context": "Cited local context:" in request.prompt,
        "prompt_contains_provider_key": provider_environment["DOCUMENT_VAULT_OPENAI_API_KEY"]
        in request.prompt,
        "provider_configured": health.configured,
        "provider_redacted_value": health.redacted_value,
        "disabled_blocked": disabled_blocked,
        "unapproved_blocked": unapproved_blocked,
        "missing_key_blocked": missing_key_blocked,
        "no_context_blocked": no_context_blocked,
        "fallback_status": fallback.status,
        "fallback_has_no_hosted_answer": fallback.answer == "",
        "unsafe_prompt_blocked": unsafe_prompt_blocked,
        "hosted_audit_recorded": any(
            event.event_type == "hosted_ai_answer_generated" for event in audit_events
        ),
        "fallback_audit_recorded": any(
            event.event_type == "hosted_ai_local_fallback" for event in audit_events
        ),
    }


def _fake_transport(request: HostedAIRequest) -> HostedAITransportResponse:
    return HostedAITransportResponse(
        answer=f"The cited local context supports injunctive relief [{request.citation_ids[0]}].",
        citation_ids=(request.citation_ids[0],),
    )


def _raises_boundary_error(callback: Callable[[], object]) -> bool:
    try:
        callback()
    except HostedAIError:
        return True
    return False


if __name__ == "__main__":
    import json

    print(json.dumps(run_hosted_ai_e2e(), indent=2, sort_keys=True))
