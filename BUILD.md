# Windows Build Guide

This guide defines the local Windows build target for JurisNuru.

## Baseline

- Windows 10/11, 64-bit.
- Python 3.11.9, 64-bit.
- Visual Studio Build Tools 2022 with Desktop development with C++ workload (for Cython obfuscation).
- PyInstaller one-folder build.
- End-user machines must not need Python, Visual Studio, or a compiler.

## Developer Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
pip install ruff pytest coverage
```

## Start Testing Locally

Run these commands from the repository root in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python main.py --selftest
$env:QT_QPA_PLATFORM = "offscreen"
python tests\validate_ui.py
python scripts\create_manual_e2e_corpus.py --output test-output\manual-source-documents
python tests\validate_manual_windows_app_e2e.py
python tests\validate_manual_ingest_smoke.py
```

The generated corpus is synthetic and safe for UI testing; it intentionally includes duplicate,
empty, corrupt, and legacy files so the review queue can be exercised. For the standalone ingest
smoke runner, point `--input` at a folder containing at least one valid text-bearing PDF, one DOCX,
one valid scanned/image-only PDF, and one legacy `.doc` file.

```powershell
python scripts\manual_ingest_smoke.py --input D:\private-vault-test-documents --workspace D:\private-vault-test-run
```

The runner copies files into quarantine and an encrypted local vault; it does not modify or upload
the source folder. Keep private test folders outside the repository and do not commit generated
vaults, backups, or documents.

## Build and Verify the Local Bundle End to End

```powershell
python tests\validate_frozen_build.py
python scripts\build_release_bundle.py
python tests\validate_release_bundle.py
python tests\validate_installer_publishing.py
python tests\validate_portable_install.py
```

The verified bundle is written to
`dist\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe` and the release archive is
written to `release-output\DocumentVaultIngestionEngine-0.1.0-windows-x64.zip`.

For the interactive desktop app:

```powershell
release-output\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe
```

Double-clicking the packaged EXE launches the JurisNuru licensing gate. Activate a valid signed
`license.key` there before the four product tabs open. After activation, the product view contains
only Dashboard, Workspace, Settings, and About; licensing is not a dashboard tab or dashboard panel.

To run the scripted UI workflow and save local screenshots without committing them:

```powershell
python tests\ui_evidence_workflow.py
```

Screenshots are written under `evidence\`, which is ignored by Git.

## Validation

```powershell
ruff check .
ruff format --check .
python tests\validate_docs.py
python tests\validate_license.py
python tests\validate_wakilios_backend.py
python tests\validate_wakilios_api.py
python tests\validate_vault.py
python tests\validate_search.py
python tests\validate_rag.py
python tests\validate_backup.py
python tests\validate_e2e.py
python tests\validate_products.py
python tests\validate_security_scan.py
python main.py --selftest
python main.py --products
```

UI validation (requires PySide6):

```powershell
pip install PySide6
set QT_QPA_PLATFORM=offscreen
python tests\validate_ui.py
```

## Packaging Target

```powershell
pyinstaller main.spec
```

The packaged executable must pass:

```powershell
dist\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --selftest
```

## Obfuscated Production Build (spec §6.3)

Release builds harden the licence check by Cython-compiling `licensing/core.py`
and `licensing/clockguard.py` to native `.pyd`.

```powershell
pip install "cython>=3,<4"
python scripts\obfuscate_licensing.py
python scripts\obfuscate_licensing.py --keep-sources
python scripts\obfuscate_licensing.py --check
```

## Release Bundle

```powershell
python scripts\build_release_bundle.py
python tests\validate_release_bundle.py
```

The release validator verifies the sidecar manifest hash and confirms the bundle does not include
obvious secret, private-key, credential, `.env`, recovery-key, or client-document file names.

## Vendor License Key Generation

1. Generate a key pair offline:

   ```powershell
   python tools\keygen.py
   python tools\keygen.py 2048
   ```

2. Sign a license for a customer's machine:

   ```powershell
   python tools\sign_license.py <installation_id> <firm_name> <plan> <expiry>
   ```

3. The customer places `license.key` next to the executable or in `%APPDATA%\WakiliOS\`.

## Main-Based 29-Document UI Evidence

This branch was verified from `origin/main` at commit `b1123ab`.

```powershell
& .venv\Scripts\python.exe -m PyInstaller main.spec --noconfirm --clean
& .\dist\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --selftest
& .venv\Scripts\python.exe tests\validate_ui.py
& .venv\Scripts\python.exe tests\validate_ocr_runtime.py
& .venv\Scripts\python.exe tests\validate_license.py
& .venv\Scripts\python.exe tests\validate_public_kenyan_e2e.py
& .venv\Scripts\python.exe tests\validate_vault.py
& .venv\Scripts\python.exe tests\validate_backup.py
& .venv\Scripts\python.exe -u tests\run_main_evidence.py
```

The UI runner activates a temporary signed test license, creates a matter, imports and uploads 29
judiciary PDFs one at a time through the visible UI, runs ten RAG questions, and exercises calendar,
backup/restore, admin sync, and audit-log controls. The verified run produced 80 PNG screenshots
under the ignored `evidence\` folder.

The local bundle from the verified fixed build is
`release-output\DocumentVaultIngestionEngine-main-e2e-v1.zip`.

The solo-mode fix in this branch ensures the dialog emits the requested admin session and the main
window owns the single backend instance, preventing `database is locked` on the first New matter
action.

## Clean Machine Acceptance

Before any release, copy the final bundle to a clean Windows VM with no Python and no Visual Studio
installed. Run the portable install smoke test, then run the end-to-end import, vault, backup, and
restore workflow.
