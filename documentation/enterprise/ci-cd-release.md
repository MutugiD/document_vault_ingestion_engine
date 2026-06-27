# CI/CD And Release Gates

CI runs on pull requests and pushes to `main` and `feature/**`. The workflow must
continue to run all completed validators as the enterprise roadmap advances.

## PR Gate

Every feature PR must include:

- documentation updates.
- implementation or validator changes.
- local validation notes in the PR description.
- no real client documents or secrets.
- CI passing before merge.

The feature branch must be merged before the next feature branch starts.

## Required Enterprise Gate

Before any enterprise release is published, run:

```powershell
python tests\validate_docs.py
python tests\validate_skeleton.py
python tests\validate_products.py
python tests\validate_security_scan.py
python tests\validate_license.py
python tests\validate_vault.py
python tests\validate_intake.py
python tests\validate_extraction.py
python tests\validate_ocr_runtime.py
python tests\validate_search.py
python tests\validate_rag.py
python tests\validate_backup.py
python tests\validate_cloud_boundary.py
python tests\validate_ui.py
python tests\validate_package.py
python tests\validate_e2e.py
python tests\validate_native_workflow.py
python tests\validate_real_world_rag_e2e.py
python tests\validate_public_kenyan_e2e.py
python tests\validate_manual_ingest_smoke.py
python tests\validate_ai_providers.py
python tests\validate_frozen_build.py
python tests\validate_release_bundle.py
python tests\validate_portable_install.py
python tests\validate_installer_publishing.py
python main.py --selftest
ruff check .
```

## Release Artifact Rules

- Release ZIPs must include a manifest and checksums.
- Frozen builds must run `--selftest`.
- Portable installs must launch without relying on a system Python installation.
- Installer artifacts must be signed before publication.
- Unsigned or tampered update manifests must be rejected.
- CI logs must not print raw document text, provider keys, recovery keys, cloud
  credentials, or private signing material.

## Failure Handling

- A failing validator blocks merge.
- A security scan failure blocks merge and release.
- A packaging failure blocks distribution but does not change local data access.
- A cloud or hosted AI outage must degrade to local vault/search/RAG behavior when
  local entitlements permit it.
