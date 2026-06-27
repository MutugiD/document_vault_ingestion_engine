# Windows Distribution Plan

The enterprise distribution target is a Windows 64-bit application that Kenyan
lawyers can install or run without a local Python setup.

## Baseline

- Python 3.11.x build environment.
- PySide6 desktop UI.
- PyInstaller one-folder bundle.
- Release ZIP with manifest and checksums.
- Portable install smoke test.
- Later installer wrapper with shortcuts and uninstall path.

## Bundle Contents

The frozen bundle must include:

- application entrypoint.
- product catalog.
- license public key.
- public Kenyan document source manifest.
- OCR runtime manifest and bundled OCR files when enabled.
- required Python runtime files and app dependencies.

The frozen bundle must not include:

- private keys.
- `.env` files.
- cloud credentials.
- provider API keys.
- sample client documents.
- plaintext vault data.
- local test-output folders.

## Publishing Path

1. Build and validate the one-folder PyInstaller bundle.
2. Build release ZIP and sidecar manifest.
3. Run portable install smoke test.
4. Wrap in installer.
5. Sign installer and release ZIP.
6. Verify signatures and checksums.
7. Run clean Windows VM test.
8. Publish versioned artifacts and release notes.

## Clean Windows Acceptance

A clean Windows machine must be able to:

- install or extract the release.
- launch the app.
- run `--selftest`.
- activate or load an offline license.
- initialize a vault.
- import documents.
- search and ask cited RAG questions.
- create and restore encrypted backups.
- show redacted provider status.

