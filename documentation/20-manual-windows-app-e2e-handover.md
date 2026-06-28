# 20 - Manual Windows App E2E Handover

## Purpose

This handover guide is for testing the packaged Windows app as a user would:
install or extract it, open it, add documents one by one, verify vault custody,
ask RAG questions, and run backup/restore.

## Fresh Build And Package

```powershell
py -3.11 tests\validate_frozen_build.py
py -3.11 tests\validate_release_bundle.py
py -3.11 tests\validate_portable_install.py
```

Expected release ZIP:

```text
release-output\DocumentVaultIngestionEngine-0.1.0-windows-x64.zip
```

## Fresh Install Or Extract

Portable extraction is validated under:

```text
test-output\portable-install\DocumentVaultIngestionEngine
```

Run:

```powershell
test-output\portable-install\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --selftest
test-output\portable-install\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --products
test-output\portable-install\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --providers
test-output\portable-install\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --gui-smoke 3000
```

## Manual App Session

Open the app:

```powershell
test-output\portable-install\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --gui
```

Then test these workflows:

1. Complete first-run setup fields.
2. Confirm license status area renders.
3. Confirm vault tab renders.
4. Add documents one by one from the Import tab.
5. Confirm each row reports accepted, duplicate, rejected, OCR pending/completed,
   extraction failed, or unsupported as appropriate.
6. Ask RAG questions from the Search and RAG tab.
7. Confirm confidence and citations are shown.
8. Create backup and restore drill from the Backup tab.
9. Confirm wrong-key restore is rejected.
10. Confirm provider API-key status is redacted.

## Required Document Mix

Use public/sample files only:

- PDF judgment.
- PDF court rules/forms.
- registry manual.
- practice directions.
- DOCX legal document.
- scanned/image-only PDF with OCR sidecar or selected OCR runtime.
- duplicate PDF copy.
- unsupported legacy `.doc`.
- corrupt PDF.
- empty file.

Create a reproducible 50+ file sample corpus:

```powershell
py -3.11 scripts\create_manual_e2e_corpus.py --output test-output\manual-e2e-corpus
```

Run the same one-by-one app workflow through the packaged executable:

```powershell
test-output\portable-install\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --manual-windows-app-e2e test-output\manual-e2e-corpus
```

This command opens the app in offscreen test mode, imports each file through the
UI/session boundary, asks 25 RAG questions, verifies citation and confidence
output, creates a backup, restores it, and confirms wrong-key restore failure.

## Evidence Rules

Record results in `evidence.md`.

Allowed evidence:

- document count.
- file type.
- status.
- warning category.
- citation count.
- confidence.
- elapsed time.
- artifact path.
- CI URL.

Do not record:

- real client documents.
- raw legal document text.
- provider API keys.
- recovery keys.
- cloud credentials.
- private signing keys.

## Handover Checklist

- Clean `main` before starting.
- Use a `feature/...` branch.
- Run packaged executable checks, not only source tests.
- Record defects and fixes in `evidence.md`.
- Run full local gate before PR.
- Open PR, wait for CI, inspect each failure, fix before merge.
- Merge only when PR and post-merge `main` CI are green.
