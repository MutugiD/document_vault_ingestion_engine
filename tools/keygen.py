"""
RSA key generation for WakiliOS licensing.

Run ONCE, offline. Writes:
  resources/license_public_key.pem -> bundled in the app
    (and hard-coded in licensing/core.py, spec §6.2)
  _vendor/private_key.pem -> KEPT BY VENDOR ONLY, never bundled

Production uses 4096-bit (spec). Pass a size arg to override (tests use 2048 for speed).
"""

import os
import re
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(bits: int = 4096) -> None:
    priv = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )

    pub_path = os.path.join(ROOT, "resources", "license_public_key.pem")
    os.makedirs(os.path.dirname(pub_path), exist_ok=True)
    with open(pub_path, "wb") as f:
        f.write(pub_pem)

    vend_dir = os.path.join(ROOT, "_vendor")
    os.makedirs(vend_dir, exist_ok=True)
    with open(os.path.join(vend_dir, "private_key.pem"), "wb") as f:
        f.write(priv_pem)

    print(f"wrote {pub_path}")
    print(f"wrote {vend_dir}/private_key.pem  ({bits}-bit) -- keep this private, do NOT bundle")

    # Update the hard-coded public key in licensing/core.py (spec §6.2)
    core_path = os.path.join(ROOT, "licensing", "core.py")
    with open(core_path, encoding="utf-8") as f:
        content = f.read()

    new_key_block = f'_PUBLIC_KEY_PEM = b"""{pub_pem.decode("ascii")}"""'
    pattern = r'_PUBLIC_KEY_PEM = b""".+?"""'
    new_content = re.sub(pattern, new_key_block, content, flags=re.DOTALL)

    if new_content != content:
        with open(core_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"updated {core_path} with new public key")
    else:
        print(f"warning: could not find public key block in {core_path}")

    # Also write the .gitignore for _vendor/
    gitignore_path = os.path.join(vend_dir, ".gitignore")
    with open(gitignore_path, "w") as f:
        f.write("# Never commit vendor private keys\n*.pem\n")
    print(f"wrote {gitignore_path}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 4096)
