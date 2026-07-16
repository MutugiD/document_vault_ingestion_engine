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
dist\WakiliOS\WakiliOS.exe --selftest
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