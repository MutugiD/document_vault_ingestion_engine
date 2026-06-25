# Project Tracker

Document Vault Ingestion Engine is a local-first Windows application for legal document intake, encrypted vault custody, local search, licensing, backup, and restore.

## Current Phase

F8 UI package planning.

## Accepted Decisions

| ID | Decision | Impact |
| --- | --- | --- |
| AD1 | Use Python 3.11.9 as the Windows build baseline. | Keeps packaging predictable for native dependencies. |
| AD2 | Use PyInstaller one-folder packaging first. | Clean, inspectable Windows bundle before installer wrapping. |
| AD3 | Use signed offline license plus periodic online sync. | Supports unreliable internet while preserving monetization controls. |
| AD4 | Use client-side encrypted backup packages for cloud. | Admin/backend cannot decrypt legal documents. |
| AD5 | Defer RAG, embeddings, Wakili-Mkononi, and direct e-filing. | Keeps first product focused on custody, intake, search, and recovery. |

## Open Decisions

| ID | Decision Needed | Default |
| --- | --- | --- |
| OD1 | Exact OCR binary distribution for Windows. | Bundle Tesseract 5.x with recorded provenance and checksum. |
| OD2 | Exact managed cloud provider priority. | Implement provider-neutral grant interface first. |
| OD3 | Installer wrapper after PyInstaller one-folder build. | Defer until frozen `--selftest` passes. |

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
| F8 UI/package | Planned | `tests/validate_ui.py`, `tests/validate_package.py` placeholders |

## Next Actions

1. Merge F7 only after CI is green.
2. Start F8 UI/package on `feature/f8-ui-package-v1`.
3. Add PySide6 shell, worker thread pattern, package selftest, and PyInstaller validation.
