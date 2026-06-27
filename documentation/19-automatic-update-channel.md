# 19 - Automatic Update Channel

## Purpose

The automatic update channel lets the application detect available releases
without accepting unsigned manifests or forcing silent updates.

## V1 Boundary

F31 implements the signed manifest verification boundary only. It does not
silently download, install, or replace the application.

Required behavior:

- update manifests are signed with RSA-PSS/SHA-256.
- unsigned or tampered manifests are rejected.
- manifests must require user approval.
- update checks compare semantic versions.
- update checks select the Windows x64 artifact.
- offline update checks return an offline result and the app continues.
- no vault data, provider keys, recovery keys, cloud credentials, or document
  metadata are sent to the update channel.

## Manifest Fields

- `app_name`.
- `channel`.
- `latest_version`.
- `published_at`.
- `requires_user_approval`.
- `artifacts`.
- `signature`.

Each artifact includes:

- `platform`.
- `url`.
- `sha256`.
- `size_bytes`.

## Validation

```powershell
python tests\validate_update_channel.py
python tests\validate_security_scan.py
python main.py --selftest
```

## Release Rules

- No unsigned update is accepted.
- No silent forced update is accepted.
- Download and install remain explicit future boundaries.
- If the update server is unavailable, local vault, intake, search, RAG, backup,
  restore, and export continue normally.
