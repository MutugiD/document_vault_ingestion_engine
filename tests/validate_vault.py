"""Validate F2 encrypted vault behavior."""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vault import (  # noqa: E402
    InvalidRecoveryKeyError,
    ObjectNotFoundError,
    initialize_vault,
    open_vault,
)


def main() -> None:
    plaintext = (
        b"CONFIDENTIAL PLEADING: Republic v Example. "
        b"This exact text must not appear in the encrypted object."
    )
    recovery_key = "correct horse battery staple for vault v1"

    with tempfile.TemporaryDirectory() as temporary_dir:
        vault_root = Path(temporary_dir) / "legal-vault"
        session = initialize_vault(vault_root, recovery_key)

        assert session.paths.database.exists()
        assert session.paths.objects.exists()
        assert session.paths.quarantine.exists()
        assert session.paths.backups.exists()

        stored_object = session.write_object(
            plaintext,
            original_name="sample-pleading.pdf",
            content_type="application/pdf",
            actor="validator",
        )

        assert stored_object.sha256 == hashlib.sha256(plaintext).hexdigest()
        assert stored_object.size_bytes == len(plaintext)
        assert stored_object.object_path.exists()
        encrypted_bytes = stored_object.object_path.read_bytes()
        assert encrypted_bytes != plaintext
        assert b"CONFIDENTIAL PLEADING" not in encrypted_bytes

        metadata = session.get_object(stored_object.object_id)
        assert metadata.object_id == stored_object.object_id
        assert metadata.original_name == "sample-pleading.pdf"
        assert metadata.content_type == "application/pdf"

        assert session.read_object(stored_object.object_id) == plaintext

        reopened_session = open_vault(vault_root, recovery_key)
        assert reopened_session.read_object(stored_object.object_id) == plaintext

        audit_types = [event.event_type for event in reopened_session.audit_events()]
        assert "vault_initialized" in audit_types
        assert "object_stored" in audit_types

        try:
            open_vault(vault_root, "wrong recovery key")
        except InvalidRecoveryKeyError:
            pass
        else:
            raise AssertionError("wrong recovery key unexpectedly unlocked the vault")

        try:
            reopened_session.read_object("missing-object-id")
        except ObjectNotFoundError:
            pass
        else:
            raise AssertionError("missing object unexpectedly returned data")

    print("VAULT VALIDATION PASS")


if __name__ == "__main__":
    main()
