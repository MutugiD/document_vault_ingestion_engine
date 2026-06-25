# 07 - Search Indexing

## Purpose

Support local matter-scoped search over metadata and extracted text.

## Engine

SQLite FTS5 for V1.

## Indexed Fields

- matter label
- document title
- document type
- lifecycle status
- parties
- case number
- extracted text

## Rules

- Search is local.
- Index can be rebuilt from vault metadata and extracted text.
- No search text is sent to admin sync.

## F5 Implementation Boundary

The first search slice implements:

- SQLite FTS5 `search_index` table.
- Indexing of matter metadata, document title, document type, lifecycle status, and extracted text.
- Global search.
- Matter-scoped search.
- Full index rebuild from stored matters, documents, and versions.

OCR retry text updates, ranking tuning, snippets in the UI, and advanced filters are delivered later.

## Verification

`tests/validate_search.py` proves:

- Search returns relevant document versions.
- Search can be scoped to a single matter.
- Results from other matters are excluded when scoped.
- Search index rebuild restores results after clearing the FTS table.
