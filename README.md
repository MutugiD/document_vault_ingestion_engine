# WakiliOS

Multi-seat Windows legal firm management built on a local-first encrypted document vault, intake, matter RAG, and audit foundation.

This repository is built documentation-first and feature by feature: clear architecture docs, a project tracker, small validation scripts, and a Windows packaging path.

## Current Status

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
- **PDF/DOCX extraction** and OCR adapter boundary
- **Matter RAG** with citation-backed responses
- **Backup/restore** with encrypted packages and wrong-key rejection
- **5 Kenyan court judgment PDFs** tested end-to-end
- **14 validation suites** all passing

### Quick start

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
python main.py --selftest
python main.py --gui
```

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