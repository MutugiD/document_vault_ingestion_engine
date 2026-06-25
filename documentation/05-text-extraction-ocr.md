# 05 - Text Extraction And OCR

## Purpose

Extract searchable text locally while preserving the original encrypted document.

## Extractors

- PyMuPDF for PDF text and page metadata.
- python-docx for DOCX text.
- Tesseract for scanned PDFs and images.

## Rules

- OCR runs locally.
- OCR failure does not block storing the original document.
- OCR state is retryable.
- Extracted text is local-only.

## Verification

`tests/validate_extraction.py` will prove PDF, DOCX, and scanned-image extraction paths.
