# 13 - Implementation Plan

## F0 - Documentation And Skeleton

Status: Complete.

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

Status: Complete.

Build signed offline license validation, installation ID, expiry checks, and feature flags.

Deliver:

- Stable installation ID generation and persistence.
- Offline JSON license model.
- RSA-PSS/SHA-256 signature validation.
- Expiry, disabled, tampered, and installation mismatch decisions.
- Feature entitlement checks for paid modules.
- Packaged-app selftest coverage for installation identity persistence.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_license.py`
- `python main.py --selftest`
- `ruff check .`

## F2 - Vault

Status: Complete.

Build SQLite metadata, encrypted object write/read, recovery-key flow, and audit ledger.

Deliver:

- Vault folder initialization.
- SQLite metadata creation.
- Audit event table.
- PBKDF2-HMAC-SHA256 recovery-key verification.
- AES-GCM encrypted object write/read.
- Wrong-key failure behavior.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_license.py`
- `python tests\validate_vault.py`
- `python main.py --selftest`
- `ruff check .`

## F3 - Intake

Status: Complete.

Build quarantine, file signature validation, SHA-256 duplicate detection, and intake records.

Deliver:

- Quarantine workspace.
- Source file hash.
- Signature detection.
- Duplicate detection.
- PDF, DOCX, and image intake records.
- Rejected records for unsupported, corrupt, and empty files.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_license.py`
- `python tests\validate_vault.py`
- `python tests\validate_intake.py`
- `python main.py --selftest`
- `ruff check .`

## F4 - Extraction And OCR

Status: Complete.

Build PDF extraction, DOCX extraction, and local Tesseract OCR adapter.

Deliver:

- PyMuPDF PDF extraction.
- python-docx extraction.
- OCR adapter boundary.
- OCR status and warnings.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_license.py`
- `python tests\validate_vault.py`
- `python tests\validate_intake.py`
- `python tests\validate_extraction.py`
- `python main.py --selftest`
- `ruff check .`

## F5 - Matter Version Search

Status: Complete.

Build matter records, document versions, lifecycle status, and SQLite FTS5 search.

Deliver:

- Matter records.
- Document records.
- Immutable document version records.
- Lifecycle status on documents and versions.
- SQLite FTS5 indexing.
- Matter-scoped search.
- Search index rebuild.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_license.py`
- `python tests\validate_vault.py`
- `python tests\validate_intake.py`
- `python tests\validate_extraction.py`
- `python tests\validate_search.py`
- `python main.py --selftest`
- `ruff check .`

## F6 - Backup Restore

Status: Complete.

Build encrypted local backup packages, manifests, and restore drills.

Deliver:

- Encrypted local backup package.
- Manifest.
- Hash verification.
- Restore drill workspace.
- Wrong-key behavior.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_license.py`
- `python tests\validate_vault.py`
- `python tests\validate_intake.py`
- `python tests\validate_extraction.py`
- `python tests\validate_search.py`
- `python tests\validate_backup.py`
- `python main.py --selftest`
- `ruff check .`

## F7 - Managed Cloud Boundary

Status: Complete.

Build short-lived provider grant client and metadata allowlist tests.

Deliver:

- Provider-neutral grant interface.
- Metadata allowlist.
- No long-lived cloud credential acceptance.
- Encrypted-package-only upload boundary.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_license.py`
- `python tests\validate_vault.py`
- `python tests\validate_intake.py`
- `python tests\validate_extraction.py`
- `python tests\validate_search.py`
- `python tests\validate_backup.py`
- `python tests\validate_cloud_boundary.py`
- `python main.py --selftest`
- `ruff check .`

## F8 - UI And Package

Status: Complete.

Build PySide6 UI shell, worker threading, `main.spec`, and frozen selftest.

Deliver:

- PySide6 shell.
- Worker thread pattern.
- Package selftest.
- PyInstaller configuration validation.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_license.py`
- `python tests\validate_vault.py`
- `python tests\validate_intake.py`
- `python tests\validate_extraction.py`
- `python tests\validate_search.py`
- `python tests\validate_backup.py`
- `python tests\validate_cloud_boundary.py`
- `python tests\validate_ui.py`
- `python tests\validate_package.py`
- `python main.py --selftest`
- `ruff check .`
