# 05 - Mandatory Document Understanding, Text Extraction, and OCR

## Purpose

Convert every accepted document into local, searchable, structured document artifacts while preserving the original source bytes unchanged and encrypted.

The mandatory pipeline is:

```text
file signature and type detection
        -> native adapter
        -> Docling conversion and layout normalization
        -> OCR for image-only or low-text pages
        -> pages, blocks, tables, metadata, provenance, confidence
        -> local search and RAG handoff
```

Docling is a required production component. It is not a best-effort or optional enhancement. PyMuPDF, `python-docx`, and other native adapters remain useful for fast source-specific work, but their output must be normalized through the Docling document-understanding boundary before downstream indexing.

## Product and Security Requirements

The extraction subsystem must:

- run entirely on the local Windows device;
- run from the frozen application without requiring Python or user-installed packages;
- preserve the original document unchanged and encrypted at rest;
- support searchable PDFs, scanned PDFs, images, and supported Office formats;
- produce structured text, layout, table, metadata, provenance, and confidence artifacts;
- keep extraction failures separate from intake and vault storage failures;
- expose retryable and permanent failure states;
- keep extracted text, model output, and OCR output inside the local application boundary;
- delete rendered pages, preprocessed images, and decrypted working copies after success, failure, cancellation, and restart recovery.

Encrypted inputs must not be modified. Where authorized credentials are available, decryption occurs only into memory or a protected, unpredictable temporary workspace. Passwords and keys must never be logged.

## Runtime Stack

| Boundary | Required component | Responsibility |
| --- | --- | --- |
| File detection | Existing signature/type detector | Reject mismatched or unsupported inputs safely. |
| Native PDF adapter | PyMuPDF | Fast embedded text, page metadata, rendering, and page-level text signals. |
| Native Office adapters | `python-docx` and later Office adapters | Fast paragraphs, tables, and source metadata before normalization. |
| Document understanding | Docling | Mandatory conversion, reading order, layout blocks, figures, tables, and structured document representation. |
| Image preparation | Pillow/OpenCV | Deskew, orientation, grayscale, contrast, denoise, threshold, and resolution normalization. |
| OCR runtime | Bundled Tesseract | Local OCR for images and rendered image-only pages. |
| OCR language data | Bundled `tessdata` | Verified language packs selected by the configured document language policy. |
| Application packaging | PyInstaller one-folder Windows x64 build | Bundles Python, application dependencies, Docling packages, model assets, and verified OCR runtime. |
| Integrity | SHA-256 and byte-size manifests | Detect missing, replaced, or tampered runtime and model files. |

The build environment installs dependencies from the repository requirements files. The release artifact contains the resulting runtime; end users do not install Python, Docling, Tesseract, model packages, or language data separately.

## Mandatory Processing Steps

1. Validate the file signature, extension, size, and supported format.
2. Preserve the source hash and original bytes before processing.
3. Resolve the frozen application runtime root and validate Docling models and Tesseract files.
4. Select the native adapter and collect fast source metadata.
5. Extract embedded text page by page where available.
6. Convert the source through Docling using the verified local model directory.
7. Normalize Docling output into pages, blocks, reading order, tables, figures, and provenance.
8. Mark pages with missing, sparse, rotated, or low-quality text as OCR candidates.
9. Preprocess only temporary derivatives and run bundled Tesseract on OCR candidates.
10. Merge native, Docling, and OCR output without losing page or block provenance.
11. Calculate confidence, word/character counts, warnings, and retryability.
12. Hand off only validated local artifacts to search/RAG.
13. Remove temporary rendered pages, preprocessing files, and decrypted workspaces.

Searchable PDFs must not be OCR-processed in full by default. OCR is page-scoped and used where native or Docling extraction does not produce sufficient usable text.

## Docling Normalization Contract

Docling is the required normalization boundary for all supported documents. The implementation must use its structured document representation rather than treating Markdown or plain text as the sole result.

Each normalized block should contain:

- `block_type` such as heading, paragraph, list, caption, figure, table, header, or footer;
- `page_number`;
- `text` when applicable;
- `bbox` when supplied by the source pipeline;
- reading-order position;
- source/provenance reference;
- OCR/native/Docling origin;
- confidence where available.

Tables must retain row/column relationships, cell text, spans, and page provenance. The normalized text remains available for FTS/RAG, but downstream consumers must be able to use blocks and tables for chunking and citations.

## Extraction Result Contract

The existing flat result fields remain compatible for current callers. The additive structured result must contain, at minimum:

- `document_id` and `source_path`;
- `detected_file_type` and source hash;
- normalized `text`;
- page results and structured blocks;
- table artifacts and cell relationships;
- page count and pages processed;
- pages requiring OCR and pages completed by OCR;
- extractor, Docling, model, OCR engine, and runtime versions;
- OCR language, processing duration, and confidence indicators;
- warnings, errors, status, retryability, start time, and completion time.

Required statuses include `completed`, `completed_with_warnings`, `pending_tesseract`, `ocr_failed`, `model_runtime_unavailable`, `unsupported_input`, `password_required`, `invalid_password`, `corrupt_document`, and `extraction_failed`.

## Bundled Runtime and Integrity Boundary

The frozen bundle must include:

- the Python interpreter/runtime required by the frozen application;
- Docling and its transitive runtime packages;
- the pinned Docling model assets required by the selected conversion pipeline;
- `tesseract.exe` and the approved `tessdata/<language>.traineddata` files;
- runtime/model manifests containing provider, version, platform, relative path, byte size, and SHA-256;
- applicable third-party license and notice files.

Startup validation must reject missing files, absolute paths, path traversal, runtime-root escapes, duplicate paths, wrong platform/architecture, size mismatches, hash mismatches, unsupported model versions, and missing language data. The application must not silently download models or OCR data at runtime.

The packaged application must provide a health check that loads the Docling converter and verifies a bundled deterministic sample, and executes a bundled Tesseract sample. Health-check errors must identify the failed runtime boundary without exposing document text.

### Tesseract CI runtime pin

The immutable build-asset contract is committed in
`resources/tesseract-runtime.lock.json`. It pins the official Windows x64
source URL, SHA-256, executable version, platform, asset type, and license.
The CI worker downloads and verifies this exact asset only while building the
frozen application; no end-user installation or runtime download is allowed.

The controlled build stages and validates the asset with:

```powershell
python scripts/prepare_document_runtime.py
python tests/validate_ocr_runtime.py
python tests/validate_ocr_execution.py
```

The lock points to the official Tesseract 5.5.0 Windows x64 release installer,
version `5.5.0.20241111`, with SHA-256
`F3FC4236425B690C8BE756F35793F77394EE004BE0A6460A440C754D892F68BC`.
The build stages its executable, language data, notices, and manifest into the
frozen bundle; the installer itself is never shipped.

## Implementation Slices

### F05 - Native Extraction and Docling Normalization

- retain PyMuPDF and Office native adapters for fast source inspection;
- add mandatory Docling conversion and structured normalization;
- return additive pages, blocks, tables, metadata, and provenance;
- preserve original intake/vault behavior;
- report structured runtime failures without blocking storage.

### F06 - Bundled Image OCR

- bundle Tesseract and approved language data;
- preprocess temporary image derivatives;
- OCR JPG, JPEG, PNG, TIFF, and supported rendered pages;
- return confidence, language, runtime version, duration, and retryable failures.

### F07 - Scanned and Mixed PDFs

- detect image-only and mixed pages;
- render only OCR candidate pages with PyMuPDF;
- OCR candidates through the verified runtime;
- merge page-level native, Docling, and OCR artifacts;
- report progress, cancellation, cleanup, and partial failures.

### F08 - Layout and Structured Tables

- preserve Docling reading order and block types;
- retain table rows, columns, cells, spans, and bounding boxes;
- support figures, captions, headers, and footers;
- expose structured artifacts to local chunking and citation generation.

### F09 - Metadata and Quality Signals

- capture PDF/Office metadata, page count, file hash, language, word count, character count, and embedded-image indicators;
- record extraction provenance and confidence;
- distinguish no text, low-quality text, OCR failure, and model failure.

### F15 - Frozen Windows Runtime

- pin and install build dependencies from repository requirements;
- download approved Docling model assets during the controlled build;
- generate and validate Docling and Tesseract manifests;
- collect packages and model/runtime files in `main.spec`;
- validate the frozen executable, offline startup, health checks, release ZIP, and portable install.

## Verification

The validation sequence is:

```powershell
python -m pip install -r requirements-dev.txt
python tests\validate_docling_runtime.py
python tests\validate_ocr_runtime.py
python tests\validate_ocr_execution.py
python tests\validate_extraction.py
python tests\validate_document_upload_evidence.py
python tests\validate_docs.py
python tests\validate_security_scan.py
python tests\validate_e2e.py
python tests\validate_real_world_rag_e2e.py
python tests\validate_public_kenyan_e2e.py
python tests\validate_frozen_build.py
python tests\validate_release_bundle.py
python tests\validate_portable_install.py
ruff check .
```

Public Kenyan Judiciary and Supreme Court documents are downloaded only to `test-output\public-kenyan-documents`. The document-extraction and OCR PRs validate searchable and scanned Kenyan uploads, UI intake, vault storage, OCR, and restore evidence. No legal documents, derivatives, or generated output are committed.

The acceptance gate requires searchable documents to produce native text plus Docling structure, scanned Kenyan documents to produce OCR text with page/block provenance and confidence, uploaded documents to be preserved through UI intake and encrypted vault storage, tables to preserve relationships, runtime tampering to fail clearly, and the frozen executable to run without Python installed.

## Current Boundaries and Compatibility

The first documentation/packaging PR establishes the mandatory runtime and result contract. The dependent document-extraction PR implements the Docling adapter and structured result fields. Existing flat `ExtractionResult` callers remain supported through additive fields and compatibility projections until all consumers use structured artifacts.

No cloud OCR, cloud parsing, runtime model download, machine-wide PATH dependency, or user-installed Python is permitted. The document-extraction and OCR implementation PRs remain separate, but both runtime paths must be bundled into the current Windows application before release.
