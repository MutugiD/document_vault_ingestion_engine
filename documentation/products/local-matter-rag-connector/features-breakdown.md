# Local Matter RAG Connector - Features Breakdown

## Implemented

| Feature | Evidence |
| --- | --- |
| local chunking | `tests/validate_rag.py` |
| matter-scoped retrieval | `tests/validate_rag.py` |
| deterministic vector-style scoring | `tests/validate_rag.py` |
| sparse lexical scoring | `tests/validate_rag.py` |
| lifecycle-aware reranking | `tests/validate_rag.py` |
| citation packet | `tests/validate_rag.py` |
| safety notice | `tests/validate_rag.py` |
| real-world grounded questions | `tests/validate_real_world_rag_e2e.py` |
| scanned pending-OCR behavior without runtime | `tests/validate_real_world_rag_e2e.py` |
| scanned OCR text retrieval when engine exists | `tests/validate_real_world_rag_e2e.py` |
| private folder RAG smoke | `tests/validate_manual_ingest_smoke.py` |

## Partially Implemented

| Feature | Current State | Missing |
| --- | --- | --- |
| answer generation | citation packet exists | local/hosted generation boundary |
| semantic retrieval | deterministic scoring exists | real embeddings or local model path |
| UI | no production RAG panel | question panel with citations |
| OCR input quality | scanned OCR text can feed RAG | vetted bundled Tesseract binary |

## Missing For MVP

| Feature | Validator Needed |
| --- | --- |
| RAG question UI | UI workflow validator |
| RAG index rebuild controls | RAG/search validator extension |
| improved no-context behavior in UI | UI/RAG validator |

## Missing For Commercial Release

| Feature | Validator Needed |
| --- | --- |
| Wakili-Mkononi integration boundary | integration payload privacy validator |
| hosted AI/LLM boundary | hosted prompt privacy validator |
| citation-required generation | hosted AI validator |
| tenant/license entitlement check | entitlement validator |
| audit events for sync/AI handoff | audit validator |

## Release Validation Commands

```powershell
python tests\validate_rag.py
python tests\validate_e2e.py
python tests\validate_real_world_rag_e2e.py
python tests\validate_manual_ingest_smoke.py
python tests\validate_security_scan.py
```
