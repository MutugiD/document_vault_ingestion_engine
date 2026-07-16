"""
Vendor signing tool for WakiliOS licenses.

Produces a license.key JSON file for a customer's installation.
Uses _vendor/private_key.pem. Never ship this script or the private key.

Usage:
    python tools/sign_license.py <installation_id> <firm_name> <plan> <expiry YYYY-MM-DD> [out=license.key]

    plan: solo, pro, enterprise

The installation_id comes from the customer's installation.json or --selftest output.
"""

import base64
import json
import os
import sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from licensing.core import LicenseDocument, FeatureEntitlements, canonical_license_bytes  # noqa: E402


PLAN_FEATURES = {
    "solo": FeatureEntitlements(
        document_intake=True,
        cloud_backup=False,
        managed_restore=False,
        matter_rag=True,
        hosted_ai=False,
    ),
    "pro": FeatureEntitlements(
        document_intake=True,
        cloud_backup=True,
        managed_restore=True,
        matter_rag=True,
        hosted_ai=False,
    ),
    "enterprise": FeatureEntitlements(
        document_intake=True,
        cloud_backup=True,
        managed_restore=True,
        matter_rag=True,
        hosted_ai=True,
    ),
}


def main() -> None:
    if len(sys.argv) < 5:
        print("usage: python tools/sign_license.py <installation_id> <firm_name> <plan> <expiry> [out]")
        print("  plan: solo, pro, enterprise")
        print("  out: output file path (default: license.key)")
        raise SystemExit(2)

    installation_id = sys.argv[1]
    firm_name = sys.argv[2]
    plan = sys.argv[3]
    expiry = sys.argv[4]
    out_path = sys.argv[5] if len(sys.argv) > 5 else "license.key"

    if plan not in PLAN_FEATURES:
        print(f"ERROR: unknown plan '{plan}'. Use: solo, pro, enterprise")
        raise SystemExit(1)

    priv_path = os.path.join(ROOT, "_vendor", "private_key.pem")
    if not os.path.exists(priv_path):
        print(f"ERROR: private key not found at {priv_path}")
        print("Run tools/keygen.py first to generate key pair.")
        raise SystemExit(1)

    with open(priv_path, "rb") as f:
        priv = serialization.load_pem_private_key(f.read(), password=None)

    from datetime import date, datetime, timezone
    from uuid import uuid4

    features = PLAN_FEATURES[plan]
    doc = LicenseDocument(
        installation_id=installation_id,
        license_id=str(uuid4()),
        firm_display_name=firm_name,
        plan=plan,
        features=features,
        expiry=date.fromisoformat(expiry),
        issued_at=datetime.now(timezone.utc),
        signature="",  # placeholder
    )

    # Sign the canonical payload
    payload_bytes = canonical_license_bytes(doc)
    sig = priv.sign(
        payload_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )

    # Create the signed document
    signed_doc = doc.unsigned_mapping() | {"signature": base64.b64encode(sig).decode("ascii")}

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(signed_doc, f, indent=2, sort_keys=True)
    print(f"wrote {out_path}")
    print(f"  installation_id: {installation_id}")
    print(f"  firm: {firm_name}")
    print(f"  plan: {plan}")
    print(f"  expiry: {expiry}")


if __name__ == "__main__":
    main()