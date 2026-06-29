# Enterprise Product Roadmap

This roadmap starts after F26, which completed PyInstaller release packaging
hardening and public Kenyan document E2E commands.

## Sequencing Rules

- Use one branch and PR per feature.
- Use branch names beginning with `feature/`.
- Never include `codex` in branch names.
- Merge the active PR into `main` before starting the next feature.
- Every feature updates `documentation/STATUS.md`,
  `documentation/13-implementation-plan.md`, product docs or enterprise docs, and
  the relevant validators.

## F27 - Enterprise Documentation Masterpack

Branch: `feature/f27-enterprise-documentation-masterpack-v1`

Status: Complete.

Deliver:

- Enterprise architecture, roadmap, CI/CD, release, security, validation, Windows
  distribution, and commercial operations documents.
- Docs validator requires the enterprise masterpack.
- Tracker and implementation plan show F27 as the current enterprise planning reset.

Definition of done:

- `python tests\validate_docs.py`
- `python tests\validate_products.py`
- `python tests\validate_security_scan.py`
- `ruff check .`

## F28 - Native App End-To-End Workflow Hardening

Branch: `feature/f28-native-app-e2e-workflows-v1`

Status: Complete.

Deliver:

- Native workflow validation for setup, license, vault, import, OCR, matter,
  search, RAG, backup, restore, admin status, and provider-key settings.
- Redacted provider key status for OpenAI, Anthropic, and future providers.
- App-level E2E validator that follows the UI/backend boundary.
- Shared native workflow runner used by CLI, UI, and tests.
- `main.py --native-workflow-e2e` with redacted JSON output.

Definition of done:

- `python tests\validate_ui.py`
- `python tests\validate_e2e.py`
- `python tests\validate_rag.py`
- `python tests\validate_ai_providers.py`
- `python tests\validate_native_workflow.py`
- `python tests\validate_security_scan.py`

## F29 - Kenyan Public Document Corpus E2E Expansion

Branch: `feature/f29-kenyan-public-corpus-e2e-v1`

Status: Complete.

Deliver:

- Expanded public-source manifest for Kenyan legal documents.
- Repeatable downloader that stores files outside tracked repository content.
- PDF, scanned PDF, DOCX where legally available, duplicate, corrupt, and legacy
  unsupported-file coverage.
- Many-question RAG checks with citations and confidence.
- Redacted output with no raw extracted legal text in logs.
- Duplicate copy, unsupported legacy `.doc`, DOCX, and scanned PDF sidecar OCR coverage.

Definition of done:

- `python scripts\download_public_kenyan_docs.py --output test-output\public-kenyan-documents`
- `python tests\validate_public_kenyan_e2e.py`
- `python tests\validate_real_world_rag_e2e.py`
- `python tests\validate_backup.py`
- `python tests\validate_security_scan.py`

## F30 - Installer, Code Signing, And Publishing

Branch: `feature/f30-installer-code-signing-publishing-v1`

Status: Complete.

Deliver:

- Installer wrapper, install/uninstall behavior, shortcuts, checksums, signing
  guide, signed artifact verification, clean Windows checklist, and publishing
  checklist.
- Installer publishing manifest and signature verification script.

Definition of done:

- `python tests\validate_package.py`
- `python tests\validate_frozen_build.py`
- `python tests\validate_release_bundle.py`
- `python tests\validate_portable_install.py`
- `python tests\validate_installer_publishing.py`
- `python tests\validate_security_scan.py`

## F31 - Automatic Update Channel

Branch: `feature/f31-automatic-update-channel-v1`

Status: Complete.

Deliver:

- Signed update manifest, version check, availability check, unsigned update
  rejection, no silent forced update, rollback-safe boundary, and offline behavior.
- RSA-PSS/SHA-256 verifier and offline-safe update result.

Definition of done:

- `python tests\validate_package.py`
- `python tests\validate_update_channel.py`
- `python tests\validate_security_scan.py`
- `python main.py --selftest`

## F32 - Manual Windows App E2E Verification

Branch: `feature/f32-manual-windows-app-e2e-v1`

Status: Complete.

Deliver:

- Real UI-backed document import actions.
- UI-backed RAG question action with confidence and citations.
- UI-backed backup and restore drill action.
- 50+ document manual-style app validator.
- Packaged executable GUI smoke and workflow evidence.
- `evidence.md`.
- Manual install/build/test/handover documentation.

Definition of done:

- `python tests\validate_manual_windows_app_e2e.py`
- packaged executable `--gui-smoke`
- packaged executable `--native-workflow-e2e`
- packaged executable public Kenyan document E2E
- full local gate

## F33 - Admin, License Sync, And Payment Entitlement Backend Boundary

Branch: `feature/f33-admin-license-payment-boundary-v1`

Status: Complete.

Deliver:

- Installation check-in payload, admin enable/disable state, license sync result,
  payment plan state, active/suspended/expired behavior, local recovery guarantee,
  privacy validator, persisted safe state, UI Admin tab status check, and
  packaged-app CLI smoke command.

Definition of done:

- `python tests\validate_admin_license_payment_boundary.py`
- `python tests\validate_license.py`
- `python tests\validate_security_scan.py`
- `python tests\validate_e2e.py`

## F34 - Managed Cloud Backup Backend Boundary

Branch: `feature/f34-managed-cloud-backup-boundary-v1`

Status: Active.

Deliver:

- AWS S3, Azure Blob, and Google Cloud Storage grant contracts, encrypted-only
  upload, allowlisted metadata, interrupted upload safety, clean-machine restore,
  no long-lived provider credentials on the PC, and packaged-app CLI smoke
  command.

Definition of done:

- `python tests\validate_cloud_boundary.py`
- `python tests\validate_backup.py`
- `python tests\validate_e2e.py`
- `python tests\validate_security_scan.py`
- `python main.py --managed-cloud-backup-e2e`

## F35 - Wakili-Mkononi Integration Boundary

Branch: `feature/f35-wakili-mkononi-integration-v1`

Deliver:

- User-approved matter export packet, citation packet handoff, audit event,
  entitlement check, and disabled-feature behavior that preserves local access.

Definition of done:

- `python tests\validate_e2e.py`
- `python tests\validate_rag.py`
- `python tests\validate_security_scan.py`

## F36 - Hosted AI/LLM Boundary

Branch: `feature/f36-hosted-ai-llm-boundary-v1`

Deliver:

- User-set provider API keys, provider health checks, local citation packet as
  prompt context, citations in every answer, confidence display, redaction
  boundary, and offline local-RAG fallback.

Definition of done:

- `python tests\validate_ai_providers.py`
- `python tests\validate_rag.py`
- `python tests\validate_real_world_rag_e2e.py`
- `python tests\validate_security_scan.py`
