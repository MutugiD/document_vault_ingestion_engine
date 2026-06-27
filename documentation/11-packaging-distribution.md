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
- public Kenyan legal document manifest
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

## F13 Implementation Boundary

The release-bundle slice implements:

- Checked ZIP creation from `dist/DocumentVaultIngestionEngine`.
- Sidecar release manifest with app name, version, platform, product catalog, release files, and SHA-256 hashes.
- Embedded `release-manifest.json` inside the ZIP without self-referential ZIP hash.
- Validation that the release includes `DocumentVaultIngestionEngine.exe`, `_internal/products/product_catalog.json`, and the embedded manifest.
- Guardrails against obvious secret, private-key, credential, `.env`, recovery-key, and client-document file names.
- CI execution of `tests/validate_release_bundle.py` after the frozen build.

Installer wrapping, code signing, bundled Tesseract binary provenance, and clean-machine VM acceptance remain later distribution hardening slices.

## F26 Implementation Boundary

The release-hardening slice implements:

- `resources/license_public_key.pem` inclusion.
- `resources/public_kenyan_legal_docs.json` inclusion.
- Native `--providers` status command with redacted API-key state.
- Native `--public-kenya-e2e` verification command.
- Public Kenyan document downloader for manual/legal-field validation.
- RAG answer confidence in citation packets.
- Windows distribution checklist in `17-windows-distribution-release-checklist.md`.
- Release ZIP validation for required resources and safety boundaries.

Installer wrapping, code signing, automatic updates, Wakili-Mkononi integration, and hosted AI remain later commercial slices.

## F14 Implementation Boundary

The portable-install smoke slice implements:

- Safe extraction of the checked release ZIP into `test-output/portable-install`.
- Path traversal protection before ZIP extraction.
- Frozen executable `--selftest` from the extracted release folder.
- Frozen executable `--products` from the extracted release folder.
- Validation that the three published products survive release ZIP extraction.
- CI execution of `tests/validate_portable_install.py` after release-bundle validation.

Installer wrapping, code signing, bundled Tesseract binary provenance, and clean-machine VM acceptance remain later distribution hardening slices.

## Verification

`tests/validate_package.py` checks the spec, confirms no private/secret/credential terms are embedded in packaging config, runs `main.py --selftest`, and verifies PyInstaller is callable.

`tests/validate_frozen_build.py` performs the full local one-folder PyInstaller build and runs the frozen executable selftest.

`tests/validate_release_bundle.py` creates the checked release ZIP and sidecar manifest, verifies the ZIP hash, confirms the three published products and required resources are present, and checks release file-name safety boundaries.

`tests/validate_portable_install.py` extracts that checked release ZIP to an isolated local folder and runs the frozen executable smoke paths from the extracted install.
