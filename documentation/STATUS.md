# Project Tracker

Document Vault Ingestion Engine is a local-first Windows application for legal document intake, encrypted vault custody, local search, licensing, backup, and restore.

## Current Phase

F2 encrypted vault planning.

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
| F2 vault | Planned | `tests/validate_vault.py` placeholder |
| F3 intake | Planned | `tests/validate_intake.py` placeholder |
| F4 extraction/OCR | Planned | `tests/validate_extraction.py` placeholder |
| F5 matter/search | Planned | `tests/validate_search.py` placeholder |
| F6 backup/restore | Planned | `tests/validate_backup.py` placeholder |
| F7 cloud boundary | Planned | `tests/validate_cloud_boundary.py` placeholder |
| F8 UI/package | Planned | `tests/validate_ui.py`, `tests/validate_package.py` placeholders |

## Next Actions

1. Merge F1 only after CI is green.
2. Start F2 encrypted vault on `feature/f2-encrypted-vault-v1`.
3. Add SQLite metadata, audit ledger, AES-GCM object storage, and wrong-key validation.
