# Releasing WakiliOS

Releases are built and published automatically by `.github/workflows/release.yml` when a version tag is pushed. Each release ships one self-contained Windows bundle built (and licence-obfuscated) on a clean `windows-latest` runner.

## Artifacts

| Asset | Notes |
|-------|-------|
| `WakiliOS-vX.Y.Z-win64.zip` | The one-folder app. Ships with licence modules Cython-compiled to `.pyd` with the hard-coded public key baked in. Includes WakiliOS solo mode, multi-seat backend, RAG, vault, and all litigation management features. |
| `WakiliOS-vX.Y.Z-win64.zip.sha256` | SHA256 checksum sidecar. |

Self-contained — unzip and run `WakiliOS.exe` (no Python required).

## Cutting a release

1. Bump the version in **`ui/__init__.py`** (`APP_VERSION`) and `pyproject.toml`; commit on `main`.
2. Tag and push:
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```
3. The workflow verifies the tag matches `ui.APP_VERSION`, obfuscates the licence modules, builds the bundle, **gates on `--selftest`**, and publishes a GitHub Release with the zip + `.sha256` + auto-generated notes.

The tag is the single trigger; the workflow needs only the repo's default `GITHUB_TOKEN` (`contents: write`). No secrets required.

## Local dry-run (no GitHub Release)

Build + package a bundle exactly as CI does, to validate the packaging step:

```powershell
# From a fresh checkout
python scripts\obfuscate_licensing.py --check   # verify Cython + compiler
python scripts\obfuscate_licensing.py             # compile licensing to .pyd
pyinstaller main.spec --noconfirm --clean
dist\WakiliOS\WakiliOS.exe --selftest            # should print: SELFTEST PASS
```

## Obfuscated production build (licensing hardening, free — no PyArmor)

Release builds harden the licence check (spec §6.3) by default: both the local build and the GitHub `release.yml` workflow Cython-compile `licensing/` to native `.pyd` before packaging, so the shipped bundle carries no licence `.py`/`.pyc` and the §6.2 hard-coded public key lives inside `core.pyd`.

Needs `cython` + a C compiler on the host (see `BUILD.md`). Use `--keep-sources` to inspect without removing:

```powershell
# On a FRESH checkout (obfuscation strips licensing .py sources), e.g.
git clone https://github.com/MutugiD/document_vault_ingestion_engine.git rel && cd rel
python scripts\obfuscate_licensing.py --keep-sources   # compile but keep .py for inspection
python scripts\obfuscate_licensing.py                   # compile and remove .py (release)
```

The resulting bundle ships compiled `licensing\*.pyd` (no licence `.py`/`.pyc`); the RSA private key is never involved.

## Verifying a download

```powershell
Get-FileHash -Algorithm SHA256 WakiliOS-v0.1.0-win64.zip
# compare against the .sha256 file
.\WakiliOS\WakiliOS.exe --selftest   # should print: SELFTEST PASS
```

## Vendor license key generation

1. **Generate key pair** (run once, offline):
   ```bash
   python tools/keygen.py
   ```
   Writes `licensing/public_key.pem` (bundled) and `_vendor/private_key.pem` (kept by vendor only, never committed).

2. **Sign a license** for a customer's machine:
   ```bash
   python tools/sign_license.py <machine_hash> <expiry YYYY-MM-DD> [plan] [output_file]
   ```
   The machine hash comes from the customer running `WakiliOS.exe --selftest` or from the installation identity JSON.

3. The customer places the `license.key` file next to `WakiliOS.exe` or in their `%APPDATA%\WakiliOS\` directory.