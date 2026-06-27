# Security And Compliance Rules

The enterprise version handles legal documents, so privacy and recovery guarantees
are product requirements rather than implementation details.

## Non-Negotiable Rules

- No real client documents in git, CI, release artifacts, test fixtures, logs, or
  screenshots.
- No private signing keys, provider API keys, cloud root credentials, `.env`
  secrets, or recovery keys in git or release artifacts.
- No plaintext legal documents in cloud storage.
- No admin access to matter content.
- No hidden telemetry.
- No direct court e-filing automation until explicitly designed and validated.

## License And Admin Boundary

Allowed check-in fields:

- installation ID.
- license ID.
- app version.
- device nickname.
- feature flags.
- entitlement state.
- coarse backup health.

Disallowed check-in fields:

- matter names.
- client names.
- case numbers.
- filenames.
- OCR text.
- prompts.
- file hashes.
- recovery keys.
- provider API keys.

## Vault And Backup

- Vault documents are immutable encrypted objects.
- SQLite metadata and local extracted text are included only in encrypted backup
  packages.
- Wrong recovery key must fail safely.
- Interrupted upload must not replace the last known good backup snapshot.
- Admin or backend operators cannot decrypt backup packages.

## Hosted AI Boundary

- Hosted AI may use only user-approved local citation packets.
- No answer may be produced without local context.
- Every answer must include citations and confidence.
- Provider keys must be stored locally, redacted in UI/CLI output, and excluded
  from backups unless a future explicit encrypted-settings export is designed.

