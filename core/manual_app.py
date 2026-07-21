"""Manual app session used by the desktop UI and Windows E2E evidence runs."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from backup import InvalidBackupKeyError, create_local_backup, restore_backup_package
from intake import (
    ACCEPTED_STATUS,
    DUPLICATE_STATUS,
    REJECTED_STATUS,
    DoclingRuntimeError,
    ExtractionError,
    extract_document,
    import_document,
)
from intake.docling_runtime import DocumentUnderstanding
from rag import build_answer_packet, build_rag_index
from search import (
    FILED_STATUS,
    add_document_version,
    create_document,
    create_matter,
    search_documents,
)
from vault import initialize_vault, open_vault


class ManualAppSessionError(Exception):
    """Raised when the manual app workflow cannot continue."""


@dataclass(frozen=True)
class ManualImportResult:
    source_name: str
    detected_file_type: str
    status: str
    warnings: tuple[str, ...]
    extraction_status: str
    page_count: int
    text_available: bool
    vault_object_created: bool
    source_copy_preserved: bool
    elapsed_ms: int

    def summary(self) -> str:
        warnings = ",".join(self.warnings) if self.warnings else "none"
        text_state = "text" if self.text_available else "no-text"
        vault_state = "vaulted" if self.vault_object_created else "not-vaulted"
        return (
            f"{self.source_name}: {self.status} {self.detected_file_type} "
            f"{self.extraction_status} {text_state} {vault_state} warnings={warnings}"
        )


@dataclass(frozen=True)
class ManualRagResult:
    question: str
    confidence: float
    citation_count: int
    citation_titles: tuple[str, ...]
    elapsed_ms: int

    def summary(self) -> str:
        titles = "; ".join(self.citation_titles) if self.citation_titles else "none"
        return (
            f"confidence={self.confidence} citations={self.citation_count} "
            f"elapsed_ms={self.elapsed_ms} titles={titles}"
        )


@dataclass(frozen=True)
class ManualBackupResult:
    backup_path: Path
    package_size_bytes: int
    restore_verified: bool
    wrong_key_failed: bool
    elapsed_ms: int

    def summary(self) -> str:
        return (
            f"backup={self.backup_path.name} bytes={self.package_size_bytes} "
            f"restore_verified={self.restore_verified} wrong_key_failed={self.wrong_key_failed}"
        )


class ManualAppSession:
    """Stateful local session that mirrors user-driven desktop actions."""

    def __init__(
        self,
        workspace: Path,
        *,
        vault_passphrase: str = "manual app session passphrase",
        document_understanding: DocumentUnderstanding | None = None,
    ) -> None:
        self.workspace = workspace
        self.vault_root = workspace / "vault"
        self.backup_path = workspace / "backups" / "manual-session.wakilibak"
        self.restore_root = workspace / "restore"
        self.vault_passphrase = vault_passphrase
        self.document_understanding = document_understanding
        self.installation_id = f"manual-session-{uuid4()}"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.vault_session = initialize_vault(self.vault_root, self.vault_passphrase)
        self.matter = create_matter(
            self.vault_root,
            internal_reference="MANUAL-E2E-001",
            client_name="Public Sample Legal Materials",
            parties="Public sample corpus verification",
            court="Kenyan courts",
            station="Nairobi",
            case_number="MANUAL-E2E-001",
            practice_area="Mixed public law and procedure",
            responsible_advocate="Manual verifier",
        )
        self.import_results: list[ManualImportResult] = []
        self.rag_results: list[ManualRagResult] = []
        self.stored_object_ids: list[str] = []

    def import_file(self, source_path: Path) -> ManualImportResult:
        start = time.perf_counter()
        record = import_document(self.vault_root, source_path)
        source_copy_preserved = source_path.exists()
        extraction_status = "not_run"
        page_count = 0
        text_available = False
        vault_object_created = False

        if record.status == ACCEPTED_STATUS:
            try:
                extraction = extract_document(
                    record.quarantine_path,
                    ocr_engine=_sidecar_ocr_engine(source_path),
                    document_understanding=self.document_understanding,
                )
                extraction_status = extraction.ocr_status
                page_count = extraction.page_count
                extracted_text = extraction.text
                text_available = bool(extracted_text.strip())
                warnings = record.warnings
            except (ExtractionError, DoclingRuntimeError) as exc:
                extraction_status = _runtime_failure_status(exc)
                page_count = 0
                extracted_text = ""
                text_available = False
                warnings = tuple(dict.fromkeys((*record.warnings, "extraction_failed")))
            stored_object = self.vault_session.write_object(
                record.quarantine_path.read_bytes(),
                original_name=source_path.name,
                content_type=_content_type(record.detected_file_type),
                actor="manual-app-session",
            )
            self.stored_object_ids.append(stored_object.object_id)
            vault_object_created = True
            structured_object_id = None
            if text_available:
                structured_payload = json.dumps(
                    _structured_payload(extraction),
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
                structured_object = self.vault_session.write_object(
                    structured_payload,
                    original_name=f"{source_path.name}.extraction.json",
                    content_type="application/json",
                    actor="manual-app-session",
                )
                structured_object_id = structured_object.object_id
            document = create_document(
                self.vault_root,
                matter_id=self.matter.matter_id,
                title=_display_title(source_path),
                document_type=record.detected_file_type.upper(),
                lifecycle_status=FILED_STATUS,
            )
            add_document_version(
                self.vault_root,
                document_id=document.document_id,
                object_id=stored_object.object_id,
                source_sha256=stored_object.sha256,
                extracted_text=extracted_text,
                structured_object_id=structured_object_id,
                lifecycle_status=FILED_STATUS,
            )
            build_rag_index(self.vault_root, matter_id=self.matter.matter_id)
        elif record.status in {DUPLICATE_STATUS, REJECTED_STATUS}:
            extraction_status = "skipped"
            warnings = record.warnings
        else:
            warnings = record.warnings

        result = ManualImportResult(
            source_name=source_path.name,
            detected_file_type=record.detected_file_type,
            status=record.status,
            warnings=warnings,
            extraction_status=extraction_status,
            page_count=page_count,
            text_available=text_available,
            vault_object_created=vault_object_created,
            source_copy_preserved=source_copy_preserved,
            elapsed_ms=_elapsed_ms(start),
        )
        self.import_results.append(result)
        return result

    def search(self, query: str) -> int:
        return len(search_documents(self.vault_root, query, matter_id=self.matter.matter_id))

    def ask(self, question: str) -> ManualRagResult:
        start = time.perf_counter()
        build_rag_index(self.vault_root, matter_id=self.matter.matter_id)
        packet = build_answer_packet(
            self.vault_root,
            question,
            matter_id=self.matter.matter_id,
            top_k=5,
        )
        result = ManualRagResult(
            question=question,
            confidence=packet.confidence,
            citation_count=len(packet.citations),
            citation_titles=tuple(citation.title for citation in packet.citations),
            elapsed_ms=_elapsed_ms(start),
        )
        self.rag_results.append(result)
        return result

    def backup_and_restore(self) -> ManualBackupResult:
        start = time.perf_counter()
        backup = create_local_backup(
            self.vault_root,
            self.backup_path,
            recovery_key=self.vault_passphrase,
            installation_id=self.installation_id,
        )
        restore_report = restore_backup_package(
            self.backup_path,
            self.restore_root,
            recovery_key=self.vault_passphrase,
        )
        restored_session = open_vault(restore_report.restored_path, self.vault_passphrase)
        restore_verified = True
        for object_id in self.stored_object_ids[:5]:
            if not restored_session.read_object(object_id):
                restore_verified = False
                break
        wrong_key_failed = False
        try:
            intentionally_wrong_passphrase = "intentionally wrong manual passphrase"
            restore_backup_package(
                self.backup_path,
                self.workspace / "wrong-key-restore",
                recovery_key=intentionally_wrong_passphrase,
            )
        except InvalidBackupKeyError:
            wrong_key_failed = True
        return ManualBackupResult(
            backup_path=self.backup_path,
            package_size_bytes=backup.manifest.package_size_bytes,
            restore_verified=restore_verified and restore_report.verified,
            wrong_key_failed=wrong_key_failed,
            elapsed_ms=_elapsed_ms(start),
        )


class SidecarOcrEngine:
    def __init__(self, text: str) -> None:
        self.text = text

    def recognize_image(
        self,
        image_path: Path,
        *,
        languages: tuple[str, ...] | None = None,
    ) -> str:
        del image_path, languages
        return self.text


def _sidecar_ocr_engine(source_path: Path) -> SidecarOcrEngine | None:
    sidecar = source_path.with_suffix(source_path.suffix + ".ocr.txt")
    if not sidecar.exists():
        return None
    return SidecarOcrEngine(sidecar.read_text(encoding="utf-8"))


def _content_type(detected_file_type: str) -> str:
    return {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "png": "image/png",
        "jpeg": "image/jpeg",
        "tiff": "image/tiff",
    }[detected_file_type]


def _display_title(source_path: Path) -> str:
    words = [word for word in source_path.stem.replace("_", "-").split("-") if word]
    return " ".join(word.capitalize() for word in words[:10]) or "Imported Document"


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _structured_payload(extraction: object) -> dict[str, object]:
    payload = asdict(extraction)
    payload["source_path"] = str(payload["source_path"])
    return payload


def _runtime_failure_status(error: Exception) -> str:
    message = str(error).lower()
    if "docling" in message or "model" in message:
        return "model_runtime_unavailable"
    if "ocr" in message or "tesseract" in message:
        return "ocr_runtime_unavailable"
    return "extraction_failed"
