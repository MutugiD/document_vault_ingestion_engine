# Enterprise Architecture

Document Vault Ingestion Engine is an enterprise Windows system built from three
local-first products plus commercial service boundaries.

## Product Boundaries

| Product | Responsibility | Enterprise rule |
| --- | --- | --- |
| Windows Legal Document Vault | Encrypted local custody, matter records, document versions, audit ledger, backup, restore | Local access and recovery must remain available even when paid features are disabled. |
| Document Intake Engine | Scan-folder/manual import, validation, duplicate detection, extraction, OCR, quality warnings, vault handoff | Plaintext source files are temporary and must not remain in app-managed temp areas. |
| Local Matter RAG Connector | Local indexing, retrieval, cited answers, confidence, provider handoff boundary | Answers must be grounded in local matter context and include citations. |

## Enterprise Layers

1. Windows desktop app: PySide6 workflows, CLI selftests, worker-thread execution.
2. Local services: licensing, vault, intake, extraction/OCR, search, RAG, backup.
3. Local stores: encrypted object store, SQLite metadata/search, audit ledger,
   encrypted backup packages.
4. Commercial boundaries: admin/license sync, payment entitlements, managed cloud
   grants, update channel, Wakili-Mkononi handoff, hosted AI boundary.
5. Distribution: PyInstaller one-folder bundle, release ZIP, installer wrapper,
   signing, checksums, clean Windows validation.

## Data Flow

1. User imports a file or drops it in a watched scan folder.
2. Intake copies to quarantine, hashes the source, detects type, validates file
   signature, and checks for duplicates.
3. Extraction/OCR creates local text and warnings without logging raw content.
4. Vault encrypts immutable document objects and records metadata/audit events in SQLite.
5. Search and Local Matter RAG index approved local text.
6. Backup creates encrypted snapshots with a manifest and allowlisted metadata.
7. Optional cloud upload uses short-lived grants issued by the owner backend.
8. Optional hosted AI receives only a local citation packet after user/provider
   entitlement checks.

## Local Storage

- Vault objects are encrypted with AES-GCM-derived object keys.
- SQLite stores matter/document/version metadata, audit events, OCR state, search
  index records, RAG chunks, license state, and backup state.
- Extracted text is local data and must be included only in encrypted local or
  cloud backup packages.
- Recovery keys remain user-held and are never uploaded.

## Licensing And Entitlements

- Offline signed license unlocks local use.
- Online sync updates admin enablement, paid plan, and feature flags.
- Expired or suspended entitlement stops paid/online features such as managed
  cloud backup and hosted AI.
- Local vault access, export, restore, and recovery remain available.

## Security And Privacy

- No raw legal documents in logs, telemetry, PR artifacts, or CI output.
- No matter names, client names, case numbers, filenames, OCR text, prompts, file
  hashes, recovery keys, or provider keys in admin check-in payloads.
- Cloud-visible metadata is limited to installation ID, snapshot ID, size,
  package hash, created timestamp, app version, and upload status.
- Hosted AI prompts must be built from local citation packets only.

## Windows Packaging

- Python baseline: 3.11.x, Windows 64-bit.
- Packaging baseline: PyInstaller one-folder bundle.
- Release bundle includes product catalog, license public key, public Kenyan
  document manifest, UI/CLI entrypoints, and validated runtime assets.
- Installer, code signing, update channel, and publishing are enterprise phases
  after the release ZIP remains reproducible and validated.

