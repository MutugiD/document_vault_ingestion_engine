"""Run a local-only private-document smoke test outside the repository."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backup import create_local_backup, restore_backup_package  # noqa: E402
from intake import (  # noqa: E402
    ACCEPTED_STATUS,
    DUPLICATE_STATUS,
    OCR_COMPLETED,
    OCR_NOT_REQUIRED,
    OCR_PENDING,
    REJECTED_STATUS,
    extract_text,
    import_document,
)
from intake.ocr_runtime import discover_tesseract_runtime  # noqa: E402
from rag import build_answer_packet, build_rag_index  # noqa: E402
from search import (  # noqa: E402
    DRAFT_STATUS,
    add_document_version,
    create_document,
    create_matter,
    search_documents,
)
from vault import initialize_vault, open_vault  # noqa: E402

SUPPORTED_INPUT_SUFFIXES = {".pdf", ".docx", ".doc"}
CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@dataclass(frozen=True)
class StoredSmokeDocument:
    source_path: Path
    quarantine_path: Path
    object_id: str
    extracted_text: str
    detected_file_type: str
    ocr_status: str


class SmokeFailure(Exception):
    """Raised when the private-document smoke test cannot prove a required stage."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a redacted local ingest smoke test against private documents.",
    )
    parser.add_argument("--input", required=True, type=Path, help="Folder containing private docs.")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Optional scratch workspace. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Keep the scratch workspace for manual inspection.",
    )
    args = parser.parse_args(argv)

    try:
        input_root = args.input.resolve()
        _validate_input_root(input_root)
        if args.workspace is None:
            with tempfile.TemporaryDirectory(prefix="dv-private-smoke-") as temporary_dir:
                summary = run_smoke(input_root, Path(temporary_dir).resolve())
        else:
            workspace = args.workspace.resolve()
            if workspace.exists() and not args.keep_workspace:
                shutil.rmtree(workspace)
            workspace.mkdir(parents=True, exist_ok=True)
            summary = run_smoke(input_root, workspace)
            if not args.keep_workspace:
                shutil.rmtree(workspace)
        print("MANUAL INGEST SMOKE PASS")
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except SmokeFailure as exc:
        print("MANUAL INGEST SMOKE FAIL")
        print(str(exc))
        return 1


def run_smoke(input_root: Path, workspace: Path) -> dict[str, object]:
    source_paths = _private_document_paths(input_root)
    if not source_paths:
        raise SmokeFailure("input folder has no PDF, DOCX, or legacy DOC files")

    pdf_paths = [path for path in source_paths if path.suffix.lower() == ".pdf"]
    docx_paths = [path for path in source_paths if path.suffix.lower() == ".docx"]
    legacy_doc_paths = [path for path in source_paths if path.suffix.lower() == ".doc"]
    if not pdf_paths:
        raise SmokeFailure("at least one PDF is required")
    if not docx_paths:
        raise SmokeFailure("at least one DOCX is required")
    if not legacy_doc_paths:
        raise SmokeFailure("at least one unsupported legacy .doc file is required")

    recovery_key = f"manual-smoke-{uuid4()}"
    installation_id = f"manual-smoke-installation-{uuid4()}"
    vault_root = workspace / "vault"
    backup_path = workspace / "backups" / "manual-smoke.wakilibak"
    restore_root = workspace / "restore"
    duplicate_root = workspace / "duplicate-source"
    duplicate_root.mkdir(parents=True, exist_ok=True)

    ocr_engine = discover_tesseract_runtime()
    vault_session = initialize_vault(vault_root, recovery_key)
    matter = create_matter(
        vault_root,
        internal_reference="PRIVATE-SMOKE-001",
        client_name="Private Smoke Client",
        parties="Private Smoke Client v Private Smoke Respondent",
        court="Local Smoke Court",
        station="Local",
        case_number="PRIVATE-SMOKE-001",
        practice_area="Validation",
        responsible_advocate="Local Operator",
    )

    stored_documents: list[StoredSmokeDocument] = []
    scanned_pdf_seen = False
    for source_path in [*pdf_paths, docx_paths[0]]:
        stored = _ingest_store_and_index(
            vault_root,
            vault_session,
            matter.matter_id,
            source_path,
            sequence=len(stored_documents) + 1,
            ocr_engine=ocr_engine,
        )
        stored_documents.append(stored)
        if stored.detected_file_type == "pdf" and stored.ocr_status in {OCR_PENDING, OCR_COMPLETED}:
            if not stored.extracted_text or stored.ocr_status == OCR_COMPLETED:
                scanned_pdf_seen = True
        if scanned_pdf_seen and any(document.extracted_text for document in stored_documents):
            break

    if not scanned_pdf_seen:
        raise SmokeFailure("at least one scanned/image-only PDF is required")
    if not any(document.detected_file_type == "docx" for document in stored_documents):
        stored_documents.append(
            _ingest_store_and_index(
                vault_root,
                vault_session,
                matter.matter_id,
                docx_paths[0],
                sequence=len(stored_documents) + 1,
                ocr_engine=ocr_engine,
            )
        )

    searchable_documents = [document for document in stored_documents if document.extracted_text]
    if not searchable_documents:
        raise SmokeFailure("at least one PDF or DOCX must contain searchable text")

    duplicate_source = duplicate_root / f"duplicate{stored_documents[0].source_path.suffix.lower()}"
    shutil.copy2(stored_documents[0].source_path, duplicate_source)
    duplicate_record = import_document(vault_root, duplicate_source)
    if duplicate_record.status != DUPLICATE_STATUS:
        raise SmokeFailure("duplicate copy was not detected")
    if duplicate_record.quarantine_path.read_bytes() != duplicate_source.read_bytes():
        raise SmokeFailure("duplicate quarantine copy does not match source bytes")

    legacy_record = import_document(vault_root, legacy_doc_paths[0])
    if legacy_record.status != REJECTED_STATUS:
        raise SmokeFailure("legacy .doc file was not rejected")

    query = _query_from_text(searchable_documents[0].extracted_text)
    if not search_documents(vault_root, query, matter_id=matter.matter_id):
        raise SmokeFailure("local search did not return the ingested matter")

    indexed_count = build_rag_index(vault_root, matter_id=matter.matter_id)
    if indexed_count < 1:
        raise SmokeFailure("RAG index did not create any chunks")
    answer_packet = build_answer_packet(vault_root, query, matter_id=matter.matter_id)
    if not answer_packet.citations or not answer_packet.grounded_context:
        raise SmokeFailure("RAG answer packet did not include grounded citations")

    backup_package = create_local_backup(
        vault_root,
        backup_path,
        recovery_key=recovery_key,
        installation_id=installation_id,
    )
    backup_bytes = backup_path.read_bytes()
    for document in stored_documents:
        _assert_vault_copy_and_encryption(vault_session, document)
        if document.extracted_text:
            sample = document.extracted_text.encode("utf-8", errors="ignore")[:48]
            if sample and sample in backup_bytes:
                raise SmokeFailure("backup package exposed extracted document text")

    restore_report = restore_backup_package(
        backup_path,
        restore_root,
        recovery_key=recovery_key,
    )
    restored_session = open_vault(restore_report.restored_path, recovery_key)
    for document in stored_documents:
        if restored_session.read_object(document.object_id) != document.source_path.read_bytes():
            raise SmokeFailure("restored vault object did not match source bytes")

    return {
        "accepted_documents": len(stored_documents),
        "backup_package_bytes": backup_package.manifest.package_size_bytes,
        "duplicate_detected": True,
        "legacy_doc_rejected": True,
        "ocr_runtime_available": ocr_engine is not None,
        "rag_citations": len(answer_packet.citations),
        "restore_verified": restore_report.verified,
        "scanned_pdf_seen": scanned_pdf_seen,
        "searchable_documents": len(searchable_documents),
    }


def _ingest_store_and_index(
    vault_root: Path,
    vault_session,
    matter_id: str,
    source_path: Path,
    *,
    sequence: int,
    ocr_engine,
) -> StoredSmokeDocument:
    record = import_document(vault_root, source_path)
    if record.status != ACCEPTED_STATUS:
        raise SmokeFailure("selected private document was not accepted")
    if record.quarantine_path == source_path:
        raise SmokeFailure("intake reused the source path instead of copying to quarantine")
    if record.quarantine_path.read_bytes() != source_path.read_bytes():
        raise SmokeFailure("quarantine copy does not match source bytes")
    if not source_path.exists():
        raise SmokeFailure("intake moved the source file instead of copying it")

    extraction = extract_text(record.quarantine_path, ocr_engine=ocr_engine)
    if extraction.detected_file_type not in CONTENT_TYPES:
        raise SmokeFailure("accepted document could not be extracted as PDF or DOCX")
    if extraction.ocr_status not in {OCR_NOT_REQUIRED, OCR_PENDING, OCR_COMPLETED}:
        raise SmokeFailure("unexpected OCR status during manual smoke")

    stored_object = vault_session.write_object(
        record.quarantine_path.read_bytes(),
        original_name=f"private-smoke-document-{sequence}{source_path.suffix.lower()}",
        content_type=CONTENT_TYPES[extraction.detected_file_type],
        actor="manual-private-smoke",
    )
    document = create_document(
        vault_root,
        matter_id=matter_id,
        title=f"Private Smoke Document {sequence}",
        document_type=extraction.detected_file_type.upper(),
        lifecycle_status=DRAFT_STATUS,
    )
    add_document_version(
        vault_root,
        document_id=document.document_id,
        object_id=stored_object.object_id,
        source_sha256=stored_object.sha256,
        extracted_text=extraction.text,
        lifecycle_status=DRAFT_STATUS,
    )
    return StoredSmokeDocument(
        source_path=source_path,
        quarantine_path=record.quarantine_path,
        object_id=stored_object.object_id,
        extracted_text=extraction.text,
        detected_file_type=extraction.detected_file_type,
        ocr_status=extraction.ocr_status,
    )


def _assert_vault_copy_and_encryption(vault_session, document: StoredSmokeDocument) -> None:
    source_bytes = document.source_path.read_bytes()
    stored_object = vault_session.get_object(document.object_id)
    if vault_session.read_object(document.object_id) != source_bytes:
        raise SmokeFailure("vault readback did not match source bytes")
    if stored_object.object_path.read_bytes() == source_bytes:
        raise SmokeFailure("vault object was stored as plaintext")


def _query_from_text(text: str) -> str:
    tokens = []
    for token in re.findall(r"[A-Za-z0-9]{4,}", text):
        lowered = token.lower()
        if lowered not in tokens:
            tokens.append(lowered)
        if len(tokens) == 3:
            return " ".join(tokens)
    raise SmokeFailure("searchable document text did not contain enough query terms")


def _private_document_paths(input_root: Path) -> list[Path]:
    return sorted(
        path
        for path in input_root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES
    )


def _validate_input_root(input_root: Path) -> None:
    if not input_root.exists() or not input_root.is_dir():
        raise SmokeFailure("input path must be an existing folder")


if __name__ == "__main__":
    raise SystemExit(main())
