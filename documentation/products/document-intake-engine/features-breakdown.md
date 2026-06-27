# Document Intake Engine - Features Breakdown

## Implemented

| Feature | Evidence |
| --- | --- |
| quarantine copy | `tests/validate_intake.py`, `tests/validate_real_world_rag_e2e.py` |
| source hash | `tests/validate_intake.py` |
| duplicate detection | `tests/validate_intake.py`, `tests/validate_real_world_rag_e2e.py` |
| PDF signature detection | `tests/validate_intake.py` |
| DOCX signature detection | `tests/validate_intake.py` |
| PNG/JPEG/TIFF detection | `tests/validate_intake.py` |
| corrupt/empty/unsupported handling | `tests/validate_intake.py` |
| PDF text extraction | `tests/validate_extraction.py` |
| DOCX text extraction | `tests/validate_extraction.py` |
| scanned/image-only PDF pending OCR | `tests/validate_real_world_rag_e2e.py` |
| Tesseract runtime manifest | `tests/validate_ocr_runtime.py` |
| Tesseract runtime discovery | `tests/validate_ocr_runtime.py` |
| image OCR adapter | `tests/validate_extraction.py` |
| scanned PDF OCR fallback | `tests/validate_extraction.py`, `tests/validate_real_world_rag_e2e.py` |
| OCR text handoff to RAG | `tests/validate_real_world_rag_e2e.py` |
| manual private ingest runner | `tests/validate_manual_ingest_smoke.py` |
| redacted private ingest output | `tests/validate_manual_ingest_smoke.py` |

## Partially Implemented

| Feature | Current State | Missing |
| --- | --- | --- |
| OCR | execution adapter exists and supports fake/real engines | vetted Tesseract binary provenance |
| scanned PDFs | page/image OCR fallback exists | clean-machine bundled runtime validation |
| UI review | worker shell exists | operator review queue and duplicate/OCR status screens |

## Missing For MVP

| Feature | Validator Needed |
| --- | --- |
| vetted Tesseract binary bundle | release bundle validator extension |

## Missing For Commercial Release

| Feature | Validator Needed |
| --- | --- |
| watched-folder daemon | intake daemon validator |
| operator review UI | UI workflow validator |
| bundled Tesseract provenance | release bundle validator |
| OCR runtime clean-machine validation | portable install validator extension |
| redacted production ingestion logs | security scan/log validator |

## Release Validation Commands

```powershell
python tests\validate_intake.py
python tests\validate_extraction.py
python tests\validate_ocr_runtime.py
python tests\validate_real_world_rag_e2e.py
python tests\validate_manual_ingest_smoke.py
python tests\validate_frozen_build.py
python tests\validate_release_bundle.py
python tests\validate_portable_install.py
```
