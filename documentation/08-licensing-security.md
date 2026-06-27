# 08 - Licensing And Security

## Purpose

Support commercial licensing without weakening local data ownership.

## Model

- Signed offline license.
- RSA-PSS/SHA-256 verification.
- Periodic online sync for entitlement state.
- Feature flags for paid modules such as cloud backup and matter RAG.
- Privacy-allowlisted admin check-in payloads.
- Local grace behavior from the last successful owner-backend sync.

## License Fields

- installation ID
- license ID
- firm display name
- plan
- features
- expiry
- issued at
- signature

## Forbidden Sync Data

- Matter names.
- Client names.
- Case numbers.
- Document filenames.
- OCR text.
- Extracted text.
- Document hashes.
- Prompts.
- Retrieved RAG context.
- Recovery keys.
- Local paths.

## Admin Check-In Payload

The Windows app may send only:

- installation ID
- license ID
- app version
- device nickname
- license status
- paid entitlement state
- feature flags
- coarse backup health
- generated timestamp

The backend response may enable, disable, suspend, or expire paid/admin features. Disablement stops paid and online features, but does not delete documents and does not block local recovery/export of already-owned legal data.

## Verification

`tests/validate_license.py` proves:

- A valid signed license activates paid feature flags.
- A valid signed license can activate `matter_rag`.
- A tampered license fails signature validation.
- A license bound to another installation fails safely.
- An expired license disables paid features but still allows local data access.
- A disabled installation disables paid features but still allows local data access.
- The admin check-in payload excludes matter, client, case, filename, OCR, prompt, hash, and recovery-key fields.
- Owner-backend disablement stops paid/online features without blocking local data access.
- A grace-expired sync state stops paid/online features while preserving local document access.

`main.py --selftest` also checks that installation identity persistence works in packaged-app style temporary storage.
