"""Run an end-to-end vault and RAG test against public Kenyan legal documents."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backup import create_local_backup, restore_backup_package  # noqa: E402
from intake import ACCEPTED_STATUS, extract_text, import_document  # noqa: E402
from rag import build_answer_packet, build_rag_index  # noqa: E402
from search import FILED_STATUS, add_document_version, create_document, create_matter  # noqa: E402
from vault import initialize_vault, open_vault  # noqa: E402

QUESTIONS = (
    "What material mentions the Supreme Court Act or Supreme Court rules?",
    "What does the public Kenyan court material say about an application or petition?",
    "What document discusses land, commission, registry, or court procedure?",
    "Which cited source discusses a stay application or court filing procedure?",
    "What local context is available about appeals, registry, notices, or forms?",
)

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class PublicKenyanE2EError(Exception):
    """Raised when the public Kenyan document verification cannot complete."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run public Kenyan legal-document E2E.")
    parser.add_argument("--input", required=True, type=Path, help="Folder containing public docs.")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Optional scratch workspace. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional JSON report path.",
    )
    args = parser.parse_args(argv)

    try:
        if args.workspace is None:
            with tempfile.TemporaryDirectory(prefix="dv-public-ke-e2e-") as temporary_dir:
                report = run_public_kenyan_e2e(args.input.resolve(), Path(temporary_dir))
        else:
            args.workspace.mkdir(parents=True, exist_ok=True)
            report = run_public_kenyan_e2e(args.input.resolve(), args.workspace.resolve())
        payload = json.dumps(report, indent=2, sort_keys=True)
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(payload + "\n", encoding="utf-8")
        print("PUBLIC KENYAN E2E PASS")
        print(payload)
        return 0
    except PublicKenyanE2EError as exc:
        print("PUBLIC KENYAN E2E FAIL")
        print(str(exc))
        return 1


def run_public_kenyan_e2e(input_root: Path, workspace: Path) -> dict[str, object]:
    source_paths = _source_paths(input_root)
    if len(source_paths) < 3:
        raise PublicKenyanE2EError("at least three public PDF/DOCX documents are required")

    recovery_key = f"public-kenya-e2e-{uuid4()}"
    installation_id = f"public-kenya-install-{uuid4()}"
    vault_root = workspace / "vault"
    backup_path = workspace / "backup" / "public-kenya.wakilibak"
    restore_root = workspace / "restore"

    vault_session = initialize_vault(vault_root, recovery_key)
    matter = create_matter(
        vault_root,
        internal_reference="PUBLIC-KE-001",
        client_name="Public Kenyan Legal Materials",
        parties="Public legal materials verification",
        court="Kenyan Judiciary public sources",
        station="Kenya",
        case_number="PUBLIC-KE-001",
        practice_area="Public law and procedure",
        responsible_advocate="Local verifier",
    )

    stored_objects: list[tuple[str, Path]] = []
    indexed_documents = 0
    for index, source_path in enumerate(source_paths, start=1):
        record = import_document(vault_root, source_path)
        if record.status != ACCEPTED_STATUS:
            continue
        extraction = extract_text(record.quarantine_path)
        if not extraction.text:
            continue
        stored_object = vault_session.write_object(
            record.quarantine_path.read_bytes(),
            original_name=f"public-kenyan-document-{index}{source_path.suffix.lower()}",
            content_type=CONTENT_TYPES[extraction.detected_file_type],
            actor="public-kenyan-e2e",
        )
        document = create_document(
            vault_root,
            matter_id=matter.matter_id,
            title=_display_title(source_path, index),
            document_type=extraction.detected_file_type.upper(),
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
        stored_objects.append((stored_object.object_id, source_path))
        indexed_documents += 1

    if indexed_documents < 3:
        raise PublicKenyanE2EError("fewer than three documents produced searchable text")

    chunk_count = build_rag_index(vault_root, matter_id=matter.matter_id)
    if chunk_count < indexed_documents:
        raise PublicKenyanE2EError("RAG chunk count is lower than indexed document count")

    answers = []
    for question in QUESTIONS:
        packet = build_answer_packet(vault_root, question, matter_id=matter.matter_id, top_k=4)
        if not packet.citations:
            raise PublicKenyanE2EError(f"no citations returned for question: {question}")
        answers.append(
            {
                "question": question,
                "confidence": packet.confidence,
                "citation_count": len(packet.citations),
                "citations": [
                    {
                        "citation_id": result.citation.citation_id,
                        "title": result.citation.title,
                        "chunk_index": result.citation.chunk_index,
                        "confidence": result.confidence,
                    }
                    for result in packet.retrieval_results
                ],
                "answer": _extractive_answer(packet.grounded_context),
            }
        )

    backup = create_local_backup(
        vault_root,
        backup_path,
        recovery_key=recovery_key,
        installation_id=installation_id,
    )
    restore_report = restore_backup_package(
        backup_path,
        restore_root,
        recovery_key=recovery_key,
    )
    restored_session = open_vault(restore_report.restored_path, recovery_key)
    for object_id, source_path in stored_objects:
        if restored_session.read_object(object_id) != source_path.read_bytes():
            raise PublicKenyanE2EError("restored public document bytes did not match source")

    return {
        "input_documents": len(source_paths),
        "indexed_documents": indexed_documents,
        "rag_chunks": chunk_count,
        "answers": answers,
        "backup_package_bytes": backup.manifest.package_size_bytes,
        "restore_verified": restore_report.verified,
    }


def _extractive_answer(grounded_context: str) -> str:
    words = grounded_context.replace("\n", " ").split()
    return " ".join(words[:36])


def _source_paths(input_root: Path) -> list[Path]:
    if not input_root.exists() or not input_root.is_dir():
        raise PublicKenyanE2EError("input path must be an existing folder")
    return sorted(
        path
        for path in input_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".pdf", ".docx"}
    )


def _display_title(source_path: Path, index: int) -> str:
    stem = source_path.stem.replace("_", "-")
    words = [word for word in stem.split("-") if word]
    if not words:
        return f"Public Kenyan Legal Document {index}"
    return " ".join(word.capitalize() for word in words[:12])


if __name__ == "__main__":
    raise SystemExit(main())
