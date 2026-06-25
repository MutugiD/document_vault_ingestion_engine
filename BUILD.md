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
python main.py --selftest
```

## Packaging Target

The first production packaging target is a PyInstaller one-folder bundle:

```powershell
pyinstaller main.spec
```

The packaged executable must later pass:

```powershell
dist\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --selftest
```

## Bundle Rules

The bundle must include:

- Application executable.
- Python runtime pieces collected by PyInstaller.
- PySide6 runtime files once UI begins.
- Tesseract executable and traineddata once OCR begins.
- License public key.
- JSON/schema files.

The bundle must not include:

- Vendor private signing keys.
- Cloud provider long-lived credentials.
- Real client documents.
- Real client logs.
- `.env` files.
- Plaintext sample matters.

## Clean Machine Acceptance

Before any release, copy the final bundle to a clean Windows VM with no Python and no Visual Studio installed. Run the frozen `--selftest`, then run the end-to-end import, vault, backup, and restore workflow.
