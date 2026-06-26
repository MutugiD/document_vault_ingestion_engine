# Windows Build Guide

This guide defines the local Windows build target for Document Vault Ingestion Engine.

## Baseline

- Windows 10/11, 64-bit.
- Python 3.11.9, 64-bit.
- Visual Studio Build Tools 2022 with Desktop development with C++ workload.
- PyInstaller one-folder build.
- End-user machines must not need Python, Visual Studio, or a compiler.

## Developer Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip wheel setuptools
pip install -r requirements-dev.txt
```

## Validation

```powershell
python tests\validate_docs.py
python tests\validate_skeleton.py
python tests\validate_license.py
python tests\validate_vault.py
python tests\validate_intake.py
python tests\validate_extraction.py
python tests\validate_search.py
python tests\validate_backup.py
python tests\validate_cloud_boundary.py
python tests\validate_ui.py
python tests\validate_package.py
python main.py --selftest
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

## Release Bundle

After the frozen build passes, create the checked release ZIP and sidecar manifest:

```powershell
python scripts\build_release_bundle.py
```

The release validator creates the same ZIP under `release-output/`, verifies the sidecar manifest hash, confirms the three product definitions are present, and checks that the bundle does not include obvious secret, private-key, credential, `.env`, recovery-key, or client-document file names:

```powershell
python tests\validate_release_bundle.py
```

## Portable Install Smoke

After the release bundle is created, extract it to an isolated local folder and run the frozen executable from that extracted location:

```powershell
python scripts\portable_install_smoke.py
```

The automated validator runs the same path and checks both `--selftest` and `--products` from the extracted release folder:

```powershell
python tests\validate_portable_install.py
```

## Bundle Rules

The bundle must include:

- Application executable.
- Python runtime pieces collected by PyInstaller.
- PySide6 runtime files once UI begins.
- Tesseract executable and traineddata once OCR packaging begins.
- License public key.
- JSON/schema files.
- `products/product_catalog.json`.
- embedded `release-manifest.json`.

The bundle must not include:

- Vendor private signing keys.
- Cloud provider long-lived credentials.
- Real client documents.
- Real client logs.
- `.env` files.
- Plaintext sample matters.

## Clean Machine Acceptance

Before any release, copy the final bundle to a clean Windows VM with no Python and no Visual Studio installed. Run the portable install smoke test, then run the end-to-end import, vault, backup, and restore workflow.
