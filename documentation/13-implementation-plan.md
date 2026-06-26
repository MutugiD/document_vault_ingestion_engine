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

## F9 - Windows Frozen Build

Status: Complete.

Build and validate the real PyInstaller one-folder Windows bundle.

Deliver:

- Real PyInstaller build through `main.spec`.
- Windows-friendly `strip=False` bundle settings.
- Frozen executable existence check.
- Frozen executable `--selftest` exit-code validation.
- CI step for `tests\validate_frozen_build.py`.

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
- `python tests\validate_frozen_build.py`
- `python main.py --selftest`
- `ruff check .`

## F10 - Local Matter RAG Connector

Status: Complete.

Publish the third solution and implement local, citation-first RAG retrieval over matter document versions.

Deliver:

- Three-product strategy documentation.
- `matter_rag` license entitlement.
- Local chunking from extracted document-version text.
- SQLite-backed RAG chunk store.
- Hybrid retrieval using sparse lexical and deterministic vector-style scoring.
- Reranking with lifecycle-aware boost.
- Matter-scoped retrieval.
- Citation-first answer packet for a later LLM generation boundary.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_license.py`
- `python tests\validate_vault.py`
- `python tests\validate_intake.py`
- `python tests\validate_extraction.py`
- `python tests\validate_search.py`
- `python tests\validate_rag.py`
- `python tests\validate_backup.py`
- `python tests\validate_cloud_boundary.py`
- `python tests\validate_ui.py`
- `python tests\validate_package.py`
- `python tests\validate_frozen_build.py`
- `python main.py --selftest`
- `ruff check .`

## F11 - End To End Verification

Status: Complete.

Validate the integrated licensed product flow across all three published products.

Deliver:

- End-to-end validator.
- Offline license validation with all paid feature flags.
- Intake to extraction to encrypted vault custody.
- Matter and document version creation.
- Search and Local Matter RAG citation packet.
- Encrypted backup, managed cloud boundary, restore drill.
- Restored vault object read verification.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_license.py`
- `python tests\validate_vault.py`
- `python tests\validate_intake.py`
- `python tests\validate_extraction.py`
- `python tests\validate_search.py`
- `python tests\validate_rag.py`
- `python tests\validate_backup.py`
- `python tests\validate_cloud_boundary.py`
- `python tests\validate_ui.py`
- `python tests\validate_package.py`
- `python tests\validate_e2e.py`
- `python tests\validate_frozen_build.py`
- `python main.py --selftest`
- `ruff check .`

## F12 - Three Product Catalog

Status: Complete.

Make the three published products explicit in code, documentation, release boundaries, and validation.

Deliver:

- `products/product_catalog.json`.
- Product catalog Python API.
- Product modules included in skeleton and frozen-build packaging.
- Product validators wired into CI.
- README and strategy documentation for the product catalog.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_products.py`
- `python tests\validate_license.py`
- `python tests\validate_vault.py`
- `python tests\validate_intake.py`
- `python tests\validate_extraction.py`
- `python tests\validate_search.py`
- `python tests\validate_rag.py`
- `python tests\validate_backup.py`
- `python tests\validate_cloud_boundary.py`
- `python tests\validate_ui.py`
- `python tests\validate_package.py`
- `python tests\validate_e2e.py`
- `python tests\validate_frozen_build.py`
- `python main.py --selftest`
- `ruff check .`

## F13 - Release Bundle

Status: Complete.

Create a checked Windows release ZIP from the frozen PyInstaller bundle.

Deliver:

- Release bundle Python module.
- `scripts/build_release_bundle.py` command.
- Sidecar release manifest with bundle SHA-256.
- Embedded release manifest in the ZIP.
- Product catalog metadata in the release manifest.
- File-level SHA-256 hashes for bundled artifacts.
- Guardrails against obvious secret, private-key, credential, `.env`, recovery-key, and client-document file names.
- CI step for `tests\validate_release_bundle.py`.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_products.py`
- `python tests\validate_license.py`
- `python tests\validate_vault.py`
- `python tests\validate_intake.py`
- `python tests\validate_extraction.py`
- `python tests\validate_search.py`
- `python tests\validate_rag.py`
- `python tests\validate_backup.py`
- `python tests\validate_cloud_boundary.py`
- `python tests\validate_ui.py`
- `python tests\validate_package.py`
- `python tests\validate_e2e.py`
- `python tests\validate_frozen_build.py`
- `python tests\validate_release_bundle.py`
- `python main.py --selftest`
- `ruff check .`

## F14 - Portable Install Smoke

Status: Complete.

Validate the release ZIP as a portable Windows install before installer wrapping begins.

Deliver:

- Portable install smoke Python module.
- `scripts/portable_install_smoke.py` command.
- Safe ZIP extraction with path traversal guard.
- Frozen executable `--selftest` from the extracted folder.
- Frozen executable `--products` from the extracted folder.
- Product catalog validation after extraction.
- CI step for `tests\validate_portable_install.py`.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_products.py`
- `python tests\validate_license.py`
- `python tests\validate_vault.py`
- `python tests\validate_intake.py`
- `python tests\validate_extraction.py`
- `python tests\validate_search.py`
- `python tests\validate_rag.py`
- `python tests\validate_backup.py`
- `python tests\validate_cloud_boundary.py`
- `python tests\validate_ui.py`
- `python tests\validate_package.py`
- `python tests\validate_e2e.py`
- `python tests\validate_frozen_build.py`
- `python tests\validate_release_bundle.py`
- `python tests\validate_portable_install.py`
- `python main.py --selftest`
- `ruff check .`

## F15 - OCR Runtime Bundle Contract

Status: Complete.

Lock the local Tesseract runtime packaging contract before committing a real OCR binary.

Deliver:

- OCR runtime manifest loader.
- Manifest creation helper.
- `tesseract.exe` and `tessdata/<language>.traineddata` required-file checks.
- SHA-256 and byte-size verification for every runtime file.
- Runtime path traversal guard.
- Tampered runtime manifest failure behavior.
- CI step for `tests\validate_ocr_runtime.py`.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_products.py`
- `python tests\validate_license.py`
- `python tests\validate_vault.py`
- `python tests\validate_intake.py`
- `python tests\validate_extraction.py`
- `python tests\validate_ocr_runtime.py`
- `python tests\validate_search.py`
- `python tests\validate_rag.py`
- `python tests\validate_backup.py`
- `python tests\validate_cloud_boundary.py`
- `python tests\validate_ui.py`
- `python tests\validate_package.py`
- `python tests\validate_e2e.py`
- `python tests\validate_frozen_build.py`
- `python tests\validate_release_bundle.py`
- `python tests\validate_portable_install.py`
- `python main.py --selftest`
- `ruff check .`
