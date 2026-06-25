# 04 - Document Intake Validation

## Purpose

Safely move files from scanner/manual sources into a validated quarantine workflow.

## Supported Inputs

- PDF
- DOCX
- JPG/JPEG
- PNG
- TIFF

## Flow

1. Copy source to quarantine.
2. Calculate SHA-256.
3. Detect file signature.
4. Reject unsupported/corrupt files.
5. Detect duplicates.
6. Emit intake record.

## Quality Warnings

- unsupported type
- extension/signature mismatch
- corrupt file
- password-protected PDF
- empty document
- duplicate source hash
- large file warning

## F3 Implementation Boundary

The first intake slice implements:

- Manual source-file import into the vault quarantine folder.
- SHA-256 source hash calculation.
- Signature-based detection for PDF, DOCX, JPG/JPEG, PNG, and TIFF.
- Extension/signature mismatch warning.
- Duplicate detection against prior accepted intake records.
- Rejected records for unsupported, corrupt, and empty files.
- SQLite `intake_records` persistence.

Text extraction, OCR, quality scoring, vault handoff, and matter assignment are delivered in later feature slices.

## Verification

`tests/validate_intake.py` proves:

- Valid PDF, DOCX, and PNG inputs are accepted.
- Duplicate PDF input is marked duplicate.
- Signature/extension mismatch is warned but still accepted when the signature is supported.
- Unsupported text files are rejected.
- Corrupt DOCX-like ZIP input is rejected with `corrupt_file`.
- Empty files are rejected with `empty_document`.
- Intake records are persisted and listable from SQLite.
