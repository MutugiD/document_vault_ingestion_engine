# 25 - WakiliOS Firm Management Gap Analysis

## Architecture Direction

WakiliOS is a single-process desktop application. The UI calls `wakilios.core` directly — no HTTP client, no separate server needed for solo use. For multi-seat firms, the optional `wakilios.api` FastAPI wrapper allows LAN/VPN access to the same core logic.

The `wakilios.client` HTTP module is only needed for multi-seat LAN/VPN mode. Solo users never use it.

## Spec vs Implementation Matrix

| Spec Requirement | Status | Gap |
|---|---|---|
| Firm initialization | DONE | None |
| User/seat/role management (CRUD) | PARTIAL | No deactivate/reactivate, no update role in UI |
| Login with PBKDF2-HMAC-SHA256 | DONE | None |
| Session token signing/verification | DONE | None |
| Seat limit enforcement | DONE | None |
| Matter workspace CRUD | DONE (core+API) | UI needs to call core directly for solo mode |
| MatterParty CRUD | DONE (core+API) | UI needs direct core calls |
| MatterActivity CRUD | DONE (core+API) | UI needs direct core calls |
| Lodging CRUD | DONE (core+API) | UI needs direct core calls |
| CourtDecision CRUD | DONE (core+API) | UI needs direct core calls |
| FeeEntry CRUD | DONE (core+API) | UI needs direct core calls |
| Receipt CRUD | DONE (core+API) | UI needs direct core calls |
| Document upload/download | PARTIAL | Upload in core, needs integration with intake/vault |
| AI summary generation | DONE (core) | Needs integration with rag/ and ai/ |
| Calendar .ics export | DONE (core+API) | None |
| Offline read-only cache | DONE (core) | No UI |
| Audit event tracking | DONE (core) | UI needs audit log viewer |
| Role-aware UI behavior | DONE | UI enables/disables controls based on role |
| Login/auth dialog in UI | DONE | BackendConnectionDialog exists for multi-seat |
| Fee-receipt linking | DONE (core) | UI shows linked_fee_id on receipts |
| Document-receipt proof attachment | MISSING | Schema supports linked_document_id, no UI/flow yet |
| FastAPI test client validation | DONE | TestClient tests pass |
| pyproject.toml dependencies | DONE | Runtime deps declared |
| CI WakiliOS validation | DONE | Steps added to ci.yml |

## UI Integration Gaps

### Solo mode: UI must call wakilios.core directly

The current UI (`app.py`) calls `wakilios.client.WakiliOSClient` for all matter operations. This is wrong for solo mode — the UI should import and call `wakilios.core` directly when running in-process.

**Needed changes:**

1. `MainWindow` should detect solo vs multi-seat mode at startup
2. In solo mode, create a `FirmBackend` instance directly and call its methods
3. In multi-seat mode, use `WakiliOSClient` to talk to the LAN/VPN server
4. Both paths exercise the same business logic (`wakilios.core`)

### Missing solo-mode initialization

- Setup page should initialize a `FirmBackend` for solo use (no server URL needed)
- Login dialog should support local authentication against `FirmBackend`
- Matter operations in solo mode go through `FirmBackend` methods, not HTTP

### Module integration

The UI currently has separate code for intake, search, RAG, and backup that works independently of `wakilios.core`. These need to be connected through the matter workspace:

- **Document tab**: Import files via `intake/` → extract text → store in `vault/` → link to matter in `wakilios.core`
- **Search tab**: Search within current matter scope using `search/`
- **AI Summary tab**: Generate summaries using `rag/` + `ai/` with matter-scoped context
- **Backup tab**: Use existing `backup/` module, also accessible from matter workspace

## Connections/Billing Gaps

### Fee-Receipt Linking
- Schema supports `linked_fee_id` and `linked_document_id` on receipts
- E2E test links receipt to fee correctly
- UI shows linked_fee_id on receipts
- API endpoint returns fees and receipts in workspace response

### Document Proof Attachment
- Receipt `linked_document_id` exists in schema but no UI flow to attach proof
- No download endpoint to retrieve proof documents
- Needs integration: receipt → document upload → link document_id to receipt

### Calendar Export
- `.ics` export wired to API endpoint and UI button
- Works in both solo and multi-seat modes

## PR Plan (Revised)

### PR1: feature/f37-wakilios-backend-gaps [MERGED]
- Add all missing API endpoints to wakilios/api.py
- Add Pydantic request/response models for all endpoints
- Add FastAPI TestClient validation test
- Fix pyproject.toml dependencies
- Add CI WakiliOS validation steps

### PR2: feature/f37-wakilios-ui-gaps [OPEN - needs rework]
Current state: Has separate HTTP client (`wakilios/client.py`) and login dialog.
Needs rework: UI must call `wakilios.core` directly for solo mode, keep `wakilios.client` as optional for multi-seat.

Rework plan:
- Add `FirmBackend` direct-call path in `MainWindow`
- Solo mode: no server URL, login against local `FirmBackend`
- Multi-seat mode: existing `BackendConnectionDialog` + `WakiliOSClient`
- Both modes share the same UI and workspace tabs
- Keep role-aware controls, audit log viewer, document upload

### PR3: feature/f37-wakilios-connections-billing [OPEN - needs rework]
Current state: Has fee-receipt linking, document upload, audit log viewer.
Needs rework: Wire these through the existing module stack (intake → vault → search → RAG) instead of only through the HTTP client.

Rework plan:
- Document upload in UI calls `intake.import_document()` → `vault.store()` → link to matter
- AI summary generation calls `rag.build_answer_packet()` → `ai.providers` with matter context
- Fee-receipt display refreshes from `FirmBackend.workspace()` in solo mode
- Audit log viewer reads from `FirmBackend.audit_events()` directly

### PR4: feature/f37-wakilios-cicd-testing
- Ensure full functional test pass on Python 3.11
- Add solo-mode integration test (UI → core directly, no HTTP)
- Keep API validation test for multi-seat mode
- Fix any remaining integration issues