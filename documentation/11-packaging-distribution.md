# 11 - Packaging Distribution

## Purpose

Ship a Windows bundle that runs without Python installed.

## Target

PyInstaller one-folder build through `main.spec`.

## Bundle Includes

- Application executable (`WakiliOS.exe`, console=False).
- Python runtime files.
- PySide6 runtime files.
- Tesseract binaries once OCR begins.
- License public key (hard-coded in `licensing/core.pyd` after obfuscation).
- `resources/license_public_key.pem` (reference copy, not used at runtime).
- `resources/public_kenyan_legal_docs.json`.
- `ui/wakilios.qss` (dark theme stylesheet).
- `products/product_catalog.json`.
- Embedded `release-manifest.json`.

The Tesseract runtime folder must include a manifest that records:

- provider `tesseract`
- Windows platform `windows-x64`
- `tesseract.exe`
- required `tessdata/<language>.traineddata` files
- SHA-256 and byte size for every OCR runtime file

## Bundle Excludes

- Vendor private signing keys (`_vendor/`).
- Cloud provider long-lived credentials.
- Real client documents.
- Real client logs.
- `.env` files.
- Plaintext sample matters.
- `licensing/core.py` and `licensing/clockguard.py` (replaced by `.pyd` after obfuscation).

## Obfuscated Production Build (spec §6.3)

Before packaging, run the Cython obfuscation script:

```powershell
pip install "cython>=3,<4"
python scripts\obfuscate_licensing.py
```

This compiles `licensing/core.py` and `licensing/clockguard.py` to native `.pyd`
extensions and removes the `.py` source files. The hard-coded RSA public key
(spec §6.2) is now inside `core.pyd` — not readable from a `.pyc`.

Then build:

```powershell
pyinstaller main.spec --noconfirm --clean
```

## Vendor License Key Generation

See [BUILD.md](../BUILD.md) for the full keygen and license signing workflow.

## Portable Install Smoke

After the release bundle is created, extract it to an isolated local folder
and run the frozen executable from that extracted location:

```powershell
python scripts\portable_install_smoke.py
```

The automated validator runs the same path and checks both `--selftest` and
`--products` from the extracted release folder:

```powershell
python tests\validate_portable_install.py
```