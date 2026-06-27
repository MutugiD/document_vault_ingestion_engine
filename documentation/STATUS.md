# Project Tracker

Document Vault Ingestion Engine is a local-first Windows application for legal document intake, encrypted vault custody, local search, licensing, backup, and restore.

## Current Phase

F28 Native app end-to-end workflow hardening.

## Accepted Decisions

| ID | Decision | Impact |
| --- | --- | --- |
| AD1 | Use Python 3.11.9 as the Windows build baseline. | Keeps packaging predictable for native dependencies. |
| AD2 | Use PyInstaller one-folder packaging first. | Clean, inspectable Windows bundle before installer wrapping. |
| AD3 | Use signed offline license plus periodic online sync. | Supports unreliable internet while preserving monetization controls. |
| AD4 | Use client-side encrypted backup packages for cloud. | Admin/backend cannot decrypt legal documents. |
| AD5 | Publish three products through Local Matter RAG Connector. | Moves RAG into near-term scope while keeping Wakili-Mkononi and direct e-filing deferred. |

## Open Decisions

| ID | Decision Needed | Default |
| --- | --- | --- |
| OD1 | Exact OCR binary distribution for Windows. | Bundle Tesseract 5.x with recorded provenance and checksum. |
| OD2 | Exact managed cloud provider priority. | Implement provider-neutral grant interface first. |
| OD3 | Installer wrapper after PyInstaller one-folder build. | Implement after the F27 enterprise roadmap is merged. |

## Progress

| Feature | Status | Evidence |
| --- | --- | --- |
| F0 documentation and skeleton | Complete | PR #1 merged, documentation pack, package dirs, validators |
| F1 licensing | Complete | Offline license module, `tests/validate_license.py`, `main.py --selftest` licensing smoke check |
| F2 vault | Complete | SQLite metadata, audit ledger, AES-GCM object storage, `tests/validate_vault.py` |
| F3 intake | Complete | Quarantine import, signature detection, duplicate detection, SQLite records, `tests/validate_intake.py` |
| F4 extraction/OCR | Complete | PyMuPDF PDF extraction, python-docx extraction, OCR adapter boundary, `tests/validate_extraction.py` |
| F5 matter/search | Complete | Matter records, document versions, SQLite FTS5, matter-scoped search, `tests/validate_search.py` |
| F6 backup/restore | Complete | Encrypted local backup package, manifest, restore drill, wrong-key behavior, `tests/validate_backup.py` |
| F7 cloud boundary | Complete | Provider-neutral grants, metadata allowlist, encrypted-package-only upload boundary, `tests/validate_cloud_boundary.py` |
| F8 UI/package | Complete | PySide6 shell, worker pattern, package selftest, `tests/validate_ui.py`, `tests/validate_package.py` |
| F9 frozen build | Complete | Real PyInstaller one-folder build, frozen executable selftest, `tests/validate_frozen_build.py` |
| F10 local matter RAG | Complete | Three-product strategy, `matter_rag` entitlement, local hybrid retrieval, citation packet, `tests/validate_rag.py` |
| F11 end-to-end verification | Complete | Licensed intake-to-RAG-to-backup-to-restore workflow, `tests/validate_e2e.py` |
| F12 three-product catalog | Complete | Product catalog JSON/API, product validators, release boundaries, `tests/validate_products.py` |
| F13 release bundle | Complete | Checked ZIP, sidecar manifest, product metadata, artifact hashes, `tests/validate_release_bundle.py` |
| F14 portable install smoke | Complete | Release ZIP extraction, frozen executable `--selftest`, product catalog check, `tests/validate_portable_install.py` |
| F15 OCR runtime bundle contract | Complete | Tesseract runtime manifest, hash/size checks, path guard, `tests/validate_ocr_runtime.py` |
| F16 security scan | Complete | Repository and release filename/secret-shape scan, `tests/validate_security_scan.py` |
| F17 real-world RAG E2E | Complete | Old PDF, DOCX, scanned PDF, many grounded RAG questions, copies, vault, backup, restore, `tests/validate_real_world_rag_e2e.py` |
| F18 end-to-end testing guide | Complete | Windows test guide, release gate, failure triage, `documentation/16-end-to-end-testing-guide.md` |
| F19 product documentation pack | Complete | Product architecture, feature breakdown, gap analysis, implementation docs under `documentation/products/` |
| F20 OCR execution and Tesseract bundling | Complete | OCR engine adapter, runtime discovery, image OCR, scanned PDF fallback, RAG E2E OCR coverage |
| F21 manual private document test runner | Complete | Local-only private folder runner, redacted output, intake, vault, search, RAG, backup, restore coverage |
| F22 admin and license sync backend boundary | Complete | Privacy-safe check-in payload, sync state, admin disablement, grace-expired paid feature stop, local data access preserved |
| F23 managed cloud grant backend | Complete | AWS/Azure/GCP grant requests, encrypted-package upload/download boundary, credential-bearing grant rejection |
| F24 payment entitlements | Complete | Plan features, active/suspended/expired behavior, admin override, cloud/RAG disablement without local lockout |
| F25 production Windows UI | Complete | PySide6 workflow tabs for setup, license, vault, matters, import/OCR, search/RAG, backup/restore, admin status, and release info |
| F26 PyInstaller bundling and release packaging | Complete | Release ZIP includes product catalog, license public key, public Kenyan doc manifest, provider-key status, public Kenyan E2E command, and checklist |
| F27 enterprise documentation masterpack | Complete | Enterprise architecture, roadmap, CI/CD release gate, security, Windows distribution, E2E validation, and commercial operations docs |
| F28 native app end-to-end workflow hardening | Active | Shared native workflow runner, CLI command, UI workflow button, provider-key redaction, and app-level validator |

## Next Actions

1. Merge F28 only after UI, E2E, RAG, AI-provider, native workflow, security, and Ruff checks pass.
2. Start F29 Kenyan public document corpus E2E expansion.
3. Continue through F30-F35 one PR at a time until installer/signing, update channel, admin/payment, managed cloud, Wakili-Mkononi, and hosted AI boundaries are complete.
