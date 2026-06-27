# Local Matter RAG Connector - Implementation Plan

## Target

Keep local RAG reliable before adding any hosted AI or Wakili-Mkononi integration.

## PR Sequence

| Feature | Branch | Scope |
| --- | --- | --- |
| F20 | `feature/f20-ocr-execution-v1` | Complete: scanned document text availability for RAG |
| F21 | `feature/f21-manual-private-document-test-runner-v1` | Complete: private document RAG smoke path |
| F25 | `feature/f25-production-windows-ui-v1` | RAG question panel and citations |
| F29 | `feature/f29-wakili-mkononi-integration-v1` | matter export and citation packet handoff |
| F30 | `feature/f30-hosted-ai-llm-boundary-v1` | cited-context-only hosted AI boundary |

## Acceptance Gate

```powershell
python tests\validate_rag.py
python tests\validate_e2e.py
python tests\validate_real_world_rag_e2e.py
python tests\validate_manual_ingest_smoke.py
python tests\validate_security_scan.py
```

## Hosted AI Gate

Hosted AI cannot ship unless:

- no local context means no answer
- citations are required
- prompt payload excludes recovery keys and credentials
- audit events record every handoff
- entitlement checks pass

## Wakili-Mkononi Gate

Wakili-Mkononi integration cannot ship unless:

- sync is user-approved
- raw uncontrolled uploads are blocked
- citation packets are preserved
- disabled entitlement blocks sync but not local vault access
