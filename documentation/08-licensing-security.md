# 08 - Licensing And Security

## Purpose

Support commercial licensing without weakening local data ownership.

## Model

- Signed offline license.
- RSA-PSS/SHA-256 verification.
- Periodic online sync for entitlement state.
- Feature flags for paid modules such as cloud backup.

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
- Recovery keys.
- Local paths.

## Verification

`tests/validate_license.py` will prove valid, tampered, expired, and disabled license behavior.
