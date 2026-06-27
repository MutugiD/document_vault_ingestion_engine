# Document Intake Engine - Gap Analysis

| Current State | Expected Product Behavior | Missing Implementation | Priority | Validator Needed | Impact |
| --- | --- | --- | --- | --- | --- |
| OCR manifest validates | OCR executes locally | Tesseract execution adapter | high | extraction/OCR validator | scanned documents |
| scanned PDF is OCR-pending | scanned PDF text becomes searchable with OCR runtime | image extraction from PDF pages and OCR fallback | high | real-world RAG E2E extension | search/RAG quality |
| generated fixtures test intake | user can test private local files safely | manual private ingest runner | high | manual smoke validator | field testing |
| intake records exist | operator can review imports | production review UI | high | UI workflow validator | usability |
| duplicate detection exists | duplicate warning is visible before vault handoff | UI duplicate warning | medium | UI workflow validator | operator safety |
| Tesseract contract exists | Tesseract binary ships with provenance | bundle inclusion and manifest validation | medium | release bundle validator | distribution |
| legacy `.doc` rejected | commercial app explains unsupported legacy docs | user-facing warning and optional converter plan | low | intake/UI validator | support clarity |

## Immediate Gap Order

1. OCR execution and Tesseract bundling.
2. Manual private document test runner.
3. Operator review UI.
4. Watched-folder daemon.
5. OCR clean-machine release validation.

## Gap Closure Rule

Every intake implementation PR must update this file and the relevant validator command list.
