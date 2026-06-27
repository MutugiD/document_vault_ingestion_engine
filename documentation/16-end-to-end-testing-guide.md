# 16 - End To End Testing Guide

## Purpose

This guide helps you test Document Vault Ingestion Engine end to end on Windows.

It covers:

- local developer setup
- fast smoke checks
- full validator suite
- real-world PDF, DOCX, scanned PDF, RAG, copy, vault, backup, restore testing
- frozen `.exe` testing
- release ZIP and portable install testing
- what to inspect when something fails

## Testing Rule

Run tests in layers. Do not start with the heavy frozen build.

Use this order:

1. Environment checks.
2. Fast source validators.
3. Feature validators.
4. End-to-end validators.
5. Frozen Windows build.
6. Release ZIP validation.
7. Portable install smoke test.

## Windows Setup

From PowerShell:

```powershell
cd D:\commercial\document_vault_ingestion_engine
py -3.11 --version
git status --short --branch
```

Expected:

```text
Python 3.11.x
## main...origin/main
```

If Python 3.11 is missing, install Python 3.11.9 64-bit before continuing.

## Virtual Environment

```powershell
cd D:\commercial\document_vault_ingestion_engine
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip wheel setuptools
pip install -r requirements-dev.txt
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

## Fast Smoke Test

Run:

```powershell
python main.py --selftest
python tests\validate_docs.py
python tests\validate_skeleton.py
python tests\validate_products.py
python tests\validate_security_scan.py
ruff check .
```

Expected output includes:

```text
SELFTEST PASS
DOC VALIDATION PASS
SKELETON VALIDATION PASS
PRODUCT CATALOG VALIDATION PASS
SECURITY SCAN VALIDATION PASS
All checks passed!
```

If this layer fails, fix it before running deeper tests.

## Feature Validators

Run:

```powershell
python tests\validate_license.py
python tests\validate_vault.py
python tests\validate_intake.py
python tests\validate_extraction.py
python tests\validate_ocr_runtime.py
python tests\validate_search.py
python tests\validate_rag.py
python tests\validate_backup.py
python tests\validate_cloud_boundary.py
python tests\validate_ui.py
python tests\validate_package.py
```

What each validator proves:

| Validator | What It Proves |
| --- | --- |
| `validate_license.py` | signed offline license, expiry, tamper, disabled, installation mismatch, feature flags |
| `validate_vault.py` | vault initialization, AES-GCM encrypted objects, wrong recovery key failure, audit events |
| `validate_intake.py` | quarantine copy, file signature detection, duplicates, corrupt/empty/unsupported handling |
| `validate_extraction.py` | PDF text, DOCX text, image OCR-pending boundary, unsupported extraction warning |
| `validate_ocr_runtime.py` | Tesseract manifest, file hashes, traineddata presence, path traversal rejection |
| `validate_search.py` | matter records, document versions, lifecycle states, SQLite FTS5 search |
| `validate_rag.py` | matter-scoped RAG chunks, retrieval, reranking, citation packet |
| `validate_backup.py` | encrypted backup package, wrong-key failure, restore drill |
| `validate_cloud_boundary.py` | short-lived grant boundary and no legal identifiers in cloud metadata |
| `validate_ui.py` | PySide6 shell and worker-thread contract |
| `validate_package.py` | PyInstaller spec, package selftest, packaging safety terms |

## Standard End-To-End Test

Run:

```powershell
python tests\validate_e2e.py
```

This proves the core flow:

1. Creates installation ID.
2. Validates signed license with all paid feature flags.
3. Initializes encrypted vault.
4. Generates a PDF fixture.
5. Imports it through quarantine.
6. Extracts text.
7. Stores original bytes in the encrypted vault.
8. Creates matter, document, and version metadata.
9. Searches the matter.
10. Builds RAG context.
11. Creates encrypted backup.
12. Uploads through managed cloud metadata boundary.
13. Restores backup.
14. Reads original bytes from restored vault.

Expected:

```text
E2E VALIDATION PASS
```

## Real-World RAG End-To-End Test

Run:

```powershell
python tests\validate_real_world_rag_e2e.py
```

This is the main stress test for current product behavior.

It generates:

- an old archived PDF with land, lease, rent, registry, and reconstruction facts
- a DOCX pleading with defence, counterclaim, evidence, deadline, and hearing-preparation facts
- an image-only scanned PDF with no extractable text
- a duplicate copy of the PDF
- a legacy `.doc` file

It validates:

- source files are copied into quarantine, not moved
- duplicate file copies are detected by SHA-256
- legacy `.doc` is currently rejected as unsupported
- original PDF, DOCX, and scanned PDF bytes are saved in encrypted vault objects
- encrypted vault object files do not equal plaintext source bytes
- matter, document, and version records are created
- scanned PDF remains `pending_tesseract` and is not indexed into RAG text
- forty grounded RAG questions retrieve cited local context from PDF and DOCX facts
- backup package bytes do not expose sample client/legal text
- managed cloud metadata remains allowlisted
- restored vault can read the original PDF, DOCX, and scanned PDF bytes

Expected:

```text
REAL WORLD RAG E2E VALIDATION PASS
```

## Frozen Windows Build Test

Run:

```powershell
python tests\validate_frozen_build.py
```

This deletes and rebuilds:

- `build/`
- `dist/`

It then runs:

```powershell
dist\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --selftest
dist\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --products
```

Expected:

```text
FROZEN BUILD VALIDATION PASS
```

## Release ZIP Test

After frozen build passes:

```powershell
python tests\validate_release_bundle.py
```

Expected:

```text
RELEASE BUNDLE VALIDATION PASS
```

Generated files:

```text
release-output\DocumentVaultIngestionEngine-0.1.0-windows-x64.zip
release-output\DocumentVaultIngestionEngine-0.1.0-windows-x64.manifest.json
```

Inspect the manifest:

```powershell
Get-Content release-output\DocumentVaultIngestionEngine-0.1.0-windows-x64.manifest.json
```

Check:

- `bundle_sha256` exists
- product catalog includes all three products
- file hashes are present
- no legal matter/client identifiers appear

## Portable Install Test

Run:

```powershell
python tests\validate_portable_install.py
```

Expected:

```text
PORTABLE INSTALL VALIDATION PASS
```

This extracts the release ZIP into:

```text
test-output\portable-install\DocumentVaultIngestionEngine
```

Then it runs the frozen app from that extracted folder.

Manual check:

```powershell
test-output\portable-install\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --selftest
test-output\portable-install\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --products
```

## Full Local Release Gate

Run this before merging release-sensitive work:

```powershell
python tests\validate_docs.py
python tests\validate_skeleton.py
python tests\validate_products.py
python tests\validate_security_scan.py
python tests\validate_ai_providers.py
python tests\validate_license.py
python tests\validate_vault.py
python tests\validate_intake.py
python tests\validate_extraction.py
python tests\validate_ocr_runtime.py
python tests\validate_search.py
python tests\validate_rag.py
python tests\validate_backup.py
python tests\validate_cloud_boundary.py
python tests\validate_ui.py
python tests\validate_package.py
python tests\validate_e2e.py
python tests\validate_real_world_rag_e2e.py
python tests\validate_public_kenyan_e2e.py
python tests\validate_manual_ingest_smoke.py
python tests\validate_frozen_build.py
python tests\validate_release_bundle.py
python tests\validate_portable_install.py
python main.py --selftest
ruff check .
```

All commands must pass.

## Testing With Your Own Legal Documents

Current automated validators generate deterministic fixtures. This keeps CI stable and avoids committing real legal documents.

For manual local testing with your own files:

1. Create a private folder outside the repo, for example:

   ```powershell
   mkdir D:\commercial\private-vault-test-documents
   ```

2. Put test copies there:

   ```text
   old-case-file.pdf
   pleading.docx
   scanned-annexure.pdf
   duplicate-copy.pdf
   legacy-word-file.doc
   ```

3. Do not commit these files.

4. Do not place client documents under:

   ```text
   tests/
   documentation/
   release-output/
   test-output/
   ```

5. Run the local-only private smoke runner:

   ```powershell
   python scripts\manual_ingest_smoke.py --input D:\commercial\private-vault-test-documents
   ```

Expected:

```text
MANUAL INGEST SMOKE PASS
```

The runner validates PDF, DOCX, scanned PDF, duplicate copy behavior, unsupported legacy `.doc`, vault encryption, search, RAG, backup, and restore. It prints redacted counts/statuses only and must not print raw document text or filenames.

## Testing With Public Kenyan Legal Documents

Download the public manifest set:

```powershell
python scripts\download_public_kenyan_docs.py --output test-output\public-kenyan-documents
```

Run the native app verification:

```powershell
python main.py --public-kenya-e2e test-output\public-kenyan-documents
```

After a frozen build:

```powershell
dist\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --public-kenya-e2e test-output\public-kenyan-documents
```

Expected output includes:

- `indexed_documents`
- `rag_chunks`
- `answers`
- `citations`
- `confidence`
- `restore_verified`

## AI Provider Keys

Set provider keys through environment variables or the AI Keys tab:

```powershell
$env:DOCUMENT_VAULT_OPENAI_API_KEY="..."
$env:DOCUMENT_VAULT_ANTHROPIC_API_KEY="..."
$env:DOCUMENT_VAULT_GOOGLE_API_KEY="..."
$env:DOCUMENT_VAULT_AZURE_OPENAI_API_KEY="..."
$env:DOCUMENT_VAULT_MISTRAL_API_KEY="..."
python main.py --providers
```

The command must show configured providers with redacted key values only.

## Failure Triage

Use this table:

| Failure | First Place To Look |
| --- | --- |
| license failure | `licensing/`, `tests/validate_license.py` |
| wrong recovery key behavior | `vault/`, `backup/`, `tests/validate_vault.py`, `tests/validate_backup.py` |
| PDF/DOCX import failure | `intake/`, `tests/validate_intake.py` |
| empty PDF text | `intake/extraction.py`, OCR status in result |
| scanned PDF not searchable | check Tesseract runtime discovery and `tests/validate_ocr_runtime.py` |
| RAG answer has no citations | run `tests/validate_rag.py`, then `tests/validate_real_world_rag_e2e.py` |
| backup leaks plaintext | `backup/`, `tests/validate_backup.py`, `tests/validate_real_world_rag_e2e.py` |
| cloud metadata contains legal identifiers | `backup/cloud_boundary.py`, `tests/validate_cloud_boundary.py` |
| frozen build failure | `main.spec`, `tests/validate_frozen_build.py` |
| release ZIP failure | `release/bundle.py`, `tests/validate_release_bundle.py` |
| portable install failure | `release/install_smoke.py`, `tests/validate_portable_install.py` |
| CI-only failure | open the GitHub run log and reproduce the exact validator locally |

## Current Known Boundaries

- Legacy `.doc` is rejected; DOCX is supported.
- Scanned PDFs remain `pending_tesseract` when no Tesseract runtime is present; with a valid bundled runtime, OCR text can feed search and RAG locally.
- RAG is local retrieval with citations; it does not call an LLM.
- Cloud backup is a boundary using short-lived grants; no real provider SDK upload is active.
- Wakili-Mkononi integration and direct e-filing are deferred.

## Clean Machine Test

On a clean Windows machine without Python:

1. Copy `release-output\DocumentVaultIngestionEngine-0.1.0-windows-x64.zip`.
2. Extract it.
3. Run:

   ```powershell
   .\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --selftest
   .\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --products
   ```

4. Confirm the app starts and returns success without Python installed.

This is the final manual gate before installer wrapping.
