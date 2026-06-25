# 11 - Packaging Distribution

## Purpose

Ship a Windows bundle that runs without Python installed.

## Target

PyInstaller one-folder build through `main.spec`.

## Bundle Includes

- app executable
- Python runtime files
- PySide6 runtime files once UI begins
- Tesseract binaries once OCR begins
- license public key
- schema/config templates

## Bundle Excludes

- private signing keys
- cloud provider credentials
- real legal documents
- real logs
- `.env` files

## Verification

`tests/validate_package.py` and frozen `--selftest` will validate packaging behavior.
