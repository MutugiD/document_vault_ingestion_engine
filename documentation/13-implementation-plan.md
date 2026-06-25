# 13 - Implementation Plan

## F0 - Documentation And Skeleton

Status: Active.

Deliver:

- Documentation pack.
- Python package skeleton.
- `main.py --selftest`.
- Validation scripts.
- PyInstaller spec placeholder.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python main.py --selftest`

## F1 - Licensing

Build signed offline license validation, installation ID, expiry checks, and feature flags.

## F2 - Vault

Build SQLite metadata, encrypted object write/read, recovery-key flow, and audit ledger.

## F3 - Intake

Build quarantine, file signature validation, SHA-256 duplicate detection, and intake records.

## F4 - Extraction And OCR

Build PDF extraction, DOCX extraction, and local Tesseract OCR adapter.

## F5 - Matter Version Search

Build matter records, document versions, lifecycle status, and SQLite FTS5 search.

## F6 - Backup Restore

Build encrypted local backup packages, manifests, and restore drills.

## F7 - Managed Cloud Boundary

Build short-lived provider grant client and metadata allowlist tests.

## F8 - UI And Package

Build PySide6 UI shell, worker threading, `main.spec`, and frozen selftest.
