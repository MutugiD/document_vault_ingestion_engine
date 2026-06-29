"""Redacted Wakili-Mkononi integration boundary smoke workflow."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from integrations import (
    MatterExportPacket,
    WakiliIntegrationDecision,
    WakiliIntegrationError,
    assert_wakili_handoff_privacy,
    prepare_wakili_mkononi_handoff,
)
from rag import build_answer_packet, build_rag_index
from search import FILED_STATUS, add_document_version, create_document, create_matter
from vault import initialize_vault


def run_wakili_mkononi_e2e(workspace: Path | None = None) -> dict[str, object]:
    """Run a local-only integration boundary check with redacted output."""

    if workspace is None:
        with tempfile.TemporaryDirectory(prefix="dv-wakili-e2e-") as temporary_dir:
            return run_wakili_mkononi_e2e(Path(temporary_dir))

    vault_root = workspace / "vault"
    vault_passphrase = "wakili mkononi integration validator passphrase"
    vault_session = initialize_vault(vault_root, vault_passphrase)
    matter = create_matter(
        vault_root,
        internal_reference="WM-001",
        client_name="Redacted Test Client",
        parties="Redacted Test Client v Redacted Respondent",
        court="High Court",
        station="Nairobi",
        case_number="HCOMM-REDACTED",
        practice_area="Commercial",
        responsible_advocate="M. Mutugi",
    )
    stored = vault_session.write_object(
        b"injunction support affidavit body",
        original_name="redacted-affidavit.pdf",
        content_type="application/pdf",
    )
    document = create_document(
        vault_root,
        matter_id=matter.matter_id,
        title="Filed Injunction Application",
        document_type="Application",
    )
    add_document_version(
        vault_root,
        document_id=document.document_id,
        object_id=stored.object_id,
        source_sha256=stored.sha256,
        extracted_text=(
            "The filed application seeks an injunction restraining disposal of supplied "
            "goods pending hearing. The cited evidence includes invoice default and "
            "risk of dissipation before determination."
        ),
        lifecycle_status=FILED_STATUS,
    )
    build_rag_index(vault_root, matter_id=matter.matter_id)
    answer_packet = build_answer_packet(
        vault_root,
        "Which local citation supports injunctive relief?",
        matter_id=matter.matter_id,
    )
    matter_packet = MatterExportPacket(
        matter_id=matter.matter_id,
        safe_labels={
            "court": matter.court,
            "practice_area": matter.practice_area,
            "station": matter.station,
            "status": matter.status,
        },
    )
    handoff = prepare_wakili_mkononi_handoff(
        vault_session=vault_session,
        answer_packet=answer_packet,
        matter=matter_packet,
        decision=WakiliIntegrationDecision(enabled=True, user_approved=True),
        actor="integration-validator",
    )
    payload = handoff.to_mapping()

    blocked_without_approval = _raises_boundary_error(
        lambda: prepare_wakili_mkononi_handoff(
            vault_session=vault_session,
            answer_packet=answer_packet,
            matter=matter_packet,
            decision=WakiliIntegrationDecision(enabled=True, user_approved=False),
        )
    )
    blocked_without_entitlement = _raises_boundary_error(
        lambda: prepare_wakili_mkononi_handoff(
            vault_session=vault_session,
            answer_packet=answer_packet,
            matter=matter_packet,
            decision=WakiliIntegrationDecision(
                enabled=False,
                user_approved=True,
                reason="integration entitlement disabled",
            ),
        )
    )
    local_access_after_block = vault_session.read_object(stored.object_id) == (
        b"injunction support affidavit body"
    )
    unsafe_payload_blocked = _raises_boundary_error(
        lambda: assert_wakili_handoff_privacy({"grounded_context": answer_packet.grounded_context})
    )
    audit_events = vault_session.audit_events()

    return {
        "handoff_prepared": True,
        "schema_version": payload["schema_version"],
        "integration": payload["integration"],
        "citation_count": len(payload["citations"]),
        "confidence": payload["confidence"],
        "contains_grounded_context": "grounded_context" in payload,
        "contains_retrieval_results": "retrieval_results" in payload,
        "question_digest_length": len(str(payload["question_digest"])),
        "blocked_without_approval": blocked_without_approval,
        "blocked_without_entitlement": blocked_without_entitlement,
        "local_access_after_block": local_access_after_block,
        "unsafe_payload_blocked": unsafe_payload_blocked,
        "audit_event_recorded": any(
            event.event_type == "wakili_mkononi_handoff_prepared" for event in audit_events
        ),
    }


def _raises_boundary_error(callback: Callable[[], object]) -> bool:
    try:
        callback()
    except WakiliIntegrationError:
        return True
    return False


if __name__ == "__main__":
    import json

    print(json.dumps(run_wakili_mkononi_e2e(), indent=2, sort_keys=True))
