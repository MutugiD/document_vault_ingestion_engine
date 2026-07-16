# 25 - WakiliOS Firm Management

F37 revamps the Windows Legal Document Vault into WakiliOS, a multi-seat litigation-focused legal firm management system.

## Purpose

WakiliOS keeps the existing Windows desktop client, encrypted vault, document intake, search, local RAG, hosted AI boundary, backup, and release packaging. It adds a firm-hosted backend so multiple licensed users can work from the same matter records without sharing a raw SQLite file over the network.

## V1 Boundary

- Windows desktop clients connect to a firm-controlled backend over LAN or VPN.
- The backend owns SQLite WAL storage and encrypted vault objects.
- Offline client behavior is a read-only cache.
- Roles are admin, advocate, clerk, accounts, and read-only.
- The matter workspace is litigation-first and contains Summary, Parties, Activities, Lodgings, Court Decisions, Fees, Receipts, and Documents.
- Calendar sync is `.ics` export/feed only.
- Fees and receipts track court costs, filing fees, reimbursements, and attached proof. Client billing, trust accounting, reconciliation, and statements are deferred.

## Backend Contract

The `wakilios` package provides:

- firm initialization with a first admin user;
- PBKDF2-HMAC-SHA256 password hashing with per-user salts;
- signed short-lived session tokens;
- seat-limit enforcement;
- role checks for matter, document, summary, and accounts workflows;
- matter workspace tables for parties, activities, lodgings, decisions, fees, receipts, documents, and summaries;
- encrypted document upload through the existing vault object model;
- AI summary generation only from cited local matter context;
- `.ics` calendar generation from dated activities, lodging due dates, and court decisions;
- audit events for firm, matter, document, summary, fee, receipt, and calendar operations.

The FastAPI boundary lives in `wakilios.api.create_app`. Validators exercise the deterministic service layer directly and keep the HTTP app as the LAN/VPN deployment wrapper.

## Privacy Rules

- Raw passwords are never stored.
- Session tokens are signed and expire.
- Provider keys, recovery material, raw document text, source hashes, and cloud credentials must not appear in audit records.
- AI summaries require local RAG citations and are blocked when cited matter context is unavailable.
- Read-only users may view/cache permitted data but cannot create fees, receipts, documents, summaries, or matter records.

## Validation

Run:

```powershell
python tests\validate_wakilios_backend.py
python main.py --wakilios-backend-e2e
python tests\validate_ui.py
python tests\validate_products.py
python tests\validate_security_scan.py
```

The validator proves:

- multi-user login succeeds;
- seat limits are enforced;
- read-only users are blocked from write actions;
- all matter workspace tabs have persisted records;
- document upload creates encrypted vault/search/RAG records;
- AI summaries preserve citation IDs;
- `.ics` export includes visible matter dates;
- offline cache is read-only;
- audit records exist without raw document text.
