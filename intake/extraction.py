"""Local text extraction and OCR adapter boundaries."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import fitz
from docx import Document

from intake.core import detect_file_type
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


@dataclass(frozen=True)
class ExtractionResult:
    source_path: Path
    detected_file_type: str
    text: str
    page_count: int
    ocr_status: str
    warnings: tuple[str, ...]


def extract_text(source_path: Path, *, ocr_engine: OcrEngine | None = None) -> ExtractionResult:
    """Extract local text from supported files or report OCR status for images."""

    source_bytes = source_path.read_bytes()
    detected_file_type, warnings = detect_file_type(source_path, source_bytes)
    if detected_file_type == "pdf":
        return _extract_pdf(source_path, warnings, ocr_engine=ocr_engine)
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
) -> ExtractionResult:
    try:
        with fitz.open(source_path) as document:
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
