# End-To-End Validation Plan

Enterprise validation proves the three products work together under realistic
Windows conditions.

## Core Local Flow

Validate:

- first-run setup.
- license activation and status display.
- vault initialization with recovery-key confirmation.
- matter creation.
- PDF, DOCX, image, scanned PDF, duplicate, corrupt file, and unsupported `.doc`
  intake.
- OCR/extraction status and warnings.
- search.
- RAG questions with citations and confidence.
- encrypted backup.
- restore drill.
- local recovery after paid feature disablement.

## Kenyan Public Corpus Flow

Use public Kenyan legal documents only. The downloader stores files under
`test-output/` or another ignored local folder.

Validate:

- source manifest can be downloaded repeatedly.
- hashes are recorded after download.
- generated answers cite the indexed source documents.
- confidence is present and bounded.
- raw document text is not printed in logs.
- backup and restore preserve search/RAG behavior.

## Private Manual Smoke Flow

Private firm files must remain outside the repo. The manual runner may report:

- counts.
- file type categories.
- duplicate status.
- warning categories.
- validator pass/fail.

It must not report:

- raw legal text.
- client names.
- matter names.
- filenames unless the user explicitly runs a local-only verbose mode outside CI.
- hashes in admin/cloud payload simulations.

## Hosted Provider Flow

Validate:

- users can set provider keys locally.
- provider status is redacted.
- no key value appears in logs, backups, or release artifacts.
- hosted AI receives only citation packets.
- no local context means no hosted answer.

