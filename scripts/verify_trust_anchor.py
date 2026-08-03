"""Verify the shipped license trust anchor is internally consistent.

The public key is published in two places: embedded in ``licensing/core.py``
(compiled into ``licensing/core.pyd`` for release builds) and as a data file at
``resources/license_public_key.pem``, which ``main.spec`` bundles. Verification
only ever uses the embedded copy, so a drift between the two is invisible at
runtime until a customer's license is rejected.

Run this after ``scripts/obfuscate_licensing.py`` as well as before it: the
release path never exercises license verification -- ``--selftest`` does not --
so a key mangled by the Cython step would otherwise ship green.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from licensing.core import embedded_public_key_pem  # noqa: E402


def _normalize(pem: bytes) -> bytes:
    return pem.replace(b"\r\n", b"\n").strip()


def main() -> int:
    resources_path = ROOT / "resources" / "license_public_key.pem"
    if not resources_path.is_file():
        print(f"FAIL: {resources_path} is missing", file=sys.stderr)
        return 1

    embedded = _normalize(embedded_public_key_pem())
    published = _normalize(resources_path.read_bytes())

    if embedded != published:
        print(
            "FAIL: licensing/core publishes a different key than "
            "resources/license_public_key.pem; one was changed without the other",
            file=sys.stderr,
        )
        return 1

    if not embedded.startswith(b"-----BEGIN PUBLIC KEY-----"):
        print("FAIL: embedded trust anchor is not a PEM public key", file=sys.stderr)
        return 1

    print("trust anchor OK: embedded key matches resources/license_public_key.pem")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
