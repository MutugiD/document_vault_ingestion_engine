# 25 - WakiliOS Firm Management

F37 revamps the Windows Legal Document Vault into WakiliOS, a multi-seat litigation-focused legal firm management system.

## Product Vision

WakiliOS is a firm-controlled litigation management product that preserves the existing Windows desktop legal vault experience while adding a shared backend layer for matters, documents, activities, fees, receipts, and audit history. The product is designed for law firms that need multiple licensed users to work from the same matter data set without relying on a fragile shared SQLite database file.

The first release is intentionally narrow:

- Windows desktop clients remain the primary user interface.
- The backend is firm-hosted on LAN/VPN, not public cloud.
- Offline mode is read-only cache only, avoiding first-release conflict resolution.
- Calendar integration is local `.ics` export/feed instead of live Outlook/Google sync.
- Financial tracking covers court costs, filing fees, reimbursements, receipts, and proof attachments only.
- Client billing, trust accounting, reconciliation, and statement generation are deferred to later releases.

## What changed in this repo

This repository now includes a WakiliOS product vertical slice with three core components:

1. `wakilios/` backend service layer
2. `wakilios/api.py` FastAPI LAN/VPN HTTP wrapper
3. `ui/app.py` rebranded PySide Windows desktop shell with a matter workspace

Additional support files were updated so the product is discoverable, validated, and packaged with the existing engineering discipline.

## What is preserved from the original product

WakiliOS builds on the existing foundation instead of replacing it:

- encrypted document vault and custody model
- document intake and validation pipeline
- local search and RAG indexing
- hosted-AI boundary and citation-aware summary controls
- backup/restore, packaging, and Windows build validation
- security and privacy audit controls

## Architecture

### Client / server split

- Desktop clients remain PySide6 Windows applications.
- They connect to the firm backend over LAN/VPN.
- The backend owns the authoritative SQLite WAL store and encrypted vault objects.
- Documents are uploaded and downloaded through authenticated service endpoints.
- Offline clients keep a read-only cache of matter data to support disconnected review.

### Firm-hosted backend

The `wakilios` package provides a deterministic service layer for:

- firm initialization
- user/seat/role management
- matter workspace CRUD
- document upload/download/versioning through the vault
- AI-assisted summary generation
- `.ics` calendar export
- audit event tracking

The HTTP wrapper in `wakilios.api.create_app` is a deployment boundary for LAN/VPN access. The core service layer remains testable without the web transport.

### Key entities

- `FirmUser`, `Seat`, `Role`, `MatterAssignment`
- `Matter` expanded with internal reference, practice area, court, case number, responsible advocate, filing status/date, and summary fields
- `MatterParty` with contact details, role, representative, and notes
- `MatterActivity` with activity type, title, date/time, court/session details, status, notes, linked documents, and calendar visibility
- `Lodging` for docketed filings, due date, lodged date, filing status, linked document, and filing reference
- `CourtDecision` for judgments, orders, rulings, outcome, and linked order document
- `FeeEntry` for court costs, filing fees, amount, currency, payer/payee, status, and matter linkage
- `Receipt` with receipt number, issuer, payer, amount, date, linked fee, and proof document
- `DocumentSummary` capturing manual summary text, AI draft text, approval state, citation IDs, and generated-by metadata

## UI and role behavior

The desktop shell is rebranded as WakiliOS and introduces a litigation matter workspace in place of the old simple Matters page.

Workspace tabs include:

- Summary
- Parties
- Activities
- Lodgings
- Court Decisions
- Fees
- Receipts
- Documents

Role-aware behavior is defined as:

- Admin: manage users, seats, firm settings, and audit visibility.
- Advocate: manage matters, decisions, activities, and summaries.
- Clerk/Paralegal: manage lodgings, documents, and activities.
- Accounts: manage fees and receipts.
- Read-only: view/export permitted matters.

## AI summaries and privacy boundary

WakiliOS uses the existing hosted AI boundary and privacy model. Summary generation is gated by:

- local matter RAG context only
- citation IDs attached to source documents
- audit records for summary generation events
- blocking summary generation when no cited context exists

This avoids inventing a second AI path and keeps the new product aligned with the repo's hosted-AI privacy controls.

## Calendar export

V1 supports calendar integration through `.ics` export or feed generation only. Dated matter events include:

- activities with calendar visibility enabled
- applications and filing deadlines
- document lodging due dates
- court decision dates

Live sync with Outlook, Google, or other hosted calendars is explicitly deferred.

## Security and privacy rules

- Passwords are hashed with PBKDF2-HMAC-SHA256 and per-user salt.
- Short-lived signed session tokens are used, not raw passwords or API keys in logs.
- Document text, provider keys, recovery material, and cloud credentials are excluded from audit records.
- AI summary metadata stores citation references but not raw source text.
- Seat limits are enforced at the backend to prevent license overuse.

## Validation and current state

The current implementation state in this repo is:

- `wakilios` backend package implemented and validated.
- FastAPI backend wrapper implemented.
- WakiliOS UI shell rebranded and added matter workspace layout.
- Backend service validators written and passing.
- UI validation updated for WakiliOS branding and matter workspace controls.

The next integration step is wiring the Windows desktop client to authenticate against the backend API and consume the service endpoints.

### Run validation

```powershell
python tests\validate_wakilios_backend.py
python main.py --wakilios-backend-e2e
python tests\validate_ui.py
python tests\validate_products.py
python tests\validate_security_scan.py
```

### Notes for reviewers

- The product is intentionally litigation-first, not a full general-practice management engine.
- Multi-seat is implemented as a backend-hosted service, not a shared SQLite workstation file.
- Offline mode is intentionally read-only for V1.
- Court costs and receipts are tracked; invoicing and trust accounting are deferred.
- `.ics` export is the only calendar integration in this release.
