# Document Intake Engine - Implementation Plan

## Target

Make intake reliable for real scanned and drafted legal documents before commercial packaging.

## PR Sequence

| Feature | Branch | Scope |
| --- | --- | --- |
| F20 | `feature/f20-ocr-execution-v1` | Complete: Tesseract discovery, execution adapter, image OCR, scanned PDF fallback |
| F21 | `feature/f21-manual-private-document-test-runner-v1` | local-only private file smoke runner |
| F25 | `feature/f25-production-windows-ui-v1` | import queue, duplicate warning, OCR status, review handoff |
| F26 | `feature/f26-pyinstaller-release-packaging-v1` | Tesseract files in PyInstaller and release validation |

## Acceptance Gate

```powershell
python tests\validate_intake.py
python tests\validate_extraction.py
python tests\validate_ocr_runtime.py
python tests\validate_e2e.py
python tests\validate_real_world_rag_e2e.py
python tests\validate_security_scan.py
```

## Packaging Gate

```powershell
python tests\validate_frozen_build.py
python tests\validate_release_bundle.py
python tests\validate_portable_install.py
```

## Manual Field Test Target

The private runner must support:

```powershell
python scripts\manual_ingest_smoke.py --input D:\commercial\private-vault-test-documents
```

It must print redacted counts/statuses only and never raw legal document text.
