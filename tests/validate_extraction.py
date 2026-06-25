"""Validate F4 text extraction and OCR adapter behavior."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import fitz
from docx import Document

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intake import OCR_NOT_REQUIRED, OCR_PENDING, extract_text  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        workspace = Path(temporary_dir)

        pdf_path = workspace / "hearing-notice.pdf"
        _write_pdf(pdf_path, "Hearing notice for Nairobi matter 001")
        pdf_result = extract_text(pdf_path)
        assert pdf_result.detected_file_type == "pdf"
        assert pdf_result.page_count == 1
        assert pdf_result.ocr_status == OCR_NOT_REQUIRED
        assert "Nairobi matter 001" in pdf_result.text

        docx_path = workspace / "draft-pleading.docx"
        _write_docx(docx_path, "Draft pleading for commercial division")
        docx_result = extract_text(docx_path)
        assert docx_result.detected_file_type == "docx"
        assert docx_result.ocr_status == OCR_NOT_REQUIRED
        assert "commercial division" in docx_result.text

        image_path = workspace / "scan.png"
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"scanned image bytes")
        image_result = extract_text(image_path)
        assert image_result.detected_file_type == "png"
        assert image_result.text == ""
        assert image_result.page_count == 1
        assert image_result.ocr_status == OCR_PENDING
        assert "ocr_adapter_pending" in image_result.warnings

        unsupported_path = workspace / "notes.txt"
        unsupported_path.write_text("not supported for extraction", encoding="utf-8")
        unsupported_result = extract_text(unsupported_path)
        assert unsupported_result.detected_file_type == "unsupported"
        assert unsupported_result.page_count == 0
        assert "unsupported_for_extraction" in unsupported_result.warnings

    print("EXTRACTION VALIDATION PASS")


def _write_pdf(path: Path, text: str) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def _write_docx(path: Path, text: str) -> None:
    document = Document()
    document.add_paragraph(text)
    document.save(path)


if __name__ == "__main__":
    main()
