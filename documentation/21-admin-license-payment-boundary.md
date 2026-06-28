# 21 - Admin, License, And Payment Boundary

## Purpose

F33 turns the earlier licensing primitives into one enterprise boundary for
commercial control without exposing legal documents.

The boundary answers one local question:

```text
Given the offline license, last admin sync state, and payment entitlement state,
which features are enabled right now, and can the user still export or restore
their local legal data?
```

## In-Scope

- privacy-safe installation check-in payload.
- owner-backend license sync response parsing.
- payment entitlement response parsing.
- persisted last-known sync and payment state.
- final local feature decision.
- active, disabled, suspended, expired, missing-payment, and tampered-license
  behavior.
- UI Admin tab status check.
- packaged-app CLI smoke command.

## Out-Of-Scope

- hosted admin web dashboard implementation.
- real payment provider integration.
- real HTTP client credentials.
- document upload.
- matter metadata upload.
- RAG prompt or OCR text upload.

Those are later product boundaries. F33 only defines the local app side of the
contract.

## Safe Check-In Fields

The app may send:

- schema version.
- installation ID.
- license ID.
- app version.
- device nickname.
- license status.
- paid entitlement state.
- feature flags.
- coarse backup health.
- generated timestamp.

The app must not send:

- matter names.
- client names.
- case numbers.
- filenames.
- OCR text.
- extracted text.
- document hashes.
- prompts.
- retrieved RAG context.
- recovery keys.
- provider API keys.
- cloud credentials.

## Backend Response Fields

The owner backend may return:

- installation status: `active`, `disabled`, `suspended`, or `expired`.
- paid entitlement state.
- enabled feature list.
- server time.
- grace expiry.
- reason.
- payment plan.
- payment status.
- admin override.

Unsafe extra fields are rejected at parse time.

## Local Decision Rules

- Active license plus active admin sync plus active payment enables only the
  intersection of license, admin, and payment features.
- Admin-disabled installs stop paid and online features.
- Suspended or expired payment stops paid and online features.
- Missing payment state stops paid and online features until sync succeeds.
- Local export and local restore remain allowed for valid disabled or expired
  local licenses.
- Tampered or bad-signature licenses do not allow local export or restore.
- Hosted AI remains disabled until the later hosted AI boundary explicitly
  enables it.

## Commands

Run the validator:

```powershell
py -3.11 tests\validate_admin_license_payment_boundary.py
```

Run the packaged-app style CLI boundary:

```powershell
py -3.11 main.py --admin-license-payment-e2e
```

Run the related safety checks:

```powershell
py -3.11 tests\validate_license.py
py -3.11 tests\validate_security_scan.py
py -3.11 tests\validate_ui.py
```

## Acceptance

- The check-in payload has only allowlisted fields.
- Unsafe backend response fields are rejected.
- Unsafe payment entitlement fields are rejected.
- Active payment enables cloud backup and Local Matter RAG when licensed.
- Hosted AI remains disabled.
- Admin disablement stops cloud backup and RAG.
- Suspended and expired payment stop cloud backup and RAG.
- Local export and restore remain allowed when payment/admin status is invalid
  but the offline license still permits local data access.
- Tampered license blocks local export and restore.
- UI Admin tab reports the boundary decision without exposing secrets.
