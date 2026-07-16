# 08 - Licensing And Security

## Purpose

Support commercial licensing without weakening local data ownership.

## Model

- Signed offline license (RSA-PSS/SHA-256).
- **Hard-coded RSA public key** (spec §6.2): The public key is compiled into
  `licensing/core.py` as a bytes literal, not read from a swappable file. In
  release builds, Cython compiles this module to `licensing/core.pyd`, so the
  key lives in native machine code. This closes the key-substitution bypass — an
  attacker can no longer replace a loose `public_key.pem` on disk to self-sign
  licenses; forging one still requires the vendor private key.
- **Clock-rollback guard** (spec §6.2): `licensing/clockguard.py` stores a
  monotonic "last seen" UTC timestamp. If the system clock is earlier than the
  stored value, the app locks. NTP cross-check catches clocks set far behind
  real time. Degrades gracefully when NTP is unreachable.
- **Cython obfuscation** (spec §6.3): `scripts/obfuscate_licensing.py` compiles
  `licensing/core.py` and `licensing/clockguard.py` to `.pyd`. The shipped
  bundle carries no `.py`/`.pyc` for licence logic. Free (no PyArmor).
- Periodic online sync for entitlement state.
- Feature flags for paid modules such as cloud backup and matter RAG.
- Privacy-allowlisted admin check-in payloads.
- Local grace behavior from the last successful owner-backend sync.
- Payment plan and entitlement decisions with admin override state.

## License Fields

- installation ID
- license ID
- firm display name
- plan (solo, pro, enterprise)
- features (document_intake, cloud_backup, managed_restore, matter_rag, hosted_ai)
- expiry date
- issued_at timestamp
- RSA-PSS/SHA-256 signature over canonical JSON (sorted keys, no whitespace)

## Verification Flow

1. Read `license.key` from the app directory or `%APPDATA%\WakiliOS\`.
2. Parse JSON, re-serialize with sorted keys and no whitespace.
3. Verify signature against the hard-coded `_PUBLIC_KEY_PEM`.
4. Check `installation_id` matches local identity.
5. Check `expiry` is not past.
6. Return `LicenseValidationResult` with status and feature flags.

## Vendor Tools

- `tools/keygen.py` — Generate 4096-bit RSA key pair; auto-updates hard-coded key in `core.py`.
- `tools/sign_license.py` — Sign a license for a customer's installation ID.
- `scripts/obfuscate_licensing.py` — Cython-compile licensing modules for release builds.

## Clock-Rollback Guard

- `InMemoryStore` for tests, `FileStore` for production.
- `check_clock(store, now=..., ntp=...)` returns `(ok, reason)`.
- NTP cross-check with configurable tolerance (default 1 day).
- Degrades gracefully: missing stored value is treated as first run; NTP failure
  is non-fatal.

## Key Substitution Attack

In a non-obfuscated build, an attacker could:
1. Replace `resources/license_public_key.pem` on disk (defeated: key is hard-coded).
2. Edit `licensing/core.py` to use a different key (defeated: Cython compiles to `.pyd`).
3. Patch the `.pyd` binary (requires reverse engineering native code).

The hard-coded key + Cython obfuscation raises the bar from "replace a file" to
"reverse-engineer native code."