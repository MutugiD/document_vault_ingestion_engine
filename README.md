# WakiliOS

Multi-seat Windows legal firm management built on a local-first encrypted document vault, intake, matter RAG, and audit foundation.

This repository is being built documentation-first and feature by feature: clear architecture docs, a project tracker, small validation scripts, and a Windows packaging path before feature work expands.

## Current Status

F37 WakiliOS multi-seat firm management is in progress.

Implemented so far:

- Documentation pack under `documentation/`.
- Python package skeleton and `main.py --selftest`.
- Signed offline license validation.
- Encrypted local vault storage.
- Document intake validation and quarantine records.
- PDF/DOCX extraction and OCR adapter boundary.
- Tesseract OCR runtime bundle manifest validation.
- Repository and release security scan validation.
- Matter/document/version records and SQLite FTS5 search.
- Encrypted local backup/restore drill.
- Managed cloud backup boundary.
- Admin, license sync, payment entitlement, and managed cloud backend boundaries.
- Real-world PDF, DOCX, scanned PDF, RAG, backup, and restore validation.
- Public Kenyan document corpus E2E validation.
- Local Matter RAG Connector with citation packets and confidence.
- Wakili-Mkononi user-approved citation handoff boundary.
- Hosted AI boundary with local-citation-only prompts, entitlement checks, provider-key redaction, fallback, and audit events.
- WakiliOS firm backend with standard roles, litigation matter workspace tabs, court fees and receipts, `.ics` calendar export, read-only offline cache, AI summaries with citations, and audit events.
- PySide6 shell and worker pattern.
- PyInstaller package configuration validation.
- Real Windows PyInstaller one-folder build and frozen executable selftest.
- Release ZIP and sidecar manifest validation.
- Portable install smoke validation from the release ZIP.

## Published Products

1. WakiliOS.
2. Document Intake Engine.
3. Local Matter RAG Connector.

The authoritative product catalog lives in:

- `products/product_catalog.json`
- `products/catalog.py`

Validate it with:

```powershell
python tests\validate_products.py
```

## Product Boundary

In scope:

- Signed offline license with periodic entitlement sync.
- Local encrypted document vault.
- Document intake from watched folders and manual import.
- PDF/DOCX/image validation and text extraction.
- Local OCR using bundled Tesseract.
- Matter/document/version metadata.
- SQLite FTS5 local search.
- Local encrypted backups and restore drills.
- Managed encrypted cloud backup through short-lived AWS/GCP/Azure grants.
- Local matter-scoped RAG retrieval with citations.
- User-approved Wakili-Mkononi citation handoff boundary.
- Hosted AI/LLM boundary that only uses local RAG context and citations.

Deferred:

- Local LLM.
- Live Wakili-Mkononi transport.
- Live hosted provider transport.
- Direct Judiciary e-filing automation.

## Repository Layout

```text
.
  README.md
  BUILD.md
  main.py
  main.spec
  pyproject.toml
  requirements.txt
  requirements-dev.txt
  backup/
  core/
  intake/
  integrations/
  licensing/
  products/
  rag/
  scripts/
  search/
  security_checks/
  tests/
  tools/
  release/
  ui/
  vault/
  documentation/
```

## Local Validation

From the repo root:

```powershell
python tests\validate_docs.py
python tests\validate_skeleton.py
python tests\validate_products.py
python tests\validate_security_scan.py
python tests\validate_license.py
python tests\validate_vault.py
python tests\validate_intake.py
python tests\validate_extraction.py
python tests\validate_ocr_runtime.py
python tests\validate_search.py
python tests\validate_rag.py
python tests\validate_wakili_integration.py
python tests\validate_hosted_ai_boundary.py
python tests\validate_wakilios_backend.py
python tests\validate_backup.py
python tests\validate_cloud_boundary.py
python tests\validate_ui.py
python tests\validate_package.py
python tests\validate_e2e.py
python tests\validate_real_world_rag_e2e.py
python tests\validate_frozen_build.py
python tests\validate_release_bundle.py
python tests\validate_portable_install.py
python main.py --selftest
python main.py --managed-cloud-backup-e2e
python main.py --wakili-mkononi-e2e
python main.py --hosted-ai-e2e
python main.py --wakilios-backend-e2e
```

After dependencies are installed:

```powershell
python -m pip install -r requirements-dev.txt
ruff check .
```

## Documentation

Start here:

- [documentation/README.md](documentation/README.md)
- [documentation/STATUS.md](documentation/STATUS.md)
- [documentation/13-implementation-plan.md](documentation/13-implementation-plan.md)
- [documentation/16-end-to-end-testing-guide.md](documentation/16-end-to-end-testing-guide.md)
- [documentation/products/README.md](documentation/products/README.md)
