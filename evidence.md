# Manual Windows App E2E Evidence

Date: 2026-06-28  
Machine: Windows, PowerShell, Python 3.11.9 via `py -3.11`  
Branch: `feature/f32-manual-windows-app-e2e-v1`

## Package Under Test

Release ZIP:

```text
D:\commercial\document_vault_ingestion_engine\release-output\DocumentVaultIngestionEngine-0.1.0-windows-x64.zip
```

Portable extraction:

```text
D:\commercial\document_vault_ingestion_engine\test-output\portable-install\DocumentVaultIngestionEngine
```

Executable:

```text
D:\commercial\document_vault_ingestion_engine\test-output\portable-install\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe
```

## Fresh Build And Install Evidence

Commands run:

```powershell
py -3.11 tests\validate_frozen_build.py
py -3.11 tests\validate_release_bundle.py
py -3.11 tests\validate_portable_install.py
```

Result:

- `FROZEN BUILD VALIDATION PASS`
- `RELEASE BUNDLE VALIDATION PASS`
- `PORTABLE INSTALL VALIDATION PASS`

## Packaged Executable Evidence

The executable is built with `console=False`, so packaged executable checks were
run with `Start-Process -Wait -PassThru` to capture real exit codes.

Commands run:

```powershell
DocumentVaultIngestionEngine.exe --selftest
DocumentVaultIngestionEngine.exe --products
DocumentVaultIngestionEngine.exe --providers
DocumentVaultIngestionEngine.exe --native-workflow-e2e
DocumentVaultIngestionEngine.exe --gui-smoke 2500
DocumentVaultIngestionEngine.exe --public-kenya-e2e test-output\manual-e2e-corpus
DocumentVaultIngestionEngine.exe --manual-windows-app-e2e test-output\manual-e2e-corpus
```

Result:

- all commands exited `0`.
- GUI smoke opened the packaged app and closed automatically.
- native workflow verified setup, license, vault, import, RAG, backup, restore,
  and provider-key redaction.
- packaged public/manual E2E passed on the 57-file corpus.
- packaged manual Windows app E2E added 57 files one by one through the
  UI/session boundary and verified RAG, citations, backup, restore, duplicate
  handling, unsupported-file handling, corrupt-file handling, OCR state, and
  vault ciphertext checks.

## Document Corpus Evidence

Generated manual corpus:

```powershell
py -3.11 scripts\create_manual_e2e_corpus.py --output test-output\manual-e2e-corpus
```

Result:

- 57 total files.
- 45 generated PDF public/sample legal files.
- 7 generated DOCX public/sample legal drafting files.
- 1 scanned/image-only PDF with OCR sidecar.
- 1 duplicate PDF copy.
- 1 unsupported legacy `.doc`.
- 1 empty PDF.
- 1 corrupt PDF.

Manual-style UI validator:

```powershell
py -3.11 tests\validate_manual_windows_app_e2e.py
```

Result:

- `MANUAL WINDOWS APP E2E VALIDATION PASS`
- added 57 files one by one through the UI/session boundary.
- accepted at least 50 searchable documents.
- duplicate visibly detected.
- unsupported legacy `.doc` visibly handled.
- corrupt PDF produced an extraction failure warning instead of crashing.
- scanned PDF completed OCR through sidecar OCR.
- 25 RAG questions returned citations and confidence.
- vault object files did not expose checked plaintext probe.
- backup/restore passed.
- wrong-key restore failed safely.

Public live corpus:

```powershell
py -3.11 scripts\download_public_kenyan_docs.py --output test-output\public-kenyan-documents-manual
py -3.11 scripts\public_kenyan_e2e.py --input test-output\public-kenyan-documents-manual --workspace test-output\public-kenyan-e2e-manual --report test-output\public-kenyan-e2e-manual\report.json
```

Result:

- 9 public Judiciary/Supreme Court PDFs downloaded or found.
- 9 indexed documents.
- 690 RAG chunks.
- 10 citation/confidence checks passed.
- restore verified.

## Defects Found And Fixed

### Defect 1 - UI Buttons Were Mostly Placeholders

Finding:

- Import, RAG, and backup buttons did not perform real document/vault/RAG work.

Fix:

- Added `ManualAppSession`.
- Wired UI import to real intake, extraction, vault storage, search/RAG indexing.
- Wired Ask to real RAG citation/confidence output.
- Wired backup/restore buttons to real encrypted backup and restore drill.

### Defect 2 - Corrupt PDF Crashed Public E2E

Finding:

- 57-document packaged E2E exceeded timeout.
- Source reproduction showed `public_kenyan_e2e.py` crashed on corrupt PDF extraction.

Fix:

- Public E2E now catches extraction failures and records `extraction_failed_count`.
- Rebuilt package.
- Packaged 57-document E2E then exited `0`.

### Defect 3 - PowerShell Exit Code Capture For GUI Executable

Finding:

- Direct `& DocumentVaultIngestionEngine.exe --selftest` printed pass output but
  left `$LASTEXITCODE` unreliable because the executable is packaged with
  `console=False`.

Fix:

- Evidence and handover use `Start-Process -Wait -PassThru` for packaged
  executable exit-code checks.

## Performance Notes

- Source 57-document public/manual E2E after corrupt-PDF fix completed in about
  6.9 seconds.
- Packaged executable 57-document public/manual E2E and packaged manual Windows
  app E2E completed within the 10-minute evidence timeout after the corrupt-PDF
  fix.
- Manual UI validator completed in about 11 seconds locally.
- RAG questions in the manual UI validator stayed below the 15-second per-question
  guard.

## Final Decision

Pass with fixes.

The app now supports a fair manual Windows workflow through the packaged build:
open app, add documents one by one through UI/session boundary, track extraction
and duplicate/unsupported states, ask cited RAG questions with confidence, create
backup, restore, reject wrong key, and run package-level smoke checks.

Remaining next enterprise feature: admin/license/payment backend boundary.
