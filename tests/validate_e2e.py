"""Validate an end-to-end licensed local matter workflow."""

from __future__ import annotations

import base64
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

import fitz
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backup import (  # noqa: E402
    InMemoryGrantBackend,
    create_local_backup,
    create_upload_grant,
    restore_backup_package,
    upload_encrypted_snapshot,
)
from intake import ACCEPTED_STATUS, extract_text, import_document  # noqa: E402
from licensing import (  # noqa: E402
    ACTIVE_STATUS,
    FeatureEntitlements,
    LicenseDocument,
    canonical_license_bytes,
    ensure_installation_identity,
    verify_license_document,
)
from rag import build_answer_packet, build_rag_index  # noqa: E402
from search import (  # noqa: E402
    FILED_STATUS,
    add_document_version,
    create_document,
    create_matter,
    search_documents,
)
from vault import initialize_vault, open_vault  # noqa: E402


def main() -> None:
    recovery_key = "e2e recovery key"

    with tempfile.TemporaryDirectory() as temporary_dir:
        workspace = Path(temporary_dir)
        vault_root = workspace / "vault"
        restore_root = workspace / "restore"
        backup_path = workspace / "snapshot.wakilibak"

        identity = ensure_installation_identity(workspace / "settings" / "installation.json")
        public_key_pem, license_document = _signed_license(identity.installation_id)
        license_result = verify_license_document(
            license_document,
            public_key_pem,
            identity.installation_id,
            as_of=date(2026, 6, 26),
        )
        assert license_result.status == ACTIVE_STATUS
        assert license_result.feature_enabled("document_intake")
        assert license_result.feature_enabled("cloud_backup")
        assert license_result.feature_enabled("managed_restore")
        assert license_result.feature_enabled("matter_rag")

        vault_session = initialize_vault(vault_root, recovery_key)

        source_pdf = workspace / "injunction-application.pdf"
        expected_text = (
            "Urgent injunction application supported by invoice default evidence "
            "and risk of dissipation."
        )
        _write_pdf(source_pdf, expected_text)

        intake_record = import_document(vault_root, source_pdf)
        assert intake_record.status == ACCEPTED_STATUS
        extraction = extract_text(intake_record.quarantine_path)
        assert "invoice default evidence" in extraction.text

        stored_object = vault_session.write_object(
            intake_record.quarantine_path.read_bytes(),
            original_name=source_pdf.name,
            content_type="application/pdf",
            actor="e2e-validator",
        )

        matter = create_matter(
            vault_root,
            internal_reference="E2E-001",
            client_name="Amani Traders Ltd",
            parties="Amani Traders Ltd v Umoja Supplies",
            court="High Court",
            station="Nairobi",
            case_number="HCOMM E2E 001",
            practice_area="Commercial",
            responsible_advocate="M. Mutugi",
        )
        document = create_document(
            vault_root,
            matter_id=matter.matter_id,
            title="Urgent Injunction Application",
            document_type="Application",
            lifecycle_status=FILED_STATUS,
        )
        add_document_version(
            vault_root,
            document_id=document.document_id,
            object_id=stored_object.object_id,
            source_sha256=stored_object.sha256,
            extracted_text=extraction.text,
            lifecycle_status=FILED_STATUS,
        )

        search_results = search_documents(vault_root, "invoice default", matter_id=matter.matter_id)
        assert search_results
        assert search_results[0].matter_id == matter.matter_id

        assert build_rag_index(vault_root, matter_id=matter.matter_id) >= 1
        answer_packet = build_answer_packet(
            vault_root,
            "What supports the injunction?",
            matter_id=matter.matter_id,
        )
        assert answer_packet.citations
        assert "invoice default evidence" in answer_packet.grounded_context

        backup_package = create_local_backup(
            vault_root,
            backup_path,
            recovery_key=recovery_key,
            installation_id=identity.installation_id,
        )
        backend = InMemoryGrantBackend()
        upload_result = upload_encrypted_snapshot(
            create_upload_grant(
                "azure",
                identity.installation_id,
                backup_package.manifest.snapshot_id,
            ),
            backup_path,
            backend=backend,
        )
        assert upload_result.metadata["snapshot_id"] == backup_package.manifest.snapshot_id
        assert b"Amani Traders" not in backup_path.read_bytes()
        assert expected_text.encode() not in backup_path.read_bytes()

        restore_report = restore_backup_package(
            backup_path,
            restore_root,
            recovery_key=recovery_key,
        )
        restored_session = open_vault(restore_report.restored_path, recovery_key)
        assert restored_session.read_object(stored_object.object_id) == source_pdf.read_bytes()

    print("E2E VALIDATION PASS")


def _write_pdf(path: Path, text: str) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def _signed_license(installation_id: str) -> tuple[bytes, LicenseDocument]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    unsigned_document = LicenseDocument(
        installation_id=installation_id,
        license_id="LIC-E2E-TEST",
        firm_display_name="Example Advocates LLP",
        plan="firm",
        features=FeatureEntitlements(
            document_intake=True,
            cloud_backup=True,
            managed_restore=True,
            matter_rag=True,
        ),
        expiry=date(2099, 12, 31),
        issued_at=datetime(2026, 6, 26, 10, 0, tzinfo=UTC),
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
