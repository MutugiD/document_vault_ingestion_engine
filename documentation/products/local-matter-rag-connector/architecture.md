# Local Matter RAG Connector - Architecture

## Purpose

Local Matter RAG Connector builds citation-first local retrieval over matter document versions. It prepares grounded context for future AI drafting without uploading matter documents.

## Module Boundaries

| Module | Responsibility |
| --- | --- |
| `rag` | chunking, local vector-style scoring, reranking, citation packets |
| `search` | matter/document/version source rows and FTS5 search |
| `licensing` | `matter_rag` entitlement |
| `intake` | upstream extraction and OCR text availability |
| `vault` | encrypted source object custody |
| `backup` | encrypted backup of local text/index state through vault files |
| `ui` | future RAG question panel |

## Data Flow

```text
document version extracted text
  -> matter-scoped chunks
  -> local sparse/vector-style retrieval
  -> lifecycle-aware reranking
  -> citation packet
  -> future local/hosted generation boundary
```

## Local Storage

RAG chunks live in local SQLite tables and are derived from document-version extracted text.

Rules:

- no retrieval outside requested matter when `matter_id` is supplied
- no answer packet without citations
- OCR-pending scanned documents are excluded until text exists
- context is local only

## Licensing And Entitlements

Requires `matter_rag`.

Future paid states:

- disabled RAG blocks new RAG operations
- local vault/export/recovery remains available
- hosted AI requires a separate entitlement

## Security And Privacy

RAG must not send raw text to hosted services until the hosted AI boundary is explicitly implemented. Future hosted prompts must use cited context only and must exclude recovery keys, credentials, and non-allowlisted metadata.

## Backup And Cloud Boundary

RAG state is local. If included in backup, it must be inside the encrypted backup payload only.

## Windows Packaging

PyInstaller bundle must include:

- `rag` module
- `search` module
- product catalog
- validators in CI

No hosted AI credentials may be bundled.

## Validators

```powershell
python tests\validate_rag.py
python tests\validate_e2e.py
python tests\validate_real_world_rag_e2e.py
python tests\validate_security_scan.py
```
