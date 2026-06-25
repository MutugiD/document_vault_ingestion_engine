# 06 - Matter Document Versioning

## Purpose

Organize documents by matter and preserve version/lifecycle history.

## Matter Fields

- matter ID
- internal reference
- client
- parties
- court
- station
- case number
- practice area
- responsible advocate
- status

## Document Types

- Pleading
- Affidavit
- Witness statement
- Annexure
- Authority
- Application
- Notice
- Order
- Judgment
- Ruling
- Correspondence
- Receipt
- Court output
- Other

## Lifecycle

- Imported
- Draft
- Reviewed
- Approved
- Signed
- Filed
- Served
- Court returned
- Superseded
- Archived

## F5 Implementation Boundary

The first matter/versioning slice implements:

- Matter records.
- Document records linked to matters.
- Immutable document version rows.
- Auto-incrementing version numbers per document.
- Lifecycle status captured on documents and versions.

Protected lifecycle enforcement for filed, served, court-returned, superseded, and archived documents will be expanded in later workflow/UI slices.

## Verification

`tests/validate_search.py` proves immutable version creation by adding multiple versions to the same document and verifying sequential version numbers.
