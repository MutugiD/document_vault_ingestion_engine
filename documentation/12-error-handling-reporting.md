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

## F16 Security Scan Boundary

The security scan slice adds a local CI gate for source and release hygiene:

- private-key block detection
- AWS access-key shape detection
- Azure connection-string shape detection
- Google service-account private-key shape detection
- recovery-key assignment shape detection
- forbidden release filename detection for `.env`, credential, private-key, recovery-key, secret, and client-document markers

The scan is intentionally local and deterministic. It does not upload source, release artifacts, logs, or legal documents to a third-party scanner.

## Verification

Each feature validator must include at least one failure-path scenario once implemented.
