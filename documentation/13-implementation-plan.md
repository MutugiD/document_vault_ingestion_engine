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

## F16 - Security Scan

Status: Complete.

Add a local deterministic security scan for source and release hygiene.

Deliver:

- Repository scanner for tracked text files.
- Release ZIP filename scanner.
- Private-key block detection.
- AWS access-key shape detection.
- Azure connection-string shape detection.
- Google private-key JSON shape detection.
- Recovery-key assignment shape detection.
- CI step for `tests\validate_security_scan.py`.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_products.py`
- `python tests\validate_security_scan.py`
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

## F17 - Real-World RAG End To End

Status: Complete.

Validate a realistic legal-document workflow with old PDF, DOCX pleading, scanned PDF, many grounded questions, copies, local vault saving, backup, cloud metadata, and restore.

Deliver:

- Old archived PDF fixture generation.
- DOCX pleading fixture generation.
- Image-only scanned PDF fixture generation.
- Legacy `.doc` unsupported-file check.
- Duplicate copy detection.
- Quarantine copy preservation checks.
- Encrypted vault object checks.
- Matter, document, and version records for accepted files.
- Matter-scoped RAG index and forty grounded RAG questions.
- OCR-pending scanned PDF exclusion from RAG chunks.
- Encrypted backup plaintext-leak checks.
- Managed cloud metadata allowlist check.
- Restore drill that reads original bytes for PDF, DOCX, and scanned PDF.
- CI step for `tests\validate_real_world_rag_e2e.py`.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `python tests\validate_products.py`
- `python tests\validate_security_scan.py`
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
- `python tests\validate_real_world_rag_e2e.py`
- `python tests\validate_frozen_build.py`
- `python tests\validate_release_bundle.py`
- `python tests\validate_portable_install.py`
- `python main.py --selftest`
- `ruff check .`

## F18 - End To End Testing Guide

Status: Complete.

Add a Windows guide for developer, release, real-world RAG, frozen build, release ZIP, portable install, and clean-machine testing.

Deliver:

- `documentation/16-end-to-end-testing-guide.md`.
- Root README link.
- Documentation README link.
- Docs validator enforcement.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_skeleton.py`
- `ruff check .`

## F19 - Product Documentation Pack

Status: Complete.

Add product-specific architecture, feature breakdown, gap analysis, and implementation docs for all three products.

Deliver:

- `documentation/products/README.md`.
- Windows Legal Document Vault product docs.
- Document Intake Engine product docs.
- Local Matter RAG Connector product docs.
- Product catalog documentation links.
- Docs validator enforcement.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_products.py`
- `ruff check .`

## F20 - OCR Execution And Tesseract Bundling

Status: Complete.

Complete OCR beyond the current runtime manifest contract.

Deliver:

- Tesseract runtime discovery.
- Tesseract execution adapter.
- Image OCR for PNG/JPEG/TIFF.
- Scanned/image-only PDF OCR fallback.
- OCR quality warnings.
- Local-only OCR text storage.
- PyInstaller inclusion rules for Tesseract files.
- Release validation that OCR runtime files are present when enabled.

Definition of done:

- `python tests\validate_extraction.py`
- `python tests\validate_ocr_runtime.py`
- `python tests\validate_real_world_rag_e2e.py`
- `python tests\validate_frozen_build.py`
- `python tests\validate_release_bundle.py`

## F21 - Manual Private Document Test Runner

Status: Complete.

Add a local-only test runner for private documents outside the repo.

Deliver:

- `scripts/manual_ingest_smoke.py`.
- Input folder argument.
- PDF, DOCX, scanned PDF, duplicate, unsupported `.doc`, intake, vault, search, RAG, backup, restore checks.
- Redacted console output.
- No raw document text in logs.

Definition of done:

- `python tests\validate_manual_ingest_smoke.py`
- `python tests\validate_security_scan.py`
- `python tests\validate_real_world_rag_e2e.py`

## F22 - Admin And License Sync Backend Boundary

Status: Complete.

Implement commercial licensing/admin sync boundary.

Deliver:

- installation check-in payload.
- license status sync.
- enabled/disabled feature flags.
- paid entitlement state.
- coarse backup health.
- privacy validator proving no matter/client/file/OCR/hash/recovery-key fields.
- local grace behavior.
- paid/online feature disablement without blocking local document recovery.

Definition of done:

- `python tests\validate_license.py`
- `python tests\validate_security_scan.py`
- admin payload privacy validator inside `tests\validate_license.py`

## F23 - Managed Cloud Grant Backend

Status: Complete.

Implement backend-facing grant client boundary for AWS S3, Azure Blob, and Google Cloud Storage.

Deliver:

- short-lived upload grants.
- short-lived download grants.
- encrypted-package-only upload path.
- encrypted-package-only download path.
- allowlisted cloud metadata.
- no long-lived cloud credentials on the PC.

Definition of done:

- `python tests\validate_cloud_boundary.py`
- `python tests\validate_backup.py`
- `python tests\validate_real_world_rag_e2e.py`

## F24 - Payment Entitlements

Status: Complete.

Add payment entitlement model without exposing documents.

Deliver:

- plans.
- feature entitlements.
- entitlement sync result.
- suspended/expired/active behavior.
- local export/recovery allowed when paid features stop.
- admin override state.
- disabled cloud/RAG tests without local data lockout.

Definition of done:

- `python tests\validate_license.py`
- `python tests\validate_security_scan.py`
- `python tests\validate_e2e.py`

## F25 - Production Windows UI

Status: Complete.

Build the usable PySide6 application.

Deliver:

- first-run setup.
- license activation.
- vault initialization.
- recovery key confirmation.
- matter list.
- document import/review queue.
- OCR status.
- duplicate warning.
- matter search.
- RAG question panel.
- backup status.
- restore drill.
- admin/license status display.
- about/release info.

Definition of done:

- `python tests\validate_ui.py`
- `python tests\validate_e2e.py`
- `python tests\validate_real_world_rag_e2e.py`

## F26 - PyInstaller Bundling And Release Packaging

Status: Complete.

Make Windows distribution production-ready.

Deliver:

- final `main.spec`.
- Tesseract bundle inclusion.
- product catalog inclusion.
- license public key inclusion.
- public Kenyan legal document manifest inclusion.
- provider API-key status command.
- native public Kenyan document E2E command with citations and confidence.
- no private keys.
- no `.env`.
- no credentials.
- no sample client documents.
- release ZIP manifest.
- portable install smoke.
- Windows clean-machine checklist.

Definition of done:

- `python tests\validate_frozen_build.py`
- `python tests\validate_release_bundle.py`
- `python tests\validate_portable_install.py`
- `python tests\validate_security_scan.py`

## F27 - Enterprise Documentation Masterpack

Status: Complete.

Add the documentation-first enterprise control layer before more code work.

Deliver:

- enterprise architecture.
- enterprise product roadmap.
- CI/CD and release gates.
- security and compliance rules.
- Windows distribution plan.
- end-to-end validation plan.
- commercial operations plan.
- docs validation requiring the enterprise masterpack.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_products.py`
- `python tests\validate_security_scan.py`
- `ruff check .`

## F28 - Native App End-To-End Workflow Hardening

Status: Complete.

Make the app prove the local product flow natively, not only through isolated scripts.

Deliver:

- first-run setup workflow validation.
- license activation/status display validation.
- vault initialization validation.
- document import, OCR/extraction, matter creation, search, RAG, backup, and restore workflow validation.
- provider API key settings for OpenAI, Anthropic, and future providers.
- redacted provider status display.
- no API keys in logs or backups.
- shared native workflow runner used by CLI, UI, and validators.
- `main.py --native-workflow-e2e` with redacted JSON output.

Definition of done:

- `python tests\validate_ui.py`
- `python tests\validate_e2e.py`
- `python tests\validate_rag.py`
- `python tests\validate_ai_providers.py`
- `python tests\validate_native_workflow.py`
- `python tests\validate_security_scan.py`

## F29 - Kenyan Public Document Corpus E2E Expansion

Status: Complete.

Expand the public Kenyan legal document test set and make it repeatable.

Deliver:

- public source manifest with URL, source name, expected file type, and hash after download.
- downloader that stores files outside tracked repo content.
- PDF, scanned PDF, DOCX where legally available, duplicate copy, corrupt file, and unsupported `.doc` coverage.
- many-question RAG test set with expected citation behavior.
- confidence scoring checks.
- no raw document text in logs.
- copy behavior checks for intake, quarantine, vault storage, backup, and restore.
- redacted report containing citation metadata, confidence, file-type counts, duplicate count, unsupported count, OCR count, and restore state.

Definition of done:

- `python scripts\download_public_kenyan_docs.py --output test-output\public-kenyan-documents`
- `python tests\validate_public_kenyan_e2e.py`
- `python tests\validate_real_world_rag_e2e.py`
- `python tests\validate_backup.py`
- `python tests\validate_security_scan.py`

## F30 - Installer, Code Signing, And Publishing

Status: Complete.

Add commercial distribution packaging.

Deliver:

- installer wrapper.
- install/uninstall path.
- desktop/start menu shortcuts.
- versioned release artifacts.
- code-signing guide.
- signed artifact verification.
- clean Windows VM test report template.
- publishing checklist.
- installer publishing manifest.
- signature verification script.

Definition of done:

- `python tests\validate_package.py`
- `python tests\validate_frozen_build.py`
- `python tests\validate_release_bundle.py`
- `python tests\validate_portable_install.py`
- `python tests\validate_installer_publishing.py`

## F31 - Automatic Update Channel

Status: Complete.

Add signed update planning and first implementation boundary.

Deliver:

- signed update manifest.
- current version check.
- update availability check.
- no silent forced update.
- rollback-safe download/install boundary.
- disabled update behavior for offline firms.
- signed manifest verifier.
- tamper and unsigned manifest rejection.
- explicit user approval requirement.
- offline-safe update check result.

Definition of done:

- `python tests\validate_update_channel.py`
- `python tests\validate_security_scan.py`
- `python main.py --selftest`

## F32 - Manual Windows App E2E Verification

Status: Complete.

Test the packaged Windows app as a user-facing product, not only through unit validators.

Deliver:

- real UI-backed document import actions.
- UI-backed RAG question action with confidence and citations.
- UI-backed backup and restore drill action.
- 50+ document manual-style app validator.
- packaged executable GUI smoke and workflow evidence.
- `evidence.md`.
- manual install/build/test/handover documentation.

Definition of done:

- `python tests\validate_manual_windows_app_e2e.py`
- packaged executable `--gui-smoke`
- packaged executable `--native-workflow-e2e`
- packaged executable public Kenyan document E2E
- full local gate

## F33 - Admin, License Sync, And Payment Entitlement Backend Boundary

Status: Complete.

Complete the enterprise commercial boundary without exposing documents.

Deliver:

- installation check-in payload.
- admin enable/disable state.
- license sync result.
- payment plan state.
- active/suspended/expired behavior.
- local export and recovery always allowed.
- paid cloud/RAG/hosted features disabled when entitlement is invalid.
- privacy validator for admin payload fields.
- persisted safe sync and payment state.
- UI Admin tab status check.
- packaged-app CLI smoke command.

Definition of done:

- `python tests\validate_admin_license_payment_boundary.py`
- `python tests\validate_license.py`
- `python tests\validate_security_scan.py`
- `python tests\validate_e2e.py`

## F34 - Managed Cloud Backup Backend Boundary

Status: Complete.

Make cloud backup enterprise-ready while keeping documents encrypted client-side.

Deliver:

- AWS S3 upload/download grant contract.
- Azure Blob upload/download grant contract.
- Google Cloud Storage upload/download grant contract.
- encrypted-package-only upload.
- allowlisted metadata only.
- interrupted upload safety.
- restore from clean machine with license plus recovery key.
- no long-lived cloud credentials on the PC.
- provider-specific grant contract validation.
- interrupted upload safety.
- clean-machine restore drill from downloaded encrypted package.
- packaged-app CLI smoke command.

Definition of done:

- `python tests\validate_cloud_boundary.py`
- `python tests\validate_backup.py`
- `python tests\validate_e2e.py`
- `python tests\validate_security_scan.py`
- `python main.py --managed-cloud-backup-e2e`

## F35 - Wakili-Mkononi Integration

Status: Complete.

Implement the user-approved integration boundary.

Deliver:

- matter export packet.
- citation packet handoff.
- no raw uncontrolled upload.
- user-approved sync only.
- audit event for every handoff.
- feature entitlement check.
- privacy validator for the handoff payload.
- `main.py --wakili-mkononi-e2e` redacted smoke command.

Definition of done:

- `python tests\validate_wakili_integration.py`
- `python tests\validate_e2e.py`
- `python tests\validate_rag.py`
- `python tests\validate_security_scan.py`
- `python main.py --wakili-mkononi-e2e`

## F36 - Hosted AI/LLM Boundary

Status: Active.

Add hosted AI only after local RAG is reliable.

Deliver:

- local citation packet as only prompt context.
- no model-memory-only answer path.
- redaction boundary.
- tenant/license entitlement check.
- audit event.
- offline fallback to local RAG packet only.
- provider-key status check.
- `main.py --hosted-ai-e2e` redacted smoke command.

Definition of done:

- `python tests\validate_hosted_ai_boundary.py`
- `python tests\validate_ai_providers.py`
- `python tests\validate_rag.py`
- `python tests\validate_real_world_rag_e2e.py`
- `python tests\validate_security_scan.py`
- `python main.py --hosted-ai-e2e`

## F37 - WakiliOS Firm Management

Status: Active.

Transform the Windows Legal Document Vault into WakiliOS, a litigation-focused legal firm management system. WakiliOS is the top-level product that runs on top of the existing document vault, RAG, search, intake, and backup modules.

### Architecture

WakiliOS is a single-process desktop application. The UI calls Python modules directly:

- Solo mode: UI → `wakilios.core` (in-process, no HTTP)
- Multi-seat mode: UI → `wakilios.client` → `wakilios.api` → `wakilios.core` (LAN/VPN)

The `wakilios.core` module owns firm/matter/fee/receipt/audit logic. Everything else (intake, vault, search, RAG, backup) delegates to the existing repo modules.

### Deliver

- Firm initialization, users, seats, roles (admin, advocate, clerk, accounts, read_only).
- Matter workspace CRUD with parties, activities, lodgings, court decisions, fees, receipts.
- Document intake through existing `intake/` module, linked to matters in `wakilios.core`.
- Search through existing `search/` module, scoped to current matter.
- RAG summaries through existing `rag/` + `ai/` modules.
- Calendar `.ics` export from matter events.
- Encrypted backup through existing `backup/` module.
- Audit event log viewable in Admin tab.
- Fee-receipt linking with `linked_fee_id`.
- Role-aware UI controls (write roles, accounts roles, summary roles, document roles).
- Solo mode: direct `wakilios.core` calls from UI (no server needed).
- Multi-seat mode: optional `wakilios.api` FastAPI wrapper + `wakilios.client` HTTP module.
- Offline read-only cache.

Definition of done:

- `python tests\validate_wakilios_backend.py`
- `python tests\validate_wakilios_api.py`
- `python tests\validate_ui.py`
- `python tests\validate_products.py`
- `python tests\validate_security_scan.py`
- `python main.py --wakilios-backend-e2e`
