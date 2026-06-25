# Document Vault Ingestion Engine - Planning Documentation

This documentation pack defines the F0 planning and implementation baseline for a local-first Windows legal document vault and ingestion engine.

It mirrors the IFC Converter documentation discipline:

- architecture before feature work
- defect and decision register
- feature-by-feature docs
- validation scripts per feature
- package and clean-machine acceptance criteria

## How To Read

1. Start with [00-system-overview.md](00-system-overview.md) and [01-architecture-e2e.md](01-architecture-e2e.md).
2. Read [02-defects-and-remedies.md](02-defects-and-remedies.md) for open risks and accepted decisions.
3. Walk the feature docs in order from [03-local-storage-vault.md](03-local-storage-vault.md) through [10-ui-threading-workflows.md](10-ui-threading-workflows.md).
4. Close with [11-packaging-distribution.md](11-packaging-distribution.md), [12-error-handling-reporting.md](12-error-handling-reporting.md), and [13-implementation-plan.md](13-implementation-plan.md).
5. Use [STATUS.md](STATUS.md) as the live tracker.

## Document Map

| File | Topic |
| --- | --- |
| [STATUS.md](STATUS.md) | Current phase, accepted decisions, progress, next actions |
| [FINDINGS-SUMMARY.md](FINDINGS-SUMMARY.md) | Executive summary and transition findings |
| [00-system-overview.md](00-system-overview.md) | Scope, non-goals, product boundary |
| [01-architecture-e2e.md](01-architecture-e2e.md) | End-to-end dataflow and layers |
| [02-defects-and-remedies.md](02-defects-and-remedies.md) | Defect/risk register and remedies |
| [03-local-storage-vault.md](03-local-storage-vault.md) | Encrypted local storage and SQLite metadata |
| [04-document-intake-validation.md](04-document-intake-validation.md) | Quarantine, file validation, duplicates |
| [05-text-extraction-ocr.md](05-text-extraction-ocr.md) | PDF/DOCX extraction and OCR |
| [06-matter-document-versioning.md](06-matter-document-versioning.md) | Matters, documents, versions, lifecycle |
| [07-search-indexing.md](07-search-indexing.md) | SQLite FTS5 search and rebuild strategy |
| [08-licensing-security.md](08-licensing-security.md) | Offline license, sync boundary, crypto rules |
| [09-backup-restore-cloud.md](09-backup-restore-cloud.md) | Local backup, restore drill, managed cloud grants |
| [10-ui-threading-workflows.md](10-ui-threading-workflows.md) | PySide6 shell and worker flow |
| [11-packaging-distribution.md](11-packaging-distribution.md) | PyInstaller, bundled tools, clean VM |
| [12-error-handling-reporting.md](12-error-handling-reporting.md) | Failure modes and reporting |
| [13-implementation-plan.md](13-implementation-plan.md) | Incremental feature plan |

## Status Legend

- Done: implemented and validated.
- Active: currently being implemented.
- Planned: designed but not implemented.
- Blocked: needs external input or dependency.
- Deferred: intentionally out of current scope.
