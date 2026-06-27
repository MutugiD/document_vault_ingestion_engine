"""Validate F10 Local Matter RAG Connector behavior."""

from __future__ import annotations

import base64
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from licensing import (  # noqa: E402
    ACTIVE_STATUS,
    FeatureEntitlements,
    LicenseDocument,
    canonical_license_bytes,
    ensure_installation_identity,
    verify_license_document,
)
from rag import build_answer_packet, build_rag_index, chunk_text, retrieve_context  # noqa: E402
from search import (  # noqa: E402
    DRAFT_STATUS,
    FILED_STATUS,
    add_document_version,
    create_document,
    create_matter,
)
from vault import initialize_vault  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        workspace = Path(temporary_dir)
        vault_root = workspace / "vault"
        identity = ensure_installation_identity(workspace / "settings" / "installation.json")
        public_key_pem, active_license = _signed_license(identity.installation_id)
        license_result = verify_license_document(
            active_license,
            public_key_pem,
            identity.installation_id,
            as_of=date(2026, 6, 26),
        )
        assert license_result.status == ACTIVE_STATUS
        assert license_result.feature_enabled("matter_rag")

        vault_session = initialize_vault(vault_root, "rag validator recovery key")
        nairobi_matter = create_matter(
            vault_root,
            internal_reference="RAG-001",
            client_name="Amani Traders Ltd",
            parties="Amani Traders Ltd v Umoja Supplies",
            court="High Court",
            station="Nairobi",
            case_number="HCOMM RAG 001",
            practice_area="Commercial",
            responsible_advocate="M. Mutugi",
        )
        kisumu_matter = create_matter(
            vault_root,
            internal_reference="RAG-002",
            client_name="Lake Basin Co",
            parties="Lake Basin Co v County Office",
            court="ELC",
            station="Kisumu",
            case_number="ELC RAG 002",
            practice_area="Land",
            responsible_advocate="M. Mutugi",
        )

        injunction_object = vault_session.write_object(
            b"injunction document",
            original_name="injunction.pdf",
            content_type="application/pdf",
        )
        injunction_document = create_document(
            vault_root,
            matter_id=nairobi_matter.matter_id,
            title="Filed Injunction Application",
            document_type="Application",
        )
        add_document_version(
            vault_root,
            document_id=injunction_document.document_id,
            object_id=injunction_object.object_id,
            source_sha256=injunction_object.sha256,
            extracted_text=(
                "The filed application seeks an injunction restraining disposal of supplied "
                "goods pending hearing. The supporting affidavit cites invoice default, "
                "commercial urgency, and risk of dissipation."
            ),
            lifecycle_status=FILED_STATUS,
        )

        land_object = vault_session.write_object(
            b"land document",
            original_name="boundary.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        land_document = create_document(
            vault_root,
            matter_id=kisumu_matter.matter_id,
            title="Boundary Affidavit",
            document_type="Affidavit",
        )
        add_document_version(
            vault_root,
            document_id=land_document.document_id,
            object_id=land_object.object_id,
            source_sha256=land_object.sha256,
            extracted_text=(
                "The affidavit concerns a Kisumu boundary dispute and occupation history. "
                "It does not discuss commercial injunction relief."
            ),
            lifecycle_status=DRAFT_STATUS,
        )

        assert len(chunk_text("one two three four", chunk_words=3, overlap_words=1)) == 2
        indexed_count = build_rag_index(vault_root)
        assert indexed_count == 2

        global_results = retrieve_context(vault_root, "commercial injunction invoice", top_k=2)
        assert global_results
        assert global_results[0].chunk.matter_id == nairobi_matter.matter_id
        assert global_results[0].citation.citation_id == "C1"
        assert global_results[0].rerank_score >= global_results[-1].rerank_score
        assert 0 < global_results[0].confidence <= 1

        scoped_results = retrieve_context(
            vault_root,
            "commercial injunction invoice",
            matter_id=nairobi_matter.matter_id,
        )
        assert scoped_results
        assert all(result.chunk.matter_id == nairobi_matter.matter_id for result in scoped_results)

        excluded_results = retrieve_context(
            vault_root,
            "invoice default",
            matter_id=kisumu_matter.matter_id,
        )
        assert excluded_results == ()

        packet = build_answer_packet(
            vault_root,
            "What evidence supports the injunction application?",
            matter_id=nairobi_matter.matter_id,
        )
        assert packet.citations
        assert "[C1]" in packet.grounded_context
        assert "Use only the cited local context" in packet.safety_notice
        assert "invoice default" in packet.grounded_context
        assert 0 < packet.confidence <= 1

    print("RAG VALIDATION PASS")


def _signed_license(installation_id: str) -> tuple[bytes, LicenseDocument]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    unsigned_document = LicenseDocument(
        installation_id=installation_id,
        license_id="LIC-RAG-TEST",
        firm_display_name="Example Advocates LLP",
        plan="firm",
        features=FeatureEntitlements(
            document_intake=True,
            cloud_backup=True,
            managed_restore=True,
            matter_rag=True,
        ),
        expiry=date(2099, 12, 31),
        issued_at=datetime(2026, 6, 26, 9, 0, tzinfo=UTC),
        signature="",
    )
    signature = private_key.sign(
        canonical_license_bytes(unsigned_document),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return public_key_pem, LicenseDocument(
        installation_id=unsigned_document.installation_id,
        license_id=unsigned_document.license_id,
        firm_display_name=unsigned_document.firm_display_name,
        plan=unsigned_document.plan,
        features=unsigned_document.features,
        expiry=unsigned_document.expiry,
        issued_at=unsigned_document.issued_at,
        signature=base64.b64encode(signature).decode("ascii"),
    )


if __name__ == "__main__":
    main()
