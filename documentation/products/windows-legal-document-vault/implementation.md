# Windows Legal Document Vault - Implementation Plan

## Target

Make the vault commercially ready as the secure local foundation for all products.

## PR Sequence

| Feature | Branch | Scope |
| --- | --- | --- |
| F22 | `feature/f22-admin-license-sync-boundary-v1` | Complete: check-in payload, privacy boundary, admin enable/disable, grace behavior |
| F24 | `feature/f24-payment-entitlements-v1` | Complete: plans, suspended/expired/active states, local recovery allowed |
| F25 | `feature/f25-production-windows-ui-v1` | first-run, license, vault, matter, search, backup, restore screens |
| F23 | `feature/f23-managed-cloud-grant-backend-v1` | Complete: provider-neutral grant client and backend-facing contract |
| F27 | `feature/f27-installer-code-signing-publishing-v1` | installer wrapper, signing guide, clean VM report |
| F28 | `feature/f28-automatic-update-channel-v1` | signed update manifest, offline-safe checks |

## Acceptance Gate

```powershell
python tests\validate_license.py
python tests\validate_vault.py
python tests\validate_search.py
python tests\validate_backup.py
python tests\validate_cloud_boundary.py
python tests\validate_manual_ingest_smoke.py
python tests\validate_ui.py
python tests\validate_package.py
python tests\validate_frozen_build.py
python tests\validate_release_bundle.py
python tests\validate_portable_install.py
python tests\validate_security_scan.py
```

## Packaging Gate

Commercial packaging must pass:

```powershell
python tests\validate_frozen_build.py
python tests\validate_release_bundle.py
python tests\validate_portable_install.py
```

The publishing artifact remains:

```text
release-output/DocumentVaultIngestionEngine-0.1.0-windows-x64.zip
```
