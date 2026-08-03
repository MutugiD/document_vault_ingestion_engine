"""Shared license activation setup for the UI evidence runners.

The evidence runners drive the real activation gate rather than bypassing it,
so each one needs a license the running process will accept. They cannot ship
a vendor-signed license (the private key never leaves the vendor), so they
substitute the trust anchor in-process with a fresh test key and sign a
license for this machine's installation identity.

.. warning::
   ``licensing_core._PUBLIC_KEY_PEM = ...`` only works while ``licensing.core``
   is a Python module. Release builds run ``scripts/obfuscate_licensing.py``,
   which Cython-compiles it to ``licensing/core.pyd``; attribute assignment on
   an extension module fails, and every license then reports ``bad_signature``.
   These runners are development tools and must not be run against an
   obfuscated checkout.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import licensing.core as licensing_core
from licensing import (
    FeatureEntitlements,
    LicenseDocument,
    canonical_license_bytes,
    ensure_installation_identity,
    write_license_file,
)


@dataclass(frozen=True)
class TestLicense:
    """Where the signed license landed, and who it was issued to."""

    path: Path
    installation_id: str


def sign_license(
    installation_id: str,
    private_key: rsa.RSAPrivateKey,
    *,
    license_id: str = "LIC-UI-EVIDENCE",
    firm_display_name: str = "Evidence Legal Practice",
    plan: str = "enterprise",
) -> LicenseDocument:
    """Produce a license document signed with ``private_key``."""
    document = LicenseDocument(
        installation_id=installation_id,
        license_id=license_id,
        firm_display_name=firm_display_name,
        plan=plan,
        features=FeatureEntitlements(True, True, True, True, True),
        expiry=date.today() + timedelta(days=365),
        issued_at=datetime.now(UTC),
        signature="",
    )
    signature = private_key.sign(
        canonical_license_bytes(document),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return LicenseDocument(
        installation_id=document.installation_id,
        license_id=document.license_id,
        firm_display_name=document.firm_display_name,
        plan=document.plan,
        features=document.features,
        expiry=document.expiry,
        issued_at=document.issued_at,
        signature=base64.b64encode(signature).decode("ascii"),
    )


def install_test_license(
    temp_root: Path,
    *,
    appdata: Path | None = None,
    firm_display_name: str = "Evidence Legal Practice",
) -> TestLicense:
    """Replace the embedded trust anchor and write a license for this machine.

    ``appdata`` defaults to ``%APPDATA%``; callers that sandbox it should have
    already set the environment variable before calling.
    """
    import os

    root = appdata or Path(os.environ["APPDATA"])
    identity = ensure_installation_identity(root / "WakiliOS" / "settings" / "installation.json")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    licensing_core._PUBLIC_KEY_PEM = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    license_path = temp_root / "license.key"
    write_license_file(
        license_path,
        sign_license(
            identity.installation_id,
            private_key,
            firm_display_name=firm_display_name,
        ),
    )
    return TestLicense(path=license_path, installation_id=identity.installation_id)
