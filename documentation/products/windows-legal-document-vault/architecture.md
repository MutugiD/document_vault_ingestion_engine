# Windows Legal Document Vault - Architecture

## Purpose

Windows Legal Document Vault is the licensed local encrypted custody layer for legal documents, matter records, document versions, audit events, local search, backup, restore, release packaging, and commercial entitlement enforcement.

## Module Boundaries

| Module | Responsibility |
| --- | --- |
| `licensing` | installation ID, signed offline license, feature flags, future sync boundary |
| `vault` | encrypted object store, vault config, recovery-key unlock, audit ledger |
| `search` | matter records, document records, document versions, SQLite FTS5 search |
| `backup` | encrypted local backup, restore drill, managed cloud metadata/grant boundary |
| `ui` | PySide6 shell and worker-thread boundary |
| `release` | release ZIP, sidecar manifest, portable install smoke |
| `security_checks` | source and release secret-shape scanning |

## Data Flow

```text
licensed install
  -> vault initialization
  -> encrypted object writes
  -> matter/document/version metadata
  -> local search index
  -> encrypted backup package
  -> managed cloud grant boundary
  -> restore workspace
  -> release ZIP and portable install smoke
```

## Local Storage

Vault root:

```text
vault.sqlite
objects/
quarantine/
search/
backups/
restore-workspaces/
logs/
```

Rules:

- object bytes are AES-GCM encrypted
- metadata lives in SQLite
- recovery key is user-held
- audit events record custody changes
- local documents remain recoverable even if paid online features are disabled

## Licensing And Entitlements

Current:

- signed offline license
- installation ID binding
- expiry validation
- feature flags for `document_intake`, `cloud_backup`, `managed_restore`, and `matter_rag`

Commercial target:

- online license sync
- admin enable/disable state
- paid entitlement state
- grace behavior
- admin override without local document lockout

## Security And Privacy

The vault must not expose:

- raw legal documents in logs
- recovery keys
- private signing keys
- cloud provider credentials
- client names, matter names, case numbers, filenames, OCR text, or source hashes in cloud metadata

## Backup And Cloud Boundary

Backups are local encrypted `.wakilibak` packages. Cloud upload is allowed only through short-lived provider grants and encrypted packages.

Supported target providers in the roadmap:

- AWS S3
- Azure Blob
- Google Cloud Storage

## Windows Packaging

Required release path:

```powershell
python tests\validate_frozen_build.py
python tests\validate_release_bundle.py
python tests\validate_portable_install.py
```

PyInstaller bundle must include:

- `DocumentVaultIngestionEngine.exe`
- Python runtime collected by PyInstaller
- product catalog JSON
- license public key material
- release manifest
- runtime files required by enabled products

PyInstaller bundle must exclude:

- private keys
- `.env`
- cloud credentials
- real client documents
- real logs

## Validators

```powershell
python tests\validate_license.py
python tests\validate_vault.py
python tests\validate_search.py
python tests\validate_backup.py
python tests\validate_cloud_boundary.py
python tests\validate_ui.py
python tests\validate_package.py
python tests\validate_frozen_build.py
python tests\validate_release_bundle.py
python tests\validate_portable_install.py
python tests\validate_security_scan.py
```
