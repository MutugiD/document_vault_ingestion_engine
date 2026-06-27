# 17 - Windows Distribution Release Checklist

## Purpose

This checklist is the final Windows publishing gate for Kenyan legal practices.

## Release Inputs

- Python 3.11.9 Windows 64-bit build environment.
- Clean git working tree.
- Passing CI on `main`.
- Frozen PyInstaller one-folder bundle.
- Release ZIP and sidecar manifest.
- Bundled `resources/license_public_key.pem`.
- Bundled `resources/public_kenyan_legal_docs.json`.
- No private keys, `.env`, credentials, recovery keys, or sample client documents.

## Build Commands

```powershell
python tests\validate_frozen_build.py
python tests\validate_release_bundle.py
python tests\validate_portable_install.py
```

## Public Kenyan Document Verification

Download public source documents:

```powershell
python scripts\download_public_kenyan_docs.py --output test-output\public-kenyan-documents
```

Run native app E2E:

```powershell
dist\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --public-kenya-e2e test-output\public-kenyan-documents
```

The report must include indexed document count, RAG chunk count, question answers, citations, confidence score per answer, encrypted backup size, and restore verification.

## AI Provider Key Configuration

Provider keys are configured by environment variables or through the app UI:

- `DOCUMENT_VAULT_OPENAI_API_KEY`
- `DOCUMENT_VAULT_ANTHROPIC_API_KEY`
- `DOCUMENT_VAULT_GOOGLE_API_KEY`
- `DOCUMENT_VAULT_AZURE_OPENAI_API_KEY`
- `DOCUMENT_VAULT_MISTRAL_API_KEY`

The status command must print redacted values only:

```powershell
dist\DocumentVaultIngestionEngine\DocumentVaultIngestionEngine.exe --providers
```

## Clean Windows Machine Gate

On a clean Windows machine:

1. Extract `DocumentVaultIngestionEngine-0.1.0-windows-x64.zip`.
2. Run `DocumentVaultIngestionEngine.exe --selftest`.
3. Run `DocumentVaultIngestionEngine.exe --products`.
4. Run `DocumentVaultIngestionEngine.exe --providers`.
5. Run public Kenyan document verification with downloaded public PDFs.
6. Launch `DocumentVaultIngestionEngine.exe --gui`.
7. Confirm setup, license, vault, import/OCR, search/RAG, backup, admin, AI key, and about tabs render.

## Publishing Blockers

Do not publish if any validator fails, release ZIP filenames contain secrets or sample client documents, public Kenyan document E2E cannot build cited RAG answers, provider status prints raw API keys, or the frozen executable fails on a machine without Python installed.
