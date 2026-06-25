# 14 - Three Products And RAG Strategy

## Strategy Shift

The product line now publishes three near-term solutions from the same local-first foundation:

1. Windows Legal Document Vault.
2. Document Intake Engine.
3. Local Matter RAG Connector.

Wakili-Mkononi integration, direct Judiciary e-filing automation, hosted AI, and remote provider SDK execution remain later integration layers. The first RAG work is local, citation-first, and matter-scoped.

The machine-readable product catalog is:

- `products/product_catalog.json`
- `products/catalog.py`

`tests/validate_products.py` proves each published product maps to existing modules, validators, documentation, license features, and release artifacts.

## Product 1 - Windows Legal Document Vault

Purpose:

- Own the local encrypted legal-document record.
- Preserve matter, document, version, audit, backup, and restore state.
- Keep local legal documents accessible even when licenses expire or paid features are disabled.

Implemented foundation:

- Signed offline license validation.
- Encrypted object store.
- SQLite metadata.
- Audit ledger.
- Matter/document/version records.
- Local backup and restore.
- Frozen Windows build validation.

## Product 2 - Document Intake Engine

Purpose:

- Move scanner/manual source files into a safe quarantine and validation path.
- Detect supported document types.
- Extract local text where possible.
- Prepare documents for vault custody, search, and RAG.

Implemented foundation:

- Quarantine import.
- File signature detection.
- Duplicate detection.
- PDF/DOCX/image intake records.
- PDF text extraction.
- DOCX text extraction.
- OCR adapter boundary.

## Product 3 - Local Matter RAG Connector

Purpose:

- Let lawyers ask matter-scoped questions over their own local legal documents.
- Retrieve cited local evidence before any generation step.
- Produce a context packet that can be used by a local or hosted LLM only after privacy, licensing, and admin boundaries are satisfied.

F10 implementation boundary:

- `matter_rag` license entitlement.
- Local chunking from extracted document-version text.
- SQLite-backed RAG chunk store.
- Hybrid retrieval pattern:
  - sparse lexical scoring over local text
  - deterministic vector-style hashed scoring
  - reranking with lifecycle-aware boost
- Matter-scoped retrieval.
- Citation-first context packet.
- Safety notice that generation must use only cited local context.

State-of-art direction:

- Use hybrid retrieval rather than vector-only retrieval for legal documents, because exact terms such as case numbers, party names, statute references, invoice numbers, and court stations matter.
- Use reranking after broad retrieval to improve precision before context reaches an LLM.
- Keep citations mandatory and first-class.
- Keep evaluation loops around retrieval quality, faithfulness, citation coverage, and latency.
- Add query classification and query rewriting only after baseline retrieval is measurable.
- Keep embeddings local by default for confidential matters; hosted embeddings must be a paid, consented, logged, and redacted feature.

Research anchors:

- Wang et al., "Searching for Best Practices in Retrieval-Augmented Generation", EMNLP 2024.
- Microsoft Azure Architecture Center, RAG information retrieval guidance, including index/search/reranking considerations.
- LangChain RAG documentation, separating indexing from retrieval/generation.
- OpenAI retrieval and embeddings documentation, for future hosted/vector-store integration boundaries.

## Licensing Boundary

RAG is a paid feature flag named `matter_rag`.

License behavior:

- Active license with `matter_rag=true`: RAG indexing and retrieval features may run.
- Expired or disabled license: paid RAG features stop.
- Local documents, backup restore, and export/recovery remain accessible.

The license check-in must not include prompts, retrieved context, citations, client names, matter names, case numbers, filenames, OCR text, extracted text, or recovery keys.

## Privacy Boundary

F10 RAG is local-only. No RAG text is sent to admin sync or cloud backup metadata.

Allowed local storage:

- chunk IDs
- matter/document/version IDs
- chunk text
- deterministic local vectors
- citation metadata

Forbidden remote metadata:

- prompts
- generated answers
- chunk text
- extracted text
- OCR text
- matter names
- client names
- party names
- case numbers
- filenames
- source hashes
- recovery keys

## Verification

`tests/validate_rag.py` proves:

- `matter_rag` license entitlement activates.
- Local documents can be chunked and indexed.
- Retrieval returns cited matter-scoped context.
- Results are reranked.
- Retrieval does not leak one matter into another when scoped.
- Answer packets contain citations and a local-context safety notice.
