# 25 - WakiliOS Firm Management Gap Analysis

## Spec vs Implementation Matrix

| Spec Requirement | Status | Gap |
|---|---|---|
| Firm initialization | DONE | None |
| User/seat/role management (CRUD) | PARTIAL | No deactivate/reactivate user, no list users, no update role API endpoints |
| Login with PBKDF2-HMAC-SHA256 | DONE | None |
| Session token signing/verification | DONE | None |
| Seat limit enforcement | DONE | None |
| Matter workspace CRUD | PARTIAL | No update/delete matter, no matter list endpoint |
| MatterParty CRUD | DONE (core) | No API endpoint |
| MatterActivity CRUD | DONE (core) | No API endpoint |
| Lodging CRUD | DONE (core) | No API endpoint |
| CourtDecision CRUD | DONE (core) | No API endpoint |
| FeeEntry CRUD | DONE (core) | No API endpoint |
| Receipt CRUD | DONE (core) | No API endpoint |
| Document upload/download | PARTIAL | Upload in core, no download endpoint, no API endpoints |
| AI summary generation | DONE (core) | No API endpoint beyond the one existing |
| Calendar .ics export | DONE (core+API) | None |
| Offline read-only cache | DONE (core) | No API endpoint, no UI |
| Audit event tracking | DONE (core) | No API endpoint |
| Role-aware UI behavior | MISSING | UI has static role label, no dynamic role enforcement |
| Login/auth dialog in UI | MISSING | UI has no login screen, no backend connection |
| Backend API client in UI | MISSING | UI has no HTTP client to talk to FastAPI backend |
| Fee-receipt linking in e2e test | DONE | None |
| Document-receipt proof attachment | MISSING | Receipt linked_document_id exists in schema but e2e never tests file attachment |
| FastAPI test client validation | MISSING | No test exercising API endpoints via HTTP (only core layer tested) |
| pyproject.toml dependencies | MISSING | No runtime deps declared in pyproject.toml (requirements.txt has them but not installable) |
| CI WakiliOS validation | MISSING | ci.yml has no WakiliOS backend validation step |
| Python version pin | BUG | requires-python ">=3.11,<3.12" blocks 3.12, but no 3.11 CI install |

## Backend API Gaps

### Missing API Endpoints (wakilios/api.py)
The FastAPI app only has 6 endpoints:
- GET /health
- POST /auth/login
- POST /matters (create only)
- GET /matters/{id}/workspace
- POST /matters/{id}/activities
- POST /matters/{id}/summaries
- GET /matters/{id}/calendar.ics

Missing endpoints that the spec and core.py support:
1. **GET /matters** - List all matters for user
2. **GET /matters/{id}** - Get single matter
3. **PUT /matters/{id}/summary** - Update matter summary
4. **POST /matters/{id}/parties** - Add party
5. **GET /matters/{id}/parties** - List parties
6. **POST /matters/{id}/lodgings** - Add lodging
7. **POST /matters/{id}/court-decisions** - Add court decision
8. **POST /matters/{id}/fees** - Add fee
9. **POST /matters/{id}/receipts** - Add receipt
10. **POST /matters/{id}/documents** - Upload document
11. **GET /matters/{id}/documents/{doc_id}** - Download document
12. **POST /users** - Create user (exists in core, no API)
13. **GET /users** - List users (missing entirely)
14. **GET /audit** - View audit log (missing)
15. **GET /offline-cache** - Build offline cache (missing)

### Schema Validation Gaps
- No Pydantic response models for any endpoint
- No request models for parties, lodgings, court decisions, fees, receipts, documents
- File upload uses multipart - no UploadFile schema

## UI Gaps

### Missing Login/Auth Flow
- No login dialog or screen
- No backend URL configuration
- No session token storage
- No logout/re-auth flow

### Missing Matter Workspace CRUD
- Workspace tabs are read-only list widgets with placeholder text
- No "Add" button wiring to backend API calls
- No form dialogs for creating parties, activities, lodgings, etc.
- No document upload/download in workspace

### Missing Role-Aware Behavior
- UI shows static "Role: advocate" label
- No dynamic role-based enable/disable of controls
- Admin tab doesn't show user management or audit log

### Missing Backend Client
- No HTTP client module for calling FastAPI endpoints
- No connection configuration (host, port, auth)
- No offline cache UI

## Connections/Billing Gaps

### Fee-Receipt Linking
- Schema supports linked_fee_id and linked_document_id on receipts
- E2E test links receipt to fee correctly
- BUT: No UI to view linked fees/receipts
- No API endpoint to retrieve fees/receipts for a matter independently

### Document Proof Attachment
- Receipt proof attachment (linked_document_id) exists in schema
- No endpoint or UI to attach proof documents
- No download endpoint to retrieve proof

### Calendar Export
- API has .ics endpoint
- UI has "Export calendar" button that doesn't call the API

## CI/CD Gaps

### Missing from ci.yml
- No `python tests\validate_wakilios_backend.py` step
- No `python main.py --wakilios-backend-e2e` step
- Python 3.11 pin is correct but pyproject.toml version range blocks 3.12+

### Dependencies
- requirements.txt has fastapi, uvicorn, pydantic but pyproject.toml has NO [project.dependencies]
- Package is not pip-installable with dependencies
- requirements-dev.txt doesn't include httpx (needed for FastAPI TestClient)

## PR Plan

### PR1: feature/f37-wakilios-backend-gaps
- Add all missing API endpoints to wakilios/api.py
- Add Pydantic request/response models for all endpoints
- Add httpx to requirements-dev.txt
- Add FastAPI TestClient validation test
- Fix pyproject.toml dependencies
- Expand validate_wakilios_backend.py with API-level tests

### PR2: feature/f37-wakilios-ui-gaps
- Add backend API client module (wakilios/client.py)
- Add login dialog to UI
- Wire matter workspace tabs to backend API
- Add role-aware UI behavior
- Add offline cache UI indicator

### PR3: feature/f37-wakilios-connections-billing
- Wire fee-receipt linking in UI
- Wire document upload/download in workspace
- Wire .ics calendar export button to API
- Add audit log viewer tab in admin
- Add proof document attachment for receipts

### PR4: feature/f37-wakilios-cicd-testing
- Add WakiliOS validation steps to ci.yml
- Add wakilios-backend-e2e CLI step to ci.yml
- Ensure full functional test pass on Python 3.11
- Fix any remaining integration issues