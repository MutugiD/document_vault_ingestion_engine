# Local Matter RAG Connector - Gap Analysis

| Current State | Expected Product Behavior | Missing Implementation | Priority | Validator Needed | Impact |
| --- | --- | --- | --- | --- | --- |
| citation packet exists | user can ask questions in UI | RAG question panel | high | UI/RAG validator | usability |
| OCR-pending scanned docs excluded | scanned evidence becomes searchable after OCR | OCR execution dependency | high | real-world RAG E2E extension | retrieval quality |
| deterministic retrieval works | private field testing can use real docs safely | manual private ingest/RAG runner | high | manual smoke validator | field confidence |
| no hosted generation | hosted AI can use only cited local context | hosted AI boundary | medium | hosted prompt validator | future AI |
| no Wakili sync | Wakili-Mkononi receives approved matter/citation packets | integration payload boundary | medium | integration validator | ecosystem |
| no audit handoff | every AI/sync handoff is auditable | audit event extension | medium | audit validator | compliance |

## Immediate Gap Order

1. OCR execution dependency.
2. Manual private document/RAG runner.
3. Production RAG UI panel.
4. Wakili-Mkononi integration boundary.
5. Hosted AI/LLM boundary.

## Gap Closure Rule

Every RAG implementation PR must prove citation behavior and update this file.
