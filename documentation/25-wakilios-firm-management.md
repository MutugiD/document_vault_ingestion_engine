# 25 - WakiliOS Firm Management

F37 evolves the Windows Legal Document Vault into WakiliOS, a litigation-focused legal firm management system.

## Product Vision

WakiliOS is a single-process desktop application where the UI calls Python modules directly — no separate server needed. The `wakilios.core` module provides the firm backend (users, seats, roles, matters, fees, receipts, audit) and the UI calls it in-process. For multi-seat firms, an optional FastAPI wrapper (`wakilios.api`) allows multiple desktop clients to connect over LAN/VPN.

The first release is intentionally narrow:

- Windows desktop is the primary interface.
- Solo mode runs entirely in-process with no server.
- Multi-seat mode uses an optional LAN/VPN FastAPI server.
- Offline mode is read-only cache only.
- Calendar integration is local `.ics` export/feed.
- Financial tracking covers court costs, filing fees, reimbursements, receipts, and proof attachments only.
- Client billing, trust accounting, reconciliation, and statement generation are deferred.

## Architecture

### Solo Mode (default)

The UI calls `wakilios.core` directly in-process. No server needed. The user clicks
"Start Solo" on the Dashboard, which initializes a local `WakiliOSBackend` with
SQLite storage in their app data directory.

### Multi-Seat Mode

For firms with 2–5 advocates sharing matters, the optional FastAPI server
(`wakilios.api`) runs on one machine and other desktops connect via
`WakiliOSClient` (urllib-based, no extra HTTP deps for Windows).

### UI Tabs

| Tab | Contents |
| --- | --- |
| **Dashboard** | BackendConnectionDialog (Start Solo / Connect), Firm setup, License activation, Vault initialization |
| **Workspace** | Matter list + 8 sub-tabs (Summary, Parties, Activities, Lodgings, Court Decisions, Fees, Receipts, Documents) |
| **Settings** | Document Import, Search & RAG, AI Keys, Backup/Restore, Admin & Audit Log |
| **About** | Module cards, release info, native workflow button |

### In-process (solo mode)

The desktop app runs as a single process. The UI (`ui/app.py`) calls `wakilios.core` directly:

```
WakiliOS UI (app.py)
  │
  ├── Firm setup → wakilios.core (FirmBackend, users, seats, roles)
  ├── Login → wakilios.core (authenticate, session token)
  ├── Matters → wakilios.core (CRUD, parties, activities, lodgings, decisions)
  ├── Fees/Receipts → wakilios.core (fee entries, receipts, linked_fee_id)
  ├── Documents → intake/ → vault/ (import, extract, encrypt, store)
  ├── Search → search/ (FTS5 matter-scoped search)
  ├── RAG → rag/ (citation-first retrieval)
  ├── AI Summaries → ai/ (hosted providers, boundary-checked)
  ├── Calendar → wakilios.core (ICS export)
  ├── Backup → backup/ (encrypted backup/restore)
  └── Audit → wakilios.core (audit event log)
```

No HTTP calls, no client module, no serialization overhead. The UI imports and calls Python functions directly.

### LAN/VPN mode (multi-seat)

For firms with multiple seats, the same `wakilios.core` module runs behind a FastAPI wrapper:

```
Firm Server (wakilios.api)
  │
  └── wakilios.core (authoritative data store)

Desktop Client 1 ──HTTP──→ Firm Server
Desktop Client 2 ──HTTP──→ Firm Server
Desktop Client 3 ──HTTP──→ Firm Server
```

The `wakilios.client` module handles HTTP communication for multi-seat mode only. Solo users never need it.

### Key design principle

The `wakilios.core` module is the single source of truth. It is called:
- **Directly** by the UI in solo mode
- **Via FastAPI** by the client module in multi-seat mode

Both paths exercise the same business logic. The API wrapper is a thin transport layer, not a separate service with its own logic.

## Key entities

- `FirmUser`, `Seat`, `Role`, `MatterAssignment`
- `Matter` expanded with internal reference, practice area, court, case number, responsible advocate, filing status/date, and summary fields
- `MatterParty` with contact details, role, representative, and notes
- `MatterActivity` with activity type, title, date/time, court/session details, status, notes, linked documents, and calendar visibility
- `Lodging` for docketed filings, due date, lodged date, filing status, linked document, and filing reference
- `CourtDecision` for judgments, orders, rulings, outcome, and linked order document
- `FeeEntry` for court costs, filing fees, amount, currency, payer/payee, status, and matter linkage
- `Receipt` with receipt number, issuer, payer, amount, date, linked fee, and proof document

## UI and role behavior

The desktop shell is branded WakiliOS with a litigation matter workspace. Workspace tabs include:

- Summary
- Parties
- Activities
- Lodgings
- Court Decisions
- Fees
- Receipts
- Documents

Role-aware behavior:

- Admin: manage users, seats, firm settings, and audit visibility.
- Advocate: manage matters, decisions, activities, and summaries.
- Clerk/Paralegal: manage lodgings, documents, and activities.
- Accounts: manage fees and receipts.
- Read-only: view/export permitted matters.

## How existing modules integrate

WakiliOS does NOT duplicate functionality that already exists in the repo:

- **Document intake**: `intake/` handles import, quarantine, duplicate detection. WakiliOS calls it.
- **Text extraction**: `intake/extraction.py` handles PDF/DOCX/image extraction. WakiliOS calls it.
- **Encrypted vault**: `vault/` handles encrypted storage and recovery keys. WakiliOS calls it.
- **Search**: `search/` provides FTS5 matter-scoped search. WakiliOS calls it.
- **RAG**: `rag/` provides citation-first retrieval. WakiliOS calls it.
- **AI summaries**: `ai/` provides hosted AI boundary-checked calls. WakiliOS calls it.
- **Backup**: `backup/` handles encrypted backup/restore. WakiliOS calls it.
- **Licensing**: `licensing/` handles offline license validation. WakiliOS calls it.

The `wakilios.core` module owns matter-specific logic (users, seats, matters, parties, fees, receipts, audit) that has no equivalent elsewhere. Everything else delegates to the existing modules.

## AI summaries and privacy boundary

WakiliOS uses the existing hosted AI boundary and privacy model. Summary generation is gated by:

- local matter RAG context only
- citation IDs attached to source documents
- audit records for summary generation events
- blocking summary generation when no cited context exists

This avoids inventing a second AI path and keeps the product aligned with the repo's hosted-AI privacy controls.

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

- `wakilios.core` backend service layer implemented and validated.
- FastAPI API wrapper implemented (optional multi-seat mode).
- WakiliOS UI shell branded with matter workspace layout.
- Backend service validators passing.
- UI validation passing.
- CI WakiliOS steps added.

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
- In solo mode, the desktop app calls `wakilios.core` directly — no HTTP needed.
- In multi-seat mode, `wakilios.api` is a thin transport wrapper over the same `wakilios.core` logic.
- Offline mode is intentionally read-only for V1.
- Court costs and receipts are tracked; invoicing and trust accounting are deferred.
- `.ics` export is the only calendar integration in this release.