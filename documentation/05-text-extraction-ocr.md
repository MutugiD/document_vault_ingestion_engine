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

## F4 Implementation Boundary

The first extraction slice implements:

- PyMuPDF text extraction for searchable PDFs.
- python-docx text extraction for DOCX files.
- Page-count reporting for PDF and image paths.
- OCR adapter boundary for JPG/JPEG, PNG, and TIFF inputs.
- `pending_tesseract` OCR status for image files until the bundled Tesseract packaging slice.
- Warnings for empty extracted text and unsupported extraction inputs.

Bundled Tesseract binaries, scanned-PDF OCR fallback, OCR retry scheduling, and text handoff into search are delivered in later feature slices.

## Verification

`tests/validate_extraction.py` proves:

- Generated PDF text is extracted through PyMuPDF.
- Generated DOCX text is extracted through python-docx.
- Image files return a pending local OCR adapter status.
- Unsupported files return extraction warnings without crashing the intake pipeline.
