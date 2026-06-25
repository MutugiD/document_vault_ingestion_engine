# 01 - Architecture End To End

## Layers

```text
PySide6 UI
  -> Worker commands
  -> Intake services
  -> Vault services
  -> SQLite metadata/search
  -> Local Matter RAG Connector
  -> Encrypted object store
  -> Backup/restore services
  -> Managed cloud grant client
```

## One File Flow

1. User drops a file in watched scan folder or imports manually.
2. Intake copies it to quarantine.
3. Intake calculates SHA-256 and validates file signature.
4. Intake extracts text or queues OCR.
5. User confirms matter and document type.
6. Vault encrypts the file bytes.
7. Vault writes metadata, version, and audit event.
8. Search indexes extracted text.
9. Local Matter RAG Connector chunks extracted text and prepares cited retrieval context.
10. Backup health is updated.
11. Quarantine plaintext is deleted after encrypted storage succeeds.

## RAG Flow

1. Extracted text from document versions is chunked locally.
2. Chunks are stored in SQLite with matter/document/version references.
3. Retrieval is scoped to a matter when a matter context is provided.
4. Hybrid retrieval combines lexical matching and deterministic vector-style scoring.
5. Reranking prioritizes answer-bearing, lifecycle-relevant chunks.
6. Output is a cited context packet for a later LLM boundary.

## Backup Flow

1. App creates local encrypted backup package.
2. App verifies manifest and package hash.
3. If cloud backup is enabled, app requests a short-lived provider grant.
4. App uploads encrypted package bytes only.
5. App records local cloud snapshot state.

## Trust Boundary

Legal contents stay local unless explicitly exported, included in encrypted backup packages, or sent through a future user-approved AI generation boundary. Admin sync and cloud metadata never include legal document identifiers, prompts, retrieved context, OCR text, extracted text, or recovery keys.
