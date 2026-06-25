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

## Verification

`tests/validate_search.py` will prove matter-scoped results and rebuild behavior.
