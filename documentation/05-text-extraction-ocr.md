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

## F15 Implementation Boundary

The OCR runtime packaging-readiness slice implements:

- Tesseract runtime manifest loader.
- Manifest creation helper for a prepared local Tesseract folder.
- Required `tesseract.exe` and `tessdata/<language>.traineddata` checks.
- SHA-256 and byte-size verification for every OCR runtime file.
- Windows platform guard through `windows-x64`.
- Path traversal guard for runtime file paths.
- Tampered runtime manifest failure behavior.

This slice does not commit a real Tesseract binary. It locks the contract for bundling a vetted binary later.

## Verification

`tests/validate_extraction.py` proves:

- Generated PDF text is extracted through PyMuPDF.
- Generated DOCX text is extracted through python-docx.
- Image files return a pending local OCR adapter status.
- Unsupported files return extraction warnings without crashing the intake pipeline.

`tests/validate_ocr_runtime.py` proves:

- A prepared Tesseract runtime folder can produce and validate a manifest.
- Tampered runtime file hashes fail validation.
- Runtime paths cannot escape the bundle root.
