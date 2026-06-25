"""Local text extraction and OCR adapter boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz
from docx import Document

from intake.core import detect_file_type

OCR_NOT_REQUIRED = "not_required"
OCR_PENDING = "pending_tesseract"
OCR_FAILED = "failed"

IMAGE_TYPES = {"jpeg", "png", "tiff"}


class ExtractionError(Exception):
    """Base extraction failure."""


@dataclass(frozen=True)
class ExtractionResult:
    source_path: Path
    detected_file_type: str
    text: str
    page_count: int
    ocr_status: str
    warnings: tuple[str, ...]


def extract_text(source_path: Path) -> ExtractionResult:
    """Extract local text from supported files or report OCR status for images."""

    source_bytes = source_path.read_bytes()
    detected_file_type, warnings = detect_file_type(source_path, source_bytes)
    if detected_file_type == "pdf":
        return _extract_pdf(source_path, warnings)
    if detected_file_type == "docx":
        return _extract_docx(source_path, warnings)
    if detected_file_type in IMAGE_TYPES:
        return ExtractionResult(
            source_path=source_path,
            detected_file_type=detected_file_type,
            text="",
            page_count=1,
            ocr_status=OCR_PENDING,
            warnings=tuple(dict.fromkeys((*warnings, "ocr_adapter_pending"))),
        )
    return ExtractionResult(
        source_path=source_path,
        detected_file_type=detected_file_type,
        text="",
        page_count=0,
        ocr_status=OCR_FAILED,
        warnings=tuple(dict.fromkeys((*warnings, "unsupported_for_extraction"))),
    )


def _extract_pdf(source_path: Path, warnings: tuple[str, ...]) -> ExtractionResult:
    try:
        with fitz.open(source_path) as document:
            page_text = [page.get_text("text") for page in document]
            page_count = document.page_count
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


def _extract_docx(source_path: Path, warnings: tuple[str, ...]) -> ExtractionResult:
    try:
        document = Document(source_path)
    except Exception as exc:
        raise ExtractionError(f"DOCX extraction failed: {source_path}") from exc

    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs]
    text = "\n".join(paragraph for paragraph in paragraphs if paragraph)
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
    )
