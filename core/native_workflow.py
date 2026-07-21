"""Native app workflow runner shared by CLI, UI, and validators."""

from __future__ import annotations

import base64
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import fitz
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from ai import configured_provider_statuses
from backup import (
    InMemoryGrantBackend,
    create_local_backup,
    create_upload_grant,
    restore_backup_package,
    upload_encrypted_snapshot,
)
from intake import ACCEPTED_STATUS, DUPLICATE_STATUS, extract_document, import_document
from licensing import (
    ACTIVE_STATUS,
    FeatureEntitlements,
    LicenseDocument,
    canonical_license_bytes,
    ensure_installation_identity,
    verify_license_document,
)
from rag import build_answer_packet, build_rag_index
from search import (
    FILED_STATUS,
    add_document_version,
    create_document,
    create_matter,
    search_documents,
)
from vault import initialize_vault, open_vault


class NativeWorkflowError(Exception):
    """Raised when the native end-to-end workflow cannot complete."""


@dataclass(frozen=True)
class NativeWorkflowReport:
    setup_completed: bool
    license_status: str
    enabled_features: tuple[str, ...]
    vault_initialized: bool
    accepted_imports: int
    duplicate_detected: bool
    extraction_status: str
    matter_created: bool
    search_results: int
    rag_citations: int
    rag_confidence: float
    backup_created: bool
    restore_verified: bool
    provider_statuses: tuple[dict[str, object], ...]

    def to_mapping(self) -> dict[str, object]:
        return {
            "setup_completed": self.setup_completed,
            "license_status": self.license_status,
            "enabled_features": list(self.enabled_features),
            "vault_initialized": self.vault_initialized,
            "accepted_imports": self.accepted_imports,
            "duplicate_detected": self.duplicate_detected,
            "extraction_status": self.extraction_status,
            "matter_created": self.matter_created,
            "search_results": self.search_results,
            "rag_citations": self.rag_citations,
            "rag_confidence": self.rag_confidence,
            "backup_created": self.backup_created,
            "restore_verified": self.restore_verified,
            "provider_statuses": list(self.provider_statuses),
        }


def run_native_app_workflow(
    workspace: Path | None = None,
    *,
    provider_environment: dict[str, str] | None = None,
) -> NativeWorkflowReport:
    """Run a redacted end-to-end local workflow for the native app boundary."""

    if workspace is None:
        with tempfile.TemporaryDirectory(prefix="dv-native-workflow-") as temporary_dir:
            return run_native_app_workflow(
                Path(temporary_dir),
                provider_environment=provider_environment,
            )

    workspace.mkdir(parents=True, exist_ok=True)
    workflow_passphrase = "native workflow passphrase"
    vault_root = workspace / "vault"
    backup_path = workspace / "native-workflow.wakilibak"
    restore_root = workspace / "restore"

    identity = ensure_installation_identity(workspace / "settings" / "installation.json")
    public_key_pem, license_document = _signed_license(identity.installation_id)
    license_result = verify_license_document(
        license_document,
        public_key_pem,
        identity.installation_id,
        as_of=date(2026, 6, 26),
    )
    if license_result.status != ACTIVE_STATUS:
        raise NativeWorkflowError(f"license status was {license_result.status}")

    vault_session = initialize_vault(vault_root, workflow_passphrase)
    source_pdf = workspace / "workflow-application.pdf"
    expected_text = (
        "Urgent injunction application supported by invoice default evidence "
        "and risk of asset dissipation."
    )
    _write_pdf(source_pdf, expected_text)

    intake_record = import_document(vault_root, source_pdf)
    duplicate_record = import_document(vault_root, source_pdf)
    if intake_record.status != ACCEPTED_STATUS:
        raise NativeWorkflowError(f"intake status was {intake_record.status}")
    if duplicate_record.status != DUPLICATE_STATUS:
        raise NativeWorkflowError("duplicate import was not detected")

    extraction = extract_document(intake_record.quarantine_path)
    if "invoice default evidence" not in extraction.text:
        raise NativeWorkflowError("expected extracted text was not available")

    stored_object = vault_session.write_object(
        intake_record.quarantine_path.read_bytes(),
        original_name=source_pdf.name,
        content_type="application/pdf",
        actor="native-workflow",
    )
    matter = create_matter(
        vault_root,
        internal_reference="NATIVE-WORKFLOW-001",
        client_name="Demo Client Ltd",
        parties="Demo Client Ltd v Demo Supplier Ltd",
        court="High Court",
        station="Nairobi",
        case_number="HCOMM NATIVE 001",
        practice_area="Commercial",
        responsible_advocate="Demo Advocate",
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
    indexed_chunks = build_rag_index(vault_root, matter_id=matter.matter_id)
    if indexed_chunks < 1 or not search_results:
        raise NativeWorkflowError("search/RAG index did not produce local context")

    answer_packet = build_answer_packet(
        vault_root,
        "What evidence supports the injunction application?",
        matter_id=matter.matter_id,
    )
    if not answer_packet.citations or answer_packet.confidence <= 0:
        raise NativeWorkflowError("RAG did not produce cited local context")

    backup_package = create_local_backup(
        vault_root,
        backup_path,
        recovery_key=workflow_passphrase,
        installation_id=identity.installation_id,
    )
    backend = InMemoryGrantBackend()
    upload_result = upload_encrypted_snapshot(
        create_upload_grant(
            "aws",
            identity.installation_id,
            backup_package.manifest.snapshot_id,
        ),
        backup_path,
        backend=backend,
    )
    if upload_result.metadata["snapshot_id"] != backup_package.manifest.snapshot_id:
        raise NativeWorkflowError("backup upload metadata did not match snapshot")

    backup_bytes = backup_path.read_bytes()
    _assert_backup_redacted(backup_bytes, expected_text, provider_environment)

    restore_report = restore_backup_package(
        backup_path,
        restore_root,
        recovery_key=workflow_passphrase,
    )
    restored_session = open_vault(restore_report.restored_path, workflow_passphrase)
    restored_bytes = restored_session.read_object(stored_object.object_id)
    restore_verified = restored_bytes == source_pdf.read_bytes()
    if not restore_verified:
        raise NativeWorkflowError("restore verification failed")

    provider_statuses = tuple(
        status.to_mapping() for status in configured_provider_statuses(provider_environment)
    )
    enabled_features = tuple(
        feature
        for feature in ("document_intake", "cloud_backup", "managed_restore", "matter_rag")
        if license_result.feature_enabled(feature)
    )
    return NativeWorkflowReport(
        setup_completed=True,
        license_status=license_result.status,
        enabled_features=enabled_features,
        vault_initialized=True,
        accepted_imports=1,
        duplicate_detected=True,
        extraction_status=extraction.ocr_status,
        matter_created=True,
        search_results=len(search_results),
        rag_citations=len(answer_packet.citations),
        rag_confidence=answer_packet.confidence,
        backup_created=backup_path.exists(),
        restore_verified=restore_verified,
        provider_statuses=provider_statuses,
    )


def _assert_backup_redacted(
    backup_bytes: bytes,
    expected_text: str,
    provider_environment: dict[str, str] | None,
) -> None:
    if expected_text.encode() in backup_bytes:
        raise NativeWorkflowError("backup package contains plaintext legal text")
    for value in (provider_environment or {}).values():
        if value and value.encode() in backup_bytes:
            raise NativeWorkflowError("backup package contains a provider key")


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
        license_id="LIC-NATIVE-WORKFLOW",
        firm_display_name="Native Workflow Advocates",
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
