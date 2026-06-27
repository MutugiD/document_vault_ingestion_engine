# Commercial Operations

Commercial readiness adds monetization and support controls without compromising
local document ownership.

## Admin And Licensing

The owner admin system may:

- issue signed licenses.
- enable or disable installations.
- sync paid feature flags.
- view coarse backup health.
- view app version and device nickname.

The owner admin system must not:

- read client documents.
- read matter metadata.
- read OCR text.
- receive recovery keys.
- receive provider API keys.
- receive cloud provider root credentials from client PCs.

## Payment Entitlements

Plans control paid features such as managed cloud backup, hosted AI, update
channels, and external integrations.

Required states:

- active.
- suspended.
- expired.
- admin disabled.
- grace period.

Local vault access, export, and restore remain available in every state.

## Managed Cloud Backup

Cloud backup is managed through owner-issued short-lived grants:

- AWS S3.
- Azure Blob Storage.
- Google Cloud Storage.

Client PCs upload only encrypted backup packages. Cloud-visible metadata is
limited to installation ID, snapshot ID, package size, package hash, created
timestamp, app version, and upload status.

## Support And Incident Response

Support tooling may request:

- app version.
- installation ID.
- license status.
- validation command output with redactions.
- backup health state.

Support tooling must not request client documents, recovery keys, provider keys,
cloud credentials, or raw OCR/search/RAG text.

## Enterprise Completion Standard

The enterprise version is publishable only when a clean Windows machine can
install or extract the package, activate a license, initialize a vault, ingest
public Kenyan documents and private local test files, extract/OCR text, search,
ask cited RAG questions with confidence, configure provider keys, run backup and
restore, enforce entitlements, and verify signed distributable artifacts.

