# Document Intake Engine - Architecture

## Purpose

Document Intake Engine is the scan-folder and manual-import pipeline for validating legal documents, copying them into quarantine, extracting text, detecting duplicates, tracking OCR state, and handing accepted files into the encrypted vault.

## Module Boundaries

| Module | Responsibility |
| --- | --- |
| `intake` | file detection, quarantine copy, duplicate detection, intake records |
| `intake.extraction` | PDF/DOCX extraction and OCR-pending status |
| `intake.ocr_runtime` | Tesseract runtime manifest, hashes, traineddata checks |
| `vault` | encrypted custody after intake handoff |
| `search` | matter/document/version storage after extraction |
| `ui` | operator review, duplicate warnings, OCR status |
| `release` | bundled runtime validation for OCR-capable distribution |

## Data Flow

```text
source file
  -> signature detection
  -> quarantine copy
  -> duplicate hash check
  -> extraction or OCR status
  -> warnings
  -> vault object write
  -> document version text
  -> search/RAG availability
```

## Local Storage

Intake records live in `vault.sqlite`.

Quarantine files are copied under:

```text
vault/quarantine/
```

Rules:

- intake copies source files; it does not move or delete them
- rejected files still get an intake record
- duplicates are detected by source SHA-256
- OCR text remains local
- OCR-pending files are not indexed as if text exists

## Licensing And Entitlements

Requires `document_intake`.

Future entitlement behavior:

- disabled document intake blocks new paid imports
- local recovery/export remains available
- manual private test runner never uploads raw documents

## Security And Privacy

The intake engine must not log:

- raw legal text
- filenames in cloud metadata
- client names
- OCR text
- source hashes outside local vault metadata
- recovery keys

## Backup And Cloud Boundary

Accepted documents become encrypted vault objects and are included only through encrypted backup packages. Intake must not upload raw source files.

## Windows Packaging

PyInstaller bundle must include:

- intake modules
- PyMuPDF runtime files
- python-docx dependency files
- Tesseract runtime files once OCR execution is enabled
- Tesseract runtime manifest

Release validation must fail if OCR is enabled but required runtime files are absent.

## Validators

```powershell
python tests\validate_intake.py
python tests\validate_extraction.py
python tests\validate_ocr_runtime.py
python tests\validate_e2e.py
python tests\validate_real_world_rag_e2e.py
python tests\validate_frozen_build.py
python tests\validate_release_bundle.py
```
