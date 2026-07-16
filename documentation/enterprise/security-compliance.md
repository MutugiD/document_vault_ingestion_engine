# Security And Compliance Rules

The enterprise version handles legal documents, so privacy and recovery guarantees
are product requirements rather than implementation details.

## Non-Negotiable Rules

- No real client documents in git, CI, release artifacts, test fixtures, logs, or screenshots.
- No private signing keys, provider API keys, cloud root credentials, `.env` secrets, or recovery keys in git or release artifacts.
- No plaintext legal documents in cloud storage.
- No admin access to matter content.
- No hidden telemetry.
- No direct court e-filing automation until explicitly designed and validated.

## License And Admin Boundary

Allowed check-in fields:

- `schema_version`, `installation_id`, `license_id`
- `app_version`, `device_nickname`
- `license_status`, `paid_entitlement_state`, `feature_flags`
- `coarse_backup_health` (status, last_success_age_hours, pending_upload_count)
- `generated_at`

Forbidden in check-in payloads (asserted by `assert_payload_privacy`):

- `client_name`, `matter_name`, `case_number`
- `filename`, `ocr_text`, `prompt`, `sha256`, `recovery`

## License Hardening (spec §6.2, §6.3)

- **Hard-coded RSA public key**: The public key is a bytes literal in `licensing/core.py`, not read from a swappable file. In release builds, Cython compiles this module to `licensing/core.pyd`, baking the key into native machine code.
- **Clock-rollback guard**: `licensing/clockguard.py` detects system clock tampering via monotonic timestamps and NTP cross-check. Locks the app on rollback; degrades gracefully when NTP is unreachable.
- **Cython obfuscation**: `scripts/obfuscate_licensing.py` compiles `licensing/core.py` and `licensing/clockguard.py` to `.pyd`. Release bundles ship no `.py`/`.pyc` for licence logic. Free (no PyArmor).
- **Vendor tools**: `tools/keygen.py` generates 4096-bit RSA key pairs. `tools/sign_license.py` signs licenses for customer installations using the vendor private key (stored in `_vendor/`, never committed).

## Clock-Rollback Guard

- Monotonic "last seen" UTC timestamp stored via abstracted `Store` interface.
- `InMemoryStore` for tests, `FileStore` for production (writes to `settings/clock.json`).
- `check_clock(store, now, ntp, ntp_tolerance_days)` returns `(ok, reason)`.
- NTP cross-check: if system clock is far behind NTP time (beyond tolerance), lock.
- Degrades gracefully: missing stored value = first run; NTP failure = non-fatal.

## Key-Substitution Attack Resistance

| Attack | Mitigation |
| --- | --- |
| Replace `resources/license_public_key.pem` on disk | Key is hard-coded in source; file is not read at runtime |
| Edit `licensing/core.py` to use a different key | Release builds compile to `licensing/core.pyd` (native code) |
| Patch `core.pyd` binary | Requires reverse-engineering native code (raises bar significantly) |

## Obfuscation Build

```powershell
pip install "cython>=3,<4"
python scripts\obfuscate_licensing.py           # compile + strip sources
python scripts\obfuscate_licensing.py --check    # verify Cython + compiler available
pyinstaller main.spec --noconfirm --clean
```