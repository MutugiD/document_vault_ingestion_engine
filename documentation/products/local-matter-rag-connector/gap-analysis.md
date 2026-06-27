# Local Matter RAG Connector - Gap Analysis

| Current State | Expected Product Behavior | Missing Implementation | Priority | Validator Needed | Impact |
| --- | --- | --- | --- | --- | --- |
| citation packet exists | user can ask questions in UI | RAG question panel | high | UI/RAG validator | usability |
| OCR-fed scanned docs can be retrieved | scanned evidence becomes searchable with bundled runtime | vetted Tesseract binary provenance | high | release/portable validator extension | retrieval quality |
| manual private RAG runner exists | private field testing can use real docs safely | add operator-facing RAG report after real private runs | medium | `tests/validate_manual_ingest_smoke.py` | field confidence |
| no hosted generation | hosted AI can use only cited local context | hosted AI boundary | medium | hosted prompt validator | future AI |
| no Wakili sync | Wakili-Mkononi receives approved matter/citation packets | integration payload boundary | medium | integration validator | ecosystem |
| no audit handoff | every AI/sync handoff is auditable | audit event extension | medium | audit validator | compliance |

## Immediate Gap Order

1. Vetted Tesseract binary provenance.
2. Production RAG UI panel.
3. Operator-facing RAG report after private smoke runs.
4. Wakili-Mkononi integration boundary.
5. Hosted AI/LLM boundary.

## Gap Closure Rule

Every RAG implementation PR must prove citation behavior and update this file.
