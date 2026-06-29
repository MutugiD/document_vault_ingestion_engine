# 23 - Wakili-Mkononi Integration Boundary

F35 adds the first local integration boundary between the completed local products and Wakili-Mkononi. It does not upload raw legal documents, extracted OCR text, recovery material, provider credentials, or uncontrolled prompts.

## Purpose

The local app already owns the core workflow:

- licensed vault access;
- encrypted document custody;
- document intake and OCR/extraction;
- matter-scoped search;
- Local Matter RAG Connector citations and confidence.

The integration boundary packages only user-approved matter and citation metadata so a later Wakili-Mkononi transport can attach local evidence to another workflow without weakening the local vault privacy model.

## Boundary Rules

- A handoff requires explicit user approval.
- A handoff requires the integration entitlement to be enabled.
- A handoff requires at least one local RAG citation.
- Raw document text remains local.
- RAG `grounded_context` and retrieval chunk text remain local.
- Vault recovery material, cloud credentials, provider API keys, source file hashes, OCR text, extracted text, client names, case numbers, and filenames are not allowed in the handoff payload.
- Every prepared handoff records a local audit event.
- Disabled integration blocks only the handoff; it does not block vault read, local export, restore, search, or local RAG where those local features remain entitled.

## Packet Shape

The validated packet contains:

- `schema_version`;
- `integration`;
- `created_at`;
- `matter.matter_id`;
- allowlisted matter labels: `court`, `station`, `practice_area`, `status`;
- `question_digest`, not the raw question;
- `confidence`;
- citation metadata: citation ID, matter ID, document ID, version ID, title, and chunk index;
- `user_approved`;
- payload notice.

The packet is deliberately a transport-neutral contract. A later HTTP client can send this payload only after the same privacy validator passes.

## Audit Event

The vault records `wakili_mkononi_handoff_prepared` with:

- integration name;
- matter ID;
- citation count;
- confidence;
- question digest.

The audit event does not store raw document text, OCR text, recovery material, cloud credentials, or provider API keys.

## Validation

Run:

```powershell
python tests\validate_wakili_integration.py
python main.py --wakili-mkononi-e2e
python tests\validate_rag.py
python tests\validate_security_scan.py
```

The validator proves:

- approved handoff succeeds;
- missing approval fails;
- disabled entitlement fails;
- local vault access still works after the disabled handoff;
- unsafe payload fields are rejected;
- citation count and confidence are present;
- no grounded RAG context or retrieval results are exported;
- audit event is recorded.
