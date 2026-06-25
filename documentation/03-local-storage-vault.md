# 03 - Local Storage Vault

## Purpose

Store legal documents locally as encrypted immutable objects, with SQLite metadata and an audit ledger.

## Inputs

- Confirmed intake payload.
- Matter assignment.
- Document type.
- User/recovery-key context.

## Outputs

- Encrypted object.
- Document row.
- Version row.
- Audit event.
- Search indexing request.

## Storage Shape

```text
vault/
  vault.sqlite
  objects/
  search/
  quarantine/
  backups/
  restore-workspaces/
  logs/
```

## Rules

- Raw recovery key is never stored.
- Document bytes use AES-GCM.
- Each object has a unique nonce.
- Filed/served/court-returned versions are never overwritten.
- Failed metadata writes must not leave untracked plaintext.

## F2 Implementation Boundary

The first implementation slice creates the local custody core:

- Vault folder initialization.
- SQLite database creation.
- `vault_config`, `vault_objects`, and `audit_events` tables.
- PBKDF2-HMAC-SHA256 recovery-key derivation.
- AES-GCM encrypted immutable object writes.
- Object reads only after recovery-key verification.
- Wrong recovery key failure before object access.
- Audit entries for initialization and object storage.

Matter records, document lifecycle statuses, version chains, and search indexing are delivered in later feature slices.

## Verification

`tests/validate_vault.py` proves:

- Vault folders and SQLite metadata are created.
- Encrypted object bytes do not contain plaintext.
- Correct recovery key can read an object after reopening the vault.
- Wrong recovery key fails safely.
- Missing object reads fail safely.
- Audit ledger records initialization and object storage.
