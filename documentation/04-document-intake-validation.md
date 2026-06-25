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

## Verification

`tests/validate_intake.py` will cover valid inputs, corrupt inputs, unsupported inputs, and duplicates.
