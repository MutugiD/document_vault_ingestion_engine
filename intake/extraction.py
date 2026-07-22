"""Local text extraction and OCR adapter boundaries."""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import fitz
from docx import Document

from intake.core import detect_file_type
from intake.docling_runtime import (
    DoclingBlock,
    DoclingDocumentUnderstanding,
    DoclingRuntimeError,
    DoclingTable,
    DocumentUnderstanding,
)
from intake.ocr_runtime import OcrRuntimeError

OCR_NOT_REQUIRED = "not_required"
OCR_PENDING = "pending_tesseract"
OCR_COMPLETED = "completed_tesseract"
OCR_FAILED = "failed"

IMAGE_TYPES = {"jpeg", "png", "tiff"}


class ExtractionError(Exception):
    """Base extraction failure."""


class OcrEngine(Protocol):
    def recognize_image(
        self,
        image_path: Path,
        *,
        languages: tuple[str, ...] | None = None,
    ) -> str:
        """Return OCR text for an image path."""


class PasswordProvider(Protocol):
    """Provide an encrypted-document password without persisting it."""

    def get_password(self, source_path: Path) -> str | None:
        """Return a password held only in the caller's memory."""


@dataclass(frozen=True)
class ExtractionResult:
    source_path: Path
    detected_file_type: str
    text: str
    page_count: int
    ocr_status: str
    warnings: tuple[str, ...]
    blocks: tuple[DoclingBlock, ...] = ()
    tables: tuple[DoclingTable, ...] = ()
    extractor_version: str = "native"
    model_version: str = "not_loaded"
    source_sha256: str = ""
    pages: tuple[PageResult, ...] = ()
    status: str = "completed"
    retryable: bool = False
    started_at: str = ""
    completed_at: str = ""


@dataclass(frozen=True)
class PageResult:
    page_number: int
    text: str
    source: str
    requires_ocr: bool = False
    ocr_completed: bool = False
    confidence: float | None = None
    warnings: tuple[str, ...] = ()


def extract_document(
    source_path: Path,
    *,
    ocr_engine: OcrEngine | None = None,
    document_understanding: DocumentUnderstanding | None = None,
    password_provider: PasswordProvider | None = None,
) -> ExtractionResult:
    """Run native extraction followed by the mandatory Docling boundary."""

    started = datetime.now(UTC)
    native_result = extract_text(
        source_path,
        ocr_engine=ocr_engine,
        password_provider=password_provider,
    )
    if native_result.status in {"password_required", "invalid_password"}:
        return replace(
            native_result,
            source_sha256=_sha256_file(source_path),
            started_at=started.isoformat(),
            completed_at=datetime.now(UTC).isoformat(),
        )
    understanding = document_understanding or DoclingDocumentUnderstanding()
    try:
        converted = understanding.convert(source_path)
    except DoclingRuntimeError:
        raise
    completed = datetime.now(UTC)
    return replace(
        native_result,
        text=converted.text or native_result.text,
        page_count=max(native_result.page_count, converted.page_count),
        warnings=tuple(dict.fromkeys((*native_result.warnings, *converted.warnings))),
        blocks=converted.blocks,
        tables=converted.tables,
        extractor_version=converted.extractor_version,
        model_version=converted.model_version,
        source_sha256=_sha256_file(source_path),
        pages=tuple(
            PageResult(
                page_number=block.page_number or 1,
                text=block.text,
                source=block.provenance or "docling",
            )
            for block in converted.blocks
        ),
        status="completed_with_warnings" if converted.warnings else "completed",
        retryable=False,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
    )


def extract_text(
    source_path: Path,
    *,
    ocr_engine: OcrEngine | None = None,
    password_provider: PasswordProvider | None = None,
) -> ExtractionResult:
    """Extract local text from supported files or report OCR status for images."""

    source_bytes = source_path.read_bytes()
    detected_file_type, warnings = detect_file_type(source_path, source_bytes)
    if detected_file_type == "pdf":
        return _extract_pdf(
            source_path,
            warnings,
            ocr_engine=ocr_engine,
            password_provider=password_provider,
        )
    if detected_file_type == "docx":
        return _extract_docx(source_path, warnings)
    if detected_file_type in IMAGE_TYPES:
        return _extract_image(
            source_path,
            detected_file_type,
            warnings,
            ocr_engine=ocr_engine,
        )
    return ExtractionResult(
        source_path=source_path,
        detected_file_type=detected_file_type,
        text="",
        page_count=0,
        ocr_status=OCR_FAILED,
        warnings=tuple(dict.fromkeys((*warnings, "unsupported_for_extraction"))),
    )


def _extract_pdf(
    source_path: Path,
    warnings: tuple[str, ...],
    *,
    ocr_engine: OcrEngine | None,
    password_provider: PasswordProvider | None,
) -> ExtractionResult:
    try:
        with fitz.open(source_path) as document:
            if document.needs_pass:
                password = (
                    password_provider.get_password(source_path) if password_provider else None
                )
                if not password:
                    return ExtractionResult(
                        source_path=source_path,
                        detected_file_type="pdf",
                        text="",
                        page_count=document.page_count,
                        ocr_status=OCR_FAILED,
                        warnings=(*warnings, "password_required"),
                        status="password_required",
                        retryable=True,
                    )
                if not document.authenticate(password):
                    return ExtractionResult(
                        source_path=source_path,
                        detected_file_type="pdf",
                        text="",
                        page_count=document.page_count,
                        ocr_status=OCR_FAILED,
                        warnings=(*warnings, "invalid_password"),
                        status="invalid_password",
                        retryable=True,
                    )
            page_text = [page.get_text("text") for page in document]
            page_count = document.page_count
            if not any(part.strip() for part in page_text) and ocr_engine is not None:
                return _ocr_pdf_pages(source_path, document, warnings, ocr_engine=ocr_engine)
    except Exception as exc:
        raise ExtractionError(f"PDF extraction failed: {source_path}") from exc

    text = "\n".join(part.strip() for part in page_text if part.strip())
    result_warnings = list(warnings)
    if not text:
        result_warnings.append("empty_extracted_text")
    return ExtractionResult(
        source_path=source_path,
        detected_file_type="pdf",
        text=text,
        page_count=page_count,
        ocr_status=OCR_NOT_REQUIRED if text else OCR_PENDING,
        warnings=tuple(dict.fromkeys(result_warnings)),
    )


def _extract_image(
    source_path: Path,
    detected_file_type: str,
    warnings: tuple[str, ...],
    *,
    ocr_engine: OcrEngine | None,
) -> ExtractionResult:
    if ocr_engine is None:
        return ExtractionResult(
            source_path=source_path,
            detected_file_type=detected_file_type,
            text="",
            page_count=1,
            ocr_status=OCR_PENDING,
            warnings=tuple(dict.fromkeys((*warnings, "ocr_adapter_pending"))),
        )
    try:
        text = ocr_engine.recognize_image(source_path)
    except OcrRuntimeError:
        return ExtractionResult(
            source_path=source_path,
            detected_file_type=detected_file_type,
            text="",
            page_count=1,
            ocr_status=OCR_FAILED,
            warnings=tuple(dict.fromkeys((*warnings, "ocr_failed"))),
        )
    return ExtractionResult(
        source_path=source_path,
        detected_file_type=detected_file_type,
        text=text,
        page_count=1,
        ocr_status=OCR_COMPLETED if text else OCR_PENDING,
        warnings=_ocr_warnings(warnings, text),
    )


def _ocr_pdf_pages(
    source_path: Path,
    document: fitz.Document,
    warnings: tuple[str, ...],
    *,
    ocr_engine: OcrEngine,
) -> ExtractionResult:
    page_text: list[str] = []
    with tempfile.TemporaryDirectory() as temporary_dir:
        workspace = Path(temporary_dir)
        for page_number, page in enumerate(document, start=1):
            image_path = workspace / f"page-{page_number}.png"
            page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(image_path)
            try:
                page_text.append(ocr_engine.recognize_image(image_path))
            except OcrRuntimeError:
                return ExtractionResult(
                    source_path=source_path,
                    detected_file_type="pdf",
                    text="",
                    page_count=document.page_count,
                    ocr_status=OCR_FAILED,
                    warnings=tuple(
                        dict.fromkeys((*warnings, "empty_extracted_text", "ocr_failed"))
                    ),
                )

    text = "\n".join(part.strip() for part in page_text if part.strip())
    return ExtractionResult(
        source_path=source_path,
        detected_file_type="pdf",
        text=text,
        page_count=document.page_count,
        ocr_status=OCR_COMPLETED if text else OCR_PENDING,
        warnings=_ocr_warnings((*warnings, "empty_extracted_text"), text),
    )


def _ocr_warnings(warnings: tuple[str, ...], text: str) -> tuple[str, ...]:
    result = list(warnings)
    if text:
        result.append("ocr_text_extracted")
        if len(text.split()) < 3:
            result.append("low_ocr_text_confidence")
    else:
        result.append("empty_ocr_text")
    return tuple(dict.fromkeys(result))


def _extract_docx(source_path: Path, warnings: tuple[str, ...]) -> ExtractionResult:
    try:
        document = Document(source_path)
    except Exception as exc:
        raise ExtractionError(f"DOCX extraction failed: {source_path}") from exc

    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs]
    table_rows = [
        " | ".join(cell.text.strip() for cell in row.cells)
        for table in document.tables
        for row in table.rows
    ]
    text = "\n".join(part for part in (*paragraphs, *table_rows) if part)
    result_warnings = list(warnings)
    if not text:
        result_warnings.append("empty_extracted_text")
    return ExtractionResult(
        source_path=source_path,
        detected_file_type="docx",
        text=text,
        page_count=1,
        ocr_status=OCR_NOT_REQUIRED,
        warnings=tuple(dict.fromkeys(result_warnings)),
        source_sha256=_sha256_file(source_path),
        pages=(PageResult(1, text, "docx"),),
    )


def _sha256_file(source_path: Path) -> str:
    digest = hashlib.sha256()
    with source_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
