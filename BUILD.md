# WakiliOS Windows Build, Bundle & Test Guide

Complete guide for building the WakiliOS `.exe` bundle, running validation tests on Windows, and collecting evidence.

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Developer Setup (Windows)](#2-developer-setup-windows)
3. [Running Validation Tests](#3-running-validation-tests)
4. [Building the .exe Bundle](#4-building-the-exe-bundle)
5. [Obfuscated Production Build](#5-obfuscated-production-build)
6. [Running the Frozen .exe](#6-running-the-frozen-exe)
7. [End-to-End Evidence Collection](#7-end-to-end-evidence-collection)
8. [Windows-Specific Testing](#8-windows-specific-testing)
9. [Release Bundle Creation](#9-release-bundle-creation)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Windows 10/11 | 64-bit | Target platform |
| Python | 3.11+ (3.12 recommended) | Runtime |
| Visual Studio Build Tools | 2022 with C++ workload | Cython obfuscation |
| PyInstaller | 6.5+ | Freezing to .exe |
| PySide6 | 6.6+ | Qt GUI framework |

## 2. Developer Setup (Windows)

Open PowerShell in the project root:

```powershell
# Create virtual environment
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
python -m pip install --upgrade pip wheel setuptools
pip install -e ".[dev]"

# Or install individually:
pip install PySide6 cryptography pydantic PyMuPDF python-docx
pip install fastapi uvicorn ruff pytest httpx python-multipart pyinstaller
```

### WSL/Linux Setup

```bash
# Using uv (recommended on WSL)
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python PySide6 cryptography pydantic PyMuPDF \
    python-docx fastapi uvicorn ruff pytest httpx python-multipart pyinstaller

# Run tests
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/validate_ui.py
```

## 3. Running Validation Tests

### Quick Smoke Test

```powershell
# All core validation (no GUI needed)
python tests\validate_vault.py
python tests\validate_intake.py
python tests\validate_search.py
python tests\validate_rag.py
python tests\validate_backup.py
python tests\validate_e2e.py
python tests\validate_license.py
python tests\validate_wakilios_backend.py
python tests\validate_wakilios_api.py
python tests\validate_security_scan.py
python tests\validate_products.py
python tests\validate_admin_license_payment_boundary.py

# UI validation (requires PySide6, offscreen mode)
set QT_QPA_PLATFORM=offscreen
python tests\validate_ui.py
```

### Full E2E Evidence Collection

```powershell
# Comprehensive backend E2E (38 tests: license, vault, intake, RAG, backup, backend)
python tests\e2e_evidence_redesign.py

# Interactive UI E2E (87 tests: layout, solo mode, matter CRUD, all workspace tabs,
# settings, admin, backup, selftest, workflow, sidebar navigation)
set QT_QPA_PLATFORM=offscreen
python tests\e2e_interactive_ui_test.py
```

### Expected Results

| Suite | Count | Description |
|---|---|---|
| validate_vault | PASS | AES-GCM encryption, wrong-key rejection |
| validate_intake | PASS | PDF/DOCX/PNG/TIF import, duplicate detection |
| validate_search | PASS | FTS5 full-text search with sanitization |
| validate_rag | PASS | Citation-backed responses, confidence scores |
| validate_backup | PASS | Encrypted backup, restore, wrong-key failure |
| validate_e2e | PASS | Intake-to-RAG-to-backup pipeline |
| validate_ui | PASS | 4-tab UI widget verification (all objectNames) |
| validate_license | PASS | RSA-4096 PSS signing, clock-rollback guard |
| validate_wakilios_backend | PASS | Solo mode, matter CRUD, audit log |
| validate_wakilios_api | PASS | FastAPI endpoints (Starlette TestClient) |
| e2e_evidence_redesign | 38 PASS | Multi-format intake, RAG performance, backup/restore |
| e2e_interactive_ui_test | 87 PASS | Full interactive UI test of every function |

## 4. Building the .exe Bundle

### Step 1: Install PyInstaller

```powershell
pip install pyinstaller>=6.5
```

### Step 2: Build

```powershell
# One-folder build (creates dist\WakiliOS\ with WakiliOS.exe and _internal\)
pyinstaller main.spec --noconfirm --clean
```

On Linux/WSL, this produces `dist/WakiliOS/WakiliOS` (Linux ELF binary).
On Windows, it produces `dist/WakiliOS/WakiliOS.exe`.

### Step 3: Verify the Bundle

```powershell
# Linux/WSL
QT_QPA_PLATFORM=offscreen ./dist/WakiliOS/WakiliOS --selftest

# Windows
dist\WakiliOS\WakiliOS.exe --selftest
```

Expected output:
```
SELFTEST PASS
Imported modules: ai, core, licensing, vault, intake, search, rag, backup, integrations, products, ui, wakilios
Licensing installation identity check: pass
Clock guard check: pass
App version: 0.1.0
```

### What Gets Bundled

The `main.spec` bundles:
- All Python packages: `ai`, `core`, `licensing`, `vault`, `intake`, `search`, `rag`, `backup`, `integrations`, `products`, `ui`, `wakilios`, `scripts`
- Data files:
  - `products/product_catalog.json` — 3-product catalog
  - `resources/license_public_key.pem` — RSA-4096 public key
  - `resources/public_kenyan_legal_docs.json` — Kenyan legal reference data
  - `ui/wakilios.qss` — e-filing stylesheet
  - `runtime/tesseract/` — OCR runtime (if present)

### Bundle Structure

```
dist/WakiliOS/
  WakiliOS.exe (or WakiliOS on Linux)
  _internal/
    products/product_catalog.json
    resources/license_public_key.pem
    resources/public_kenyan_legal_docs.json
    ui/wakilios.qss
    ... (PyInstaller runtime files)
```

## 5. Obfuscated Production Build

Release builds Cython-compile `licensing/core.py` and `licensing/clockguard.py` to `.pyd` so the RSA public key and license verification logic cannot be trivially read or patched.

### Prerequisites

```powershell
# Verify Cython + compiler available
python scripts\obfuscate_licensing.py --check

# Install Cython if needed
pip install "cython>=3,<4"
```

### Build Steps

```powershell
# 1. Obfuscate licensing (strips .py sources, compiles to .pyd)
python scripts\obfuscate_licensing.py

# 2. Build the frozen executable
pyinstaller main.spec --noconfirm --clean

# 3. Verify the frozen build works
dist\WakiliOS\WakiliOS.exe --selftest

# 4. Verify licensing is obfuscated (no licensing/*.py or licensing/*.pyc in bundle)
dir dist\WakiliOS\_internal\licensing\*.py  2>nul && echo FAIL: .py found || echo PASS: no .py
dir dist\WakiliOS\_internal\licensing\*.pyc 2>nul && echo FAIL: .pyc found || echo PASS: no .pyc
dir dist\WakiliOS\_internal\licensing\*.pyd 2>nul && echo PASS: .pyd obfuscated
```

### Inspect Mode (Keep Sources)

```powershell
# Compile to .pyd but keep .py for debugging
python scripts\obfuscate_licensing.py --keep-sources
```

## 6. Running the Frozen .exe

### GUI Mode

```powershell
# Normal GUI launch
dist\WakiliOS\WakiliOS.exe
```

### Self-Test Mode

```powershell
# CLI self-test (no GUI window, exits after verification)
dist\WakiliOS\WakiliOS.exe --selftest
```

### Offscreen Validation

```powershell
# Run UI validation tests against the frozen executable
set QT_QPA_PLATFORM=offscreen
python tests\validate_ui.py
python tests\e2e_interactive_ui_test.py
```

### Clean Machine Test

Copy the `dist\WakiliOS\` folder to a Windows machine with **no Python installed**:

```powershell
# On clean Windows machine (no Python, no VS)
WakiliOS.exe --selftest
# Expected: SELFTEST PASS
```

## 7. End-to-End Evidence Collection

### Backend E2E (38 tests)

```powershell
python tests\e2e_evidence_redesign.py
```

This exercises:
- License & key bundling (4096-bit RSA PSS)
- Vault initialization (AES-GCM)
- Multi-format document intake (PDF, DOCX, image-PDF, TXT rejection, duplicate detection)
- Matter creation & FTS5 search
- RAG performance (confidence, citations, latency)
- Encrypted backup & restore (wrong-key rejection)
- Solo mode backend (matter, party, fee, receipt CRUD, audit log)
- Bundle selftest

Output: `evidence/e2e_evidence_redesign.json`

### Interactive UI E2E (87 tests)

```powershell
set QT_QPA_PLATFORM=offscreen
python tests\e2e_interactive_ui_test.py
```

This exercises every UI function:
- Layout verification (sidebar, stat cards, tabs)
- Solo mode connection (login, role, status)
- Matter creation (new matter, list update)
- All 8 workspace sub-tabs (Summary, Parties, Activities, Lodgings, Court Decisions, Fees, Receipts, Documents)
- Add party/activity/lodging/court decision/fee/receipt
- Settings (import, search, RAG, AI keys, backup, admin)
- Admin sync (license status, entitlements)
- Audit log (refresh, event count)
- Backup & restore (create backup, restore drill)
- Selftest & native workflow
- Sidebar navigation (4 buttons, tab sync)

Output: `evidence/e2e_interactive_ui_evidence.json`

### Screenshot Collection

```powershell
set QT_QPA_PLATFORM=offscreen
python -c "from ui import *; app = create_app(); w = MainWindow(); w.show(); w.resize(1280,800); app.processEvents(); w.grab().save('evidence/screenshot.png'); w.close()"
```

## 8. Windows-Specific Testing

### Manual Windows App E2E

Requires a folder of test documents (PDFs, DOCX files):

```powershell
python scripts\manual_windows_app_e2e.py
```

This runs the full desktop workflow: document import, OCR, RAG queries, backup/restore. Requires 25+ Kenyan legal documents in the input folder.

### Portable Install Smoke Test

```powershell
python scripts\portable_install_smoke.py
```

Verifies the frozen executable works on a clean machine without Python.

### Validation on Windows

All validation suites run on Windows:

```powershell
set QT_QPA_PLATFORM=offscreen

# Run each suite
python tests\validate_vault.py
python tests\validate_intake.py
python tests\validate_search.py
python tests\validate_rag.py
python tests\validate_backup.py
python tests\validate_e2e.py
python tests\validate_ui.py
python tests\validate_license.py
python tests\validate_wakilios_backend.py
python tests\validate_wakilios_api.py
python tests\validate_security_scan.py
python tests\validate_products.py
python tests\validate_admin_license_payment_boundary.py

# Frozen build validation
python tests\validate_frozen_build.py
python tests\validate_release_bundle.py
```

### Important Windows Notes

1. **QT_QPA_PLATFORM**: Must be set to `offscreen` for headless/CI testing. On Windows, you can also use `windows` for GUI mode.

2. **python-multipart**: Required by FastAPI for file upload endpoints. Install with `pip install python-multipart`. Without it, `validate_wakilios_api.py` fails with `RuntimeError: Form data requires "python-multipart"`.

3. **PySide6**: The offscreen platform plugin is included with PySide6. No separate Qt installation needed.

4. **Path separators**: Use `\\` or raw strings in PowerShell. The Python code handles both `/` and `\\`.

5. **Antivirus**: Windows Defender may flag the `.exe` on first run. Add an exclusion for the `dist\WakiliOS\` folder.

## 9. Release Bundle Creation

After the frozen build passes self-test:

```powershell
# Create the release ZIP and sidecar manifest
python scripts\build_release_bundle.py
```

Output in `release-output/`:
- `DocumentVaultIngestionEngine-v0.1.0-windows-x64.zip` — the bundle
- `DocumentVaultIngestionEngine-v0.1.0-windows-x64.manifest.json` — sidecar manifest with SHA-256

### Release Bundle Validation

```powershell
python tests\validate_release_bundle.py
```

Checks:
- ZIP hash matches sidecar manifest
- No forbidden files (`.env`, credentials, private keys, recovery keys)
- Required entries present (executable, product catalog, public key, legal docs, manifest)
- Three product definitions in catalog
- All referenced validation scripts exist

### Release Bundle Contents

The ZIP contains:
- `WakiliOS/WakiliOS.exe` — main executable
- `WakiliOS/_internal/` — runtime dependencies
- `WakiliOS/_internal/products/product_catalog.json` — 3-product catalog
- `WakiliOS/_internal/resources/license_public_key.pem` — RSA-4096 public key
- `WakiliOS/_internal/resources/public_kenyan_legal_docs.json` — Kenyan legal data
- `WakiliOS/_internal/ui/wakilios.qss` — e-filing stylesheet
- `WakiliOS/release-manifest.json` — embedded manifest (no self-referencing hash)

## 10. Troubleshooting

### PyInstaller Build Fails

```
ModuleNotFoundError: No module named 'xxx'
```

Fix: Add the module to `hiddenimports` in `main.spec`, or ensure it's installed:
```powershell
pip install xxx
```

### Self-Test Fails

```
ImportError: No module named 'xxx'
```

The frozen build may be missing a dependency. Check `main.spec` hiddenimports and the `datas` list.

### PySide6 Offscreen Platform Missing

```
Could not find the Qt platform plugin "offscreen"
```

Fix: Ensure PySide6 is installed and the `_internal/PySide6/Qt/plugins/platforms/` folder exists in the bundle.

### Windows Path Issues

Use forward slashes in Python code — they work on both Windows and Linux. PySide6 file dialogs return native paths automatically.

### python-multipart Missing

```
RuntimeError: Form data requires "python-multipart" to be installed.
```

Fix: `pip install python-multipart` — required by FastAPI for file upload endpoints.

### Linux/WSL Build Creates Linux Binary

The PyInstaller build creates a binary for the host OS. To build a Windows `.exe`, run PyInstaller on Windows. The Linux build creates `dist/WakiliOS/WakiliOS` which is useful for development testing but cannot run on Windows.

For cross-platform release, use GitHub Actions (`.github/workflows/release.yml`) which builds on `windows-latest`.

### Cython Compilation Fails

```
error: Microsoft Visual C++ 14.0 or greater is required.
```

Fix: Install Visual Studio Build Tools 2022 with the "Desktop development with C++" workload. Verify with:
```powershell
python scripts\obfuscate_licensing.py --check
```

### Bundle Size Too Large

The one-folder build includes all PySide6 Qt libraries. Typical size: 150-250MB. To reduce:
1. Use UPX compression (set `upx=True` in `main.spec` and install UPX)
2. Exclude unused Qt modules (QtWebEngine, Qt3D, etc.)
3. Strip debug symbols (set `strip=True` in `main.spec`)

---

## Quick Reference

| Command | Purpose |
|---|---|
| `pyinstaller main.spec --noconfirm` | Build frozen .exe |
| `dist\WakiliOS\WakiliOS.exe --selftest` | Verify frozen build |
| `python tests\validate_ui.py` | UI widget validation |
| `python tests\e2e_evidence_redesign.py` | Backend E2E evidence |
| `python tests\e2e_interactive_ui_test.py` | Interactive UI E2E |
| `python scripts\obfuscate_licensing.py` | Compile licensing to .pyd |
| `python scripts\build_release_bundle.py` | Create release ZIP |
| `python tests\validate_release_bundle.py` | Validate release ZIP |