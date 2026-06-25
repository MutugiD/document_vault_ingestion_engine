# 08 - Licensing And Security

## Purpose

Support commercial licensing without weakening local data ownership.

## Model

- Signed offline license.
- RSA-PSS/SHA-256 verification.
- Periodic online sync for entitlement state.
- Feature flags for paid modules such as cloud backup and matter RAG.

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

## Verification

`tests/validate_license.py` proves:

- A valid signed license activates paid feature flags.
- A valid signed license can activate `matter_rag`.
- A tampered license fails signature validation.
- A license bound to another installation fails safely.
- An expired license disables paid features but still allows local data access.
- A disabled installation disables paid features but still allows local data access.

`main.py --selftest` also checks that installation identity persistence works in packaged-app style temporary storage.
