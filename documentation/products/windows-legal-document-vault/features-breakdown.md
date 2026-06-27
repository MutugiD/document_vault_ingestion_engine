# Windows Legal Document Vault - Features Breakdown

## Implemented

| Feature | Evidence |
| --- | --- |
| installation ID | `tests/validate_license.py` |
| signed offline license | `tests/validate_license.py` |
| feature flags | `tests/validate_license.py` |
| admin/license sync payload boundary | `tests/validate_license.py` |
| admin disablement local-access rule | `tests/validate_license.py` |
| sync grace behavior | `tests/validate_license.py` |
| payment plan entitlement model | `tests/validate_license.py` |
| suspended/expired paid feature behavior | `tests/validate_license.py` |
| admin payment override state | `tests/validate_license.py` |
| encrypted object store | `tests/validate_vault.py` |
| recovery-key unlock | `tests/validate_vault.py` |
| wrong recovery key failure | `tests/validate_vault.py`, `tests/validate_backup.py` |
| audit event ledger | `tests/validate_vault.py` |
| matter/document/version records | `tests/validate_search.py` |
| SQLite FTS5 search | `tests/validate_search.py` |
| encrypted backup package | `tests/validate_backup.py` |
| restore drill | `tests/validate_backup.py`, `tests/validate_e2e.py` |
| managed cloud metadata boundary | `tests/validate_cloud_boundary.py` |
| AWS/Azure/GCP grant upload/download boundary | `tests/validate_cloud_boundary.py` |
| private folder vault smoke | `tests/validate_manual_ingest_smoke.py` |
| PyInstaller frozen executable | `tests/validate_frozen_build.py` |
| checked release ZIP | `tests/validate_release_bundle.py` |
| portable install smoke | `tests/validate_portable_install.py` |
| security scan | `tests/validate_security_scan.py` |

## Partially Implemented

| Feature | Current State | Missing |
| --- | --- | --- |
| UI | PySide6 shell exists | production operator screens |
| cloud backup | provider grant client boundary exists | real hosted backend deployment |
| distribution | one-folder and release ZIP exist | installer wrapper, code signing, clean VM signed report |

## Missing For MVP

| Feature | Validator Needed |
| --- | --- |
| first-run production setup flow | `tests/validate_ui.py` extension |
| license activation UI | `tests/validate_ui.py` extension |
| vault recovery/export UX | UI workflow validator |
| clean Windows VM checklist artifact | package/release validator extension |

## Missing For Commercial Release

| Feature | Validator Needed |
| --- | --- |
| installer wrapper | installer validator |
| code signing | signed artifact validator |
| automatic update channel | signed update manifest validator |
| hosted cloud grant backend deployment | cloud grant backend validator |

## Release Validation Commands

```powershell
python tests\validate_license.py
python tests\validate_vault.py
python tests\validate_search.py
python tests\validate_backup.py
python tests\validate_cloud_boundary.py
python tests\validate_manual_ingest_smoke.py
python tests\validate_frozen_build.py
python tests\validate_release_bundle.py
python tests\validate_portable_install.py
python tests\validate_security_scan.py
```
