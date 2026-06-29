# 22 - Managed Cloud Backup Boundary

## Purpose

F34 hardens the cloud backup boundary for commercial use while preserving local
document ownership.

The app must never ask lawyers for AWS, Azure, or Google Cloud root credentials.
Instead, the owner backend issues short-lived grants. The Windows app uploads
and downloads encrypted `.wakilibak` packages only.

## In-Scope

- AWS S3 upload/download grant contract.
- Azure Blob upload/download grant contract.
- Google Cloud Storage upload/download grant contract.
- encrypted-package-only upload and download.
- cloud metadata allowlist.
- no long-lived provider credentials on the PC.
- interrupted upload safety.
- clean-machine restore drill from a downloaded encrypted package.
- packaged executable smoke command.

## Out-Of-Scope

- real cloud account provisioning.
- real HTTP upload/download implementation.
- storage lifecycle policies.
- customer billing portal.
- admin web dashboard.

Those belong to the backend platform. F34 defines and validates the local app
boundary.

## Allowed Cloud Metadata

Cloud-visible metadata is limited to:

- installation ID.
- snapshot ID.
- package size.
- package hash.
- created timestamp.
- app version.
- upload status.

Cloud-visible metadata must not include:

- matter names.
- client names.
- case numbers.
- filenames.
- OCR text.
- extracted text.
- prompts.
- source hashes.
- recovery keys.
- cloud credentials.
- provider API keys.

## Grant Contract

Each grant is provider-bound and operation-bound:

- provider: `aws`, `azure`, or `gcp`.
- operation: `upload`, `download`, or `delete`.
- installation ID.
- snapshot ID.
- short expiry.
- provider-specific URL.
- required installation binding header.

Provider-specific grant markers are validated so an AWS grant cannot masquerade
as an Azure or GCP grant.

## Upload Safety

Uploads are staged first and committed only after the encrypted package can be
read and its manifest package hash matches the expected snapshot.

If upload is interrupted:

- the pending upload is aborted.
- no cloud snapshot is listed.
- the last known good snapshot remains available.
- no partial package replaces a committed snapshot.

## Restore Drill

The restore drill:

1. creates an encrypted local backup.
2. uploads it through short-lived grants.
3. downloads the encrypted package through a download grant.
4. restores into a clean workspace with the user-held recovery key.
5. opens the restored vault.
6. verifies the original encrypted vault object is readable after restore.

## Commands

Run the cloud boundary validator:

```powershell
py -3.11 tests\validate_cloud_boundary.py
```

Run the packaged-app style CLI boundary:

```powershell
py -3.11 main.py --managed-cloud-backup-e2e
```

Run related safety checks:

```powershell
py -3.11 tests\validate_backup.py
py -3.11 tests\validate_security_scan.py
py -3.11 tests\validate_frozen_build.py
```

## Acceptance

- AWS, Azure, and GCP grant contracts are validated.
- Upload accepts only encrypted `.wakilibak` packages.
- Download writes only encrypted `.wakilibak` packages.
- Metadata contains only allowlisted fields.
- Nested credential-bearing payloads are rejected.
- Interrupted upload does not create a visible snapshot.
- Interrupted upload does not replace the last known good snapshot.
- Clean-machine restore works from cloud-downloaded encrypted package plus the
  recovery key.
- Frozen executable runs `--managed-cloud-backup-e2e`.
