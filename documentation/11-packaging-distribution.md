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

## F8 Implementation Boundary

The first packaging slice implements:

- PyInstaller one-folder `main.spec` validation.
- `DocumentVaultIngestionEngine` bundle name.
- Windowed bundle configuration with `console=False`.
- Packaged-app `main.py --selftest` smoke path.
- PyInstaller availability check in CI.

## F9 Implementation Boundary

The frozen-build hardening slice implements:

- Real PyInstaller one-folder build on Windows.
- Frozen executable existence check.
- `_internal` runtime folder existence check.
- Frozen `DocumentVaultIngestionEngine.exe --selftest` exit-code validation.
- `strip=False` in `main.spec` to avoid GNU strip warnings on Windows.

Installer wrapping, code signing, bundled Tesseract, and clean-machine smoke testing are later distribution hardening slices.

## Verification

`tests/validate_package.py` checks the spec, confirms no private/secret/credential terms are embedded in packaging config, runs `main.py --selftest`, and verifies PyInstaller is callable.

`tests/validate_frozen_build.py` performs the full local one-folder PyInstaller build and runs the frozen executable selftest.
