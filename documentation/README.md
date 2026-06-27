# Document Vault Ingestion Engine - Planning Documentation

This documentation pack defines the planning and implementation baseline for a local-first Windows legal document vault and ingestion engine.

The documentation discipline is:

- architecture before feature work
- defect and decision register
- feature-by-feature docs
- validation scripts per feature
- package and clean-machine acceptance criteria

## How To Read

1. Start with [00-system-overview.md](00-system-overview.md) and [01-architecture-e2e.md](01-architecture-e2e.md).
2. Read [02-defects-and-remedies.md](02-defects-and-remedies.md) for open risks and accepted decisions.
3. Walk the feature docs in order from [03-local-storage-vault.md](03-local-storage-vault.md) through [10-ui-threading-workflows.md](10-ui-threading-workflows.md).
4. Close with [11-packaging-distribution.md](11-packaging-distribution.md), [12-error-handling-reporting.md](12-error-handling-reporting.md), [13-implementation-plan.md](13-implementation-plan.md), [14-three-products-rag-strategy.md](14-three-products-rag-strategy.md), [15-end-to-end-verification.md](15-end-to-end-verification.md), [16-end-to-end-testing-guide.md](16-end-to-end-testing-guide.md), [17-windows-distribution-release-checklist.md](17-windows-distribution-release-checklist.md), [18-installer-code-signing-publishing.md](18-installer-code-signing-publishing.md), and [19-automatic-update-channel.md](19-automatic-update-channel.md).
5. Read [enterprise/README.md](enterprise/README.md) for the enterprise architecture, release, CI/CD, validation, and commercial roadmap.
6. Read [products/README.md](products/README.md) for product-specific architecture, features, gaps, and implementation plans.
7. Use [STATUS.md](STATUS.md) as the live tracker.

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
| [14-three-products-rag-strategy.md](14-three-products-rag-strategy.md) | Three-product publishing strategy and local RAG boundary |
| [15-end-to-end-verification.md](15-end-to-end-verification.md) | Integrated licensing, vault, intake, RAG, backup, cloud, restore validation |
| [16-end-to-end-testing-guide.md](16-end-to-end-testing-guide.md) | Windows end-to-end testing guide and failure triage |
| [17-windows-distribution-release-checklist.md](17-windows-distribution-release-checklist.md) | Windows release, public Kenyan document verification, and distribution gate |
| [18-installer-code-signing-publishing.md](18-installer-code-signing-publishing.md) | Installer manifest, code-signing verification, and publishing checklist |
| [19-automatic-update-channel.md](19-automatic-update-channel.md) | Signed update manifest boundary and offline-safe update checks |
| [enterprise/README.md](enterprise/README.md) | Enterprise masterpack index |
| [enterprise/architecture.md](enterprise/architecture.md) | Enterprise architecture, product boundaries, local storage, and packaging |
| [enterprise/product-roadmap.md](enterprise/product-roadmap.md) | F27-F35 PR roadmap and definitions of done |
| [enterprise/ci-cd-release.md](enterprise/ci-cd-release.md) | CI/CD, release gates, PR rules, and validation command set |
| [enterprise/security-compliance.md](enterprise/security-compliance.md) | Privacy, license, backup, and hosted AI security rules |
| [enterprise/windows-distribution.md](enterprise/windows-distribution.md) | Windows packaging, installer, signing, and clean-machine path |
| [enterprise/e2e-validation-plan.md](enterprise/e2e-validation-plan.md) | End-to-end local, Kenyan corpus, private smoke, and provider validation |
| [enterprise/commercial-operations.md](enterprise/commercial-operations.md) | Admin, licensing, payment, managed cloud, support, and completion standard |
| [products/README.md](products/README.md) | Product-specific architecture, features, gaps, and implementation plans |

Product folders contain `architecture.md`, `features-breakdown.md`, `gap-analysis.md`, and `implementation.md` for each commercial product.

## Status Legend

- Done: implemented and validated.
- Active: currently being implemented.
- Planned: designed but not implemented.
- Blocked: needs external input or dependency.
- Deferred: intentionally out of current scope.
