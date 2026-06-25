# 09 - Backup Restore Cloud

## Purpose

Make recovery a first-class feature, not an afterthought.

## Local Backup

Backup packages include:

- encrypted vault objects
- metadata backup
- audit ledger
- manifest
- package hash
- app version
- schema version

## Restore Drill

Restore drill must:

- decrypt locally
- verify hashes
- verify manifest
- verify metadata readability
- write restore report
- avoid touching live vault

## F6 Implementation Boundary

The first backup slice implements:

- Local `.wakilibak` package creation.
- ZIP payload of vault metadata and encrypted object files.
- AES-GCM encryption of the payload using a recovery-key-derived backup key.
- Non-sensitive manifest containing installation ID, snapshot ID, hashes, schema version, app version, timestamp, and size.
- Restore into a separate restore workspace.
- Wrong recovery key failure before extraction.
- Restored metadata readability check.
- Restore report generation.

Managed cloud upload grants remain in F7. The F6 package is already encrypted and is the only object F7 is allowed to upload.

## Managed Cloud Backup

Cloud backup uses vendor-managed AWS/GCP/Azure storage through short-lived grants. The desktop app never stores long-lived cloud provider credentials.

Allowed cloud metadata:

- installation ID
- snapshot ID
- package size
- package hash
- app version
- created timestamp
- upload status

Forbidden cloud metadata:

- matter names
- client names
- case numbers
- filenames
- OCR text
- extracted text
- recovery keys

## F7 Implementation Boundary

The managed cloud boundary implements:

- Provider-neutral grant model for AWS, Azure, and GCP targets.
- Short-lived upload/download grant representation.
- Encrypted `.wakilibak` package-only upload boundary.
- Cloud-visible metadata allowlist.
- Rejection of matter names, client names, case numbers, filenames, OCR text, extracted text, source hashes, recovery keys, and cloud credential fields.
- Snapshot list/delete boundary through the owner backend abstraction.

This slice does not call AWS, Azure, or GCP SDKs directly. The desktop app remains dependent on your backend to issue grants and broker provider storage.

## Verification

`tests/validate_backup.py` proves:

- Backup package is created with a manifest.
- Package bytes do not expose sample legal text, client names, or case numbers.
- Wrong recovery key cannot restore the package.
- Correct recovery key restores into a clean directory.
- Restored vault metadata is readable.
- Restored encrypted objects can be unlocked with the recovery key.

`tests/validate_cloud_boundary.py` will prove F7 metadata safety for managed uploads.
`tests/validate_cloud_boundary.py` proves:

- Upload boundary accepts encrypted backup packages.
- Cloud metadata contains only allowlisted fields.
- Client/case metadata is rejected.
- Long-lived cloud credential fields are rejected.
- Non-`.wakilibak` package upload is rejected.
- Snapshot listing and deletion stay inside the owner backend boundary.
