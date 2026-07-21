# Windows Build Guide

This guide defines the local Windows build target for WakiliOS.

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
one valid scanned/image-only PDF, and one legacy `.doc` file:

```powershell
python scripts\manual_ingest_smoke.py --input D:\private-vault-test-documents --workspace D:\private-vault-test-run
```

The runner copies files into quarantine and an encrypted local vault; it does not modify or upload
the source folder. Keep private test folders outside the repository and do not commit generated
vaults, backups, or documents.

## Build and Verify the Local Bundle End to End

The following sequence creates the Windows one-folder executable, runs its frozen smoke suite,
creates the release ZIP, and verifies a portable extraction:

```powershell
python tests\validate_frozen_build.py
python scripts\build_release_bundle.py
python tests\validate_release_bundle.py
python tests\validate_installer_publishing.py
python tests\validate_portable_install.py
```

The verified bundle is written to
`dist\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe` and the release archive is
written to `release-output\DocumentVaultIngestionEngine-0.1.0-windows-x64.zip`. The adjacent
`release-output\DocumentVaultIngestionEngine\` folder is refreshed from the same build, so the
EXE in that folder and the EXE inside the ZIP are identical.

For the interactive desktop app:

```powershell
release-output\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe
```

Double-clicking the packaged EXE launches the License screen. Activate a valid signed `license.key`
there before Dashboard, Workspace, or Settings become available. The Dashboard contains setup and
vault controls only; license activation is kept on the License screen.

To run the scripted UI workflow and save 23 local screenshots without committing them:

```powershell
python tests\ui_evidence_workflow.py
```

Screenshots are written under `evidence\`, which is ignored by Git.

Use the Dashboard/Workspace import controls to add documents one at a time. The application keeps
the original source file in place, copies it to intake quarantine, extracts text locally, indexes
the matter, and stores encrypted vault objects. Configure a real private-document folder only when
you are ready to test with client data.

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

The first production packaging target is a PyInstaller one-folder bundle:

```powershell
pyinstaller main.spec
```

The packaged executable must pass:

```powershell
dist\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --selftest
```

The automated frozen-build validator runs the same path:

```powershell
python tests\validate_frozen_build.py
```

## Obfuscated Production Build (spec §6.3)

Release builds harden the licence check by Cython-compiling `licensing/core.py`
and `licensing/clockguard.py` to native `.pyd`. The hard-coded RSA public key
(spec §6.2) is baked into `core.pyd`, closing the key-substitution bypass.

Needs `cython` + a C compiler on the host:

```powershell
pip install "cython>=3,<4"
python scripts\obfuscate_licensing.py              # compile + strip sources (release)
python scripts\obfuscate_licensing.py --keep-sources  # compile but keep .py (inspect)
python scripts\obfuscate_licensing.py --check         # verify Cython + compiler available
```

## Release Bundle

After the frozen build passes, create the checked release ZIP and sidecar manifest:

```powershell
python scripts\build_release_bundle.py
```

The release validator creates the same ZIP under `release-output/`, verifies the
sidecar manifest hash, confirms the three product definitions are present, and
checks that the bundle does not include obvious secret, private-key, credential,
`.env`, recovery-key, or client-document file names:

```powershell
python tests\validate_release_bundle.py
```

## Vendor License Key Generation

1. **Generate key pair** (run once, offline):

   ```powershell
   python tools\keygen.py            # 4096-bit (production)
   python tools\keygen.py 2048       # 2048-bit (testing)
   ```

   Writes `licensing/public_key.pem` (bundled, hard-coded in `core.py`) and
   `_vendor/private_key.pem` (never committed or bundled).

2. **Sign a license** for a customer's machine:

   ```powershell
   python tools\sign_license.py <installation_id> <firm_name> <plan> <expiry>
   # plan: solo, pro, enterprise
   # expiry: YYYY-MM-DD
   ```

   The customer's `installation_id` comes from running `WakiliOS.exe --selftest`
   or from their `%APPDATA%\WakiliOS\settings\installation.json`.

3. The customer places the `license.key` file next to `WakiliOS.exe` or in
   `%APPDATA%\WakiliOS\`.

## Clean Machine Acceptance

Before any release, copy the final bundle to a clean Windows VM with no Python
and no Visual Studio installed. Run the portable install smoke test, then run
the end-to-end import, vault, backup, and restore workflow.
