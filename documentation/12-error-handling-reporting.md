# 12 - Error Handling Reporting

## Required Failure Modes

- Invalid license.
- Expired license.
- Disabled cloud backup entitlement.
- Corrupt file.
- Unsupported file.
- OCR failure.
- Duplicate file.
- Low disk space.
- Backup interrupted.
- Cloud upload grant expired.
- Wrong recovery key.

## Reporting Rules

- User messages must be understandable.
- Logs must be redacted.
- Audit events must exist for custody changes.
- No legal text, filenames, case numbers, or recovery keys in logs.

## Verification

Each feature validator must include at least one failure-path scenario once implemented.
