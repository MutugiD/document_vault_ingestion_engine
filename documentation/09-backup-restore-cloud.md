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

## Verification

`tests/validate_backup.py` and `tests/validate_cloud_boundary.py` will prove restore and metadata safety.
