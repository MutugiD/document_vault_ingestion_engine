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

## Verification

`tests/validate_vault.py` will prove encrypted objects are unreadable as plaintext and wrong recovery keys fail safely.
