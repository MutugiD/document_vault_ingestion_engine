# WakiliOS

Multi-seat Windows legal firm management built on a local-first encrypted document vault, intake, matter RAG, and audit foundation.

This repository is built documentation-first and feature by feature: clear architecture docs, a project tracker, small validation scripts, and a Windows packaging path.

## Current Status

The v0.1.0 production path is still gated by the dependent extraction/OCR PR
chain, verified Windows runtime assets, and green checks. The frozen application
is not considered release-ready while those gates are red or pending.

**v0.1.0 release candidate** — all features through F39 complete, CI/CD green, E2E validated.

### What's implemented

- **4-tab desktop UI**: Dashboard (setup + license + vault), Workspace (matters + sub-tabs), Settings (import + search/RAG + AI keys + backup + admin), About
- **Professional dark theme**: Navy/blue stylesheet (`ui/wakilios.qss`)
- **Solo mode**: In-process backend, no server needed; UI calls `wakilios.core` directly
- **Multi-seat mode**: Optional FastAPI server (`wakilios.api`) with HTTP client (`wakilios.client`)
- **Hard-coded RSA public key** (spec §6.2): No swappable `public_key.pem` on disk; Cython-compiled to `.pyd` in release builds
- **Clock-rollback guard**: NTP cross-check, file-backed monotonic store
- **IFC-Converter CI/CD pattern**: Lint+format, dependency audit, test+coverage, build+smoke, CodeQL weekly
- **Tag-triggered release**: Cython obfuscation, selftest gate, GitHub Release with zip + sha256
- **FTS5 query sanitizer**: Handles hyphens and special characters in search
- **Signed offline license** with RSA-PSS/SHA-256
- **Encrypted local vault** (AES-GCM, SQLite metadata)
- **Document intake** (quarantine, signature detection, duplicates)
- **Mandatory Docling document understanding** after native PDF/DOCX inspection,
  including structured blocks, tables, provenance, and local search/RAG handoff
- **Bundled Tesseract OCR** with TSV-derived confidence and frozen-runtime validation
- **Matter RAG** with citation-backed responses
- **Backup/restore** with encrypted packages and wrong-key rejection
- **Public Kenyan corpus validation** outside Git under `test-output\public-kenyan-documents`
- **Encrypted originals preserved** when extraction or OCR is retryable

### Build and run

End users receive a frozen Windows application and do not install Python,
Docling, Tesseract, model files, or other runtime dependencies manually.

Python is required only on the controlled build machine:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
python main.py --selftest
python main.py --gui
```

The controlled build prepares and verifies the Docling model and Tesseract
runtime before PyInstaller. The immutable Windows x64 Tesseract source URL,
SHA-256, version, platform, and license are pinned in
`resources/tesseract-runtime.lock.json`; the application never downloads OCR
assets at end-user runtime. See
[documentation/05-text-extraction-ocr.md](documentation/05-text-extraction-ocr.md)
for the complete procedure.

### Validation

```powershell
python tests\validate_license.py
python tests\validate_wakilios_backend.py
python tests\validate_wakilios_api.py
python tests\validate_vault.py
python tests\validate_search.py
python tests\validate_rag.py
python tests\validate_backup.py
python tests\validate_e2e.py
python tests\validate_extraction.py
python tests\validate_docling_runtime.py
python tests\validate_ocr_runtime.py
python tests\validate_ocr_execution.py
python tests\validate_ui.py
python main.py --selftest
python main.py --products
```

### Release

See [RELEASE.md](RELEASE.md) and [BUILD.md](BUILD.md) for packaging and release instructions.

### Documentation

See [documentation/README.md](documentation/README.md) for the full documentation pack index and [documentation/STATUS.md](documentation/STATUS.md) for the live feature tracker.

### CI/CD

4-job CI on every PR and push to `main`:

1. **Lint & format** — `ruff check` + `ruff format --check`
2. **Dependency audit** — `pip-audit --strict`
3. **Test & coverage** — All validation suites with >=60% coverage
4. **Build bundle (smoke)** — PyInstaller build + `--selftest` gate

Plus weekly **CodeQL** security scanning.
